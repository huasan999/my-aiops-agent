"""Plan-Execute-Replan 服务 - 组装状态图"""

import os

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agent.aiops.executor import executor
from app.agent.aiops.planner import planner
from app.agent.aiops.replanner import replanner
from app.agent.aiops.state import PlanExecuteState
from app.core.tracing import get_callbacks

# 硬性保险丝:图级 recursion_limit(节点执行总次数上限,兜底防死循环)
# 正常情况下 4-6 步 + replanner 6 步保险丝,这里留足余量但设硬上限
RECURSION_LIMIT = 25


class AIOpsService:
    """三节点状态机:planner → executor → replanner(循环)→ END

    懒初始化:graph 首次调用时才编译(Postgres checkpointer 连接不在 import 期创建)
    """

    def __init__(self):
        self._graph = None

    async def _get_graph(self):
        """惰性编译状态图(首次调用时;AsyncPostgresSaver 需 await 初始化)"""
        if self._graph is None:
            self._graph = await self._build_graph()
            print("AIOps 状态机构建完成")
        return self._graph

    async def _build_graph(self):
        workflow = StateGraph(PlanExecuteState)

        # 三个节点
        workflow.add_node("planner", planner)
        workflow.add_node("executor", executor)
        workflow.add_node("replanner", replanner)

        # 入口:planner
        workflow.set_entry_point("planner")

        # 主线
        workflow.add_edge("planner", "executor")
        workflow.add_edge("executor", "replanner")

        # 条件边:replanner 之后去哪
        def should_continue(state: PlanExecuteState) -> str:
            if state.get("response"):
                return END          # 出了报告 → 结束
            if state.get("plan"):
                return "executor"   # 还有计划 → 继续执行
            return END              # 没计划没报告 → 结束(兜底)

        workflow.add_conditional_edges(
            "replanner",
            should_continue,
            {"executor": "executor", END: END},
        )

        # checkpointer:支持按 thread_id 保存状态(get_state 需要它)
        # 生产环境用 PostgresSaver(见 _get_checkpointer),本地无 Postgres 时退化为 MemorySaver
        return workflow.compile(checkpointer=await self._get_checkpointer())

    async def _get_checkpointer(self):
        """持久化 checkpointer 工厂(懒初始化)

        环境变量 CHECKPOINTER_DSN 指向 Postgres 时用 AsyncPostgresSaver(持久化,重启不丢);
        未配置时退化为 MemorySaver(进程内存,适合本地开发)。
        注意:懒初始化——不要在 import 期创建数据库连接。
        """
        dsn = os.environ.get("CHECKPOINTER_DSN", "").strip()
        if not dsn:
            return MemorySaver()
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg_pool import AsyncConnectionPool

            # AsyncPostgresSaver.setup() 用 CREATE INDEX CONCURRENTLY,必须 autocommit
            pool = AsyncConnectionPool(
                dsn,
                open=False,
                kwargs={"autocommit": True},
            )
            await pool.open()
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()   # 建表(幂等)
            return checkpointer
        except Exception as e:
            print(f"[Checkpointer] Postgres 初始化失败,退化 MemorySaver: {e}")
            return MemorySaver()

    async def _invoke_graph(self, initial_state: PlanExecuteState, config: dict):
        """统一入口:调用图 + 兜底捕获 GraphRecursionError(保险丝第三层)"""
        try:
            graph = await self._get_graph()
            return await graph.ainvoke(initial_state, config)
        except Exception as e:
            # recursion_limit 触发时 LangGraph 抛 GraphRecursionError
            if "recursion" in str(e).lower():
                print(f"[AIOps] 触发 recursion_limit 保险丝: {e}")
                return {**initial_state, "response": f"诊断中止:执行步骤过多,已触发保险丝({e})"}
            raise

    async def execute(self, user_input: str, session_id: str = "default") -> str:
        """执行完整诊断流程,返回最终报告"""
        initial_state: PlanExecuteState = {
            "input": user_input,
            "plan": [],
            "past_steps": [],
            "step_count": 0,
            "response": "",
        }
        result = await self._invoke_graph(
            initial_state,
            {
                "configurable": {"thread_id": session_id},
                "recursion_limit": RECURSION_LIMIT,
                "callbacks": get_callbacks(),
            },
        )
        return result.get("response", "")

    async def get_persisted_state(self, session_id: str) -> dict | None:
        """从持久化 checkpointer 读取指定会话的最新状态(崩溃恢复用)

        Returns:
            dict | None: 状态快照;该会话无记录或仅内存模式时返回 None
        """
        try:
            graph = await self._get_graph()
            # 内存 checkpointer 无法跨进程恢复,直接跳过
            if not hasattr(graph.checkpointer, "aget_tuple"):
                return None
            config = {"configurable": {"thread_id": session_id}}
            snapshot = await graph.checkpointer.aget_tuple(config)
            if snapshot is None:
                return None
            return dict(snapshot.state) if hasattr(snapshot, "state") else dict(snapshot.checkpoint.get("channel_values", {}))
        except Exception as e:
            print(f"[AIOps] 读取持久化状态失败: {e}")
            return None

    async def stream_execute(self, user_input: str, session_id: str = "default"):
        """流式执行:逐步产出格式化事件

        Yields:
            {"type": "plan" | "step_complete" | "report" | "complete" | "error", ...}
        """
        initial_state: PlanExecuteState = {
            "input": user_input,
            "plan": [],
            "past_steps": [],
            "step_count": 0,
            "response": "",
        }
        config = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": RECURSION_LIMIT,
            "callbacks": get_callbacks(),
        }

        try:
            graph = await self._get_graph()
            async for event in graph.astream(
                initial_state,
                config,
                stream_mode="updates",
            ):
                for node_name, node_output in event.items():
                    if not node_output:   # 节点无更新(返回空/None)时跳过
                        continue
                    if node_name == "planner":
                        plan = node_output.get("plan", [])
                        yield {
                            "type": "plan",
                            "stage": "plan_created",
                            "message": f"执行计划已制定,共 {len(plan)} 个步骤",
                            "plan": plan,
                        }
                    elif node_name == "executor":
                        plan = node_output.get("plan", [])
                        past_steps = node_output.get("past_steps", [])
                        if past_steps:
                            last_step, _ = past_steps[-1]
                            yield {
                                "type": "step_complete",
                                "stage": "step_executed",
                                "message": f"步骤执行完成 ({len(past_steps)}/{len(past_steps) + len(plan)})",
                                "current_step": last_step,
                                "remaining_steps": len(plan),
                            }
                    elif node_name == "replanner":
                        response = node_output.get("response", "")
                        if response:
                            yield {
                                "type": "report",
                                "stage": "final_report",
                                "message": "最终报告已生成",
                                "report": response,
                            }

            # 取最终状态收尾
            final_state = await graph.get_state(config)
            final_response = ""
            if final_state and final_state.values:
                final_response = final_state.values.get("response", "")
            yield {
                "type": "complete",
                "stage": "complete",
                "message": "诊断完成",
                "response": final_response,
            }

        except Exception as e:
            yield {"type": "error", "stage": "error", "message": f"诊断出错: {str(e)}"}


# 全局单例
aiops_service = AIOpsService()