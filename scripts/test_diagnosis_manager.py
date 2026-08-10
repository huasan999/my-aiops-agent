"""验证诊断任务管理器(异步提交/订阅,无需 LLM)"""
import asyncio
import sys
from pathlib import Path

# Windows:psycopg async 需要 SelectorEventLoop(必须在事件循环创建前)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.diagnosis_manager import diagnosis_manager
from app.services.aiops_service import aiops_service


async def test_manager():
    # 1. 创建 + 发布 + 订阅(先回放历史)
    task = await diagnosis_manager.create("test-session")
    assert task.task_id.startswith("diag-"), task.task_id
    await task.publish({"type": "plan", "plan": ["s1", "s2"]})
    await task.publish({"type": "step_complete", "current_step": "s1"})
    task.finish("done")

    q = await task.subscribe()
    got = []
    while not q.empty():
        got.append(await q.get())
    assert len(got) == 2, f"回放应收到 2 条事件,实际 {len(got)}"
    assert got[0]["type"] == "plan"
    assert got[1]["type"] == "step_complete"
    assert task.status == "done"
    print(f"[OK] DiagnosisManager: 发布/订阅/回放正常 ({task.task_id})")


async def test_graph_lazy_build():
    # 2. 懒初始化:未调用 execute 前 graph 为 None
    assert aiops_service._graph is None, "graph 不应在 import 期构建"
    # 构建图(compile + MemorySaver checkpointer,无外部依赖)
    graph = await aiops_service._get_graph()
    assert graph is not None
    print(f"[OK] 懒初始化: graph 首次调用才构建 ({type(graph).__name__})")


async def main():
    await test_manager()
    await test_graph_lazy_build()
    print("=" * 40)
    print("诊断任务管理器 + 懒初始化 验证通过")


asyncio.run(main())
