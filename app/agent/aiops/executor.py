"""Executor 节点 - 执行计划中的单个步骤"""

import os
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.agent.aiops.state import PlanExecuteState
from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.time_tool import get_current_time
from app.tools.query_metrics_alerts import query_prometheus_alerts

# 执行器可用的工具(诊断时能查知识库/时间)
EXECUTOR_TOOLS = [get_current_time, retrieve_knowledge, query_prometheus_alerts]


async def executor(state: PlanExecuteState) -> Dict[str, Any]:
    """执行 plan[0],返回:剩余计划 + 本次执行历史

    流程:
    1. 取第一个步骤
    2. LLM 决定是否调用工具(工具循环,和里程碑 3 一样)
    3. 返回 {"plan": 剩余步骤, "past_steps": [(步骤, 结果)]}
    """
    plan = state.get("plan", [])
    if not plan:
        return {}

    task = plan[0]
    print(f"[Executor] 执行: {task}")

    llm = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8006/v1"),
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )
    llm_with_tools = llm.bind_tools(EXECUTOR_TOOLS)

    messages = [
        SystemMessage(content="你是一个执行助手,负责执行具体任务步骤。可以选择合适的工具获取信息,或者直接基于知识回答。不要编造数据,执行结果要清晰准确。"),
        HumanMessage(content=f"请执行以下任务: {task}"),
    ]

    # 第一步:LLM 决定是否调用工具
    response = await llm_with_tools.ainvoke(messages)

    if getattr(response, "tool_calls", None):
        messages.append(response)
        tool_map = {t.name: t for t in EXECUTOR_TOOLS}
        for tc in response.tool_calls:
            tool = tool_map[tc["name"]]
            tool_result = await tool.ainvoke(tc["args"])
            messages.append(ToolMessage(content=str(tool_result), tool_call_id=tc["id"]))

        # 工具结果回传后,让 LLM 生成最终答复
        final = await llm_with_tools.ainvoke(messages)
        result = final.content if hasattr(final, "content") else str(final)
    else:
        # 无工具调用:直接回答
        result = response.content if hasattr(response, "content") else str(response)


    # 返回更新:移除已执行的步骤 + 追加执行历史(operator.add) + 步数计数递增
    return {
        "plan": plan[1:],                    # 剩余计划
        "past_steps": [(task, result)],      # 本次步骤 + 结果
        "step_count": state.get("step_count", 0) + 1,   # 硬性保险丝计数
    }