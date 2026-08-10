"""Replanner 节点 - 评估执行结果,决定下一步"""

import os
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agent.aiops.state import PlanExecuteState

# 保险丝上限:最多执行的步骤数,超出强制收尾(防死循环)
MAX_EXECUTION_STEPS = 6


class Act(BaseModel):
    """决策输出格式"""

    action: str = Field(
        description="下一步行动: continue(继续) / replan(调整计划) / respond(生成最终响应)"
    )
    new_steps: List[str] = Field(
        default_factory=list, description="replan 时提供的新步骤列表"
    )


REPLANNER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个重新规划专家,根据已执行的步骤决定下一步行动。

三个选择(按优先级):
1. 'respond' - 信息已足够,立即生成最终响应 【最高优先级】
2. 'continue' - 计划合理,继续执行下一步
3. 'replan' - 计划有严重问题,调整计划 【最低优先级,谨慎】

决策标准:
- 已执行 >= 3 步且获取了关键信息 → respond
- 剩余步骤仍能提供关键信息 → continue
- 剩余步骤明显无用或遗漏关键步骤 → replan(新步骤数不能超过剩余数)

重要:以 JSON 返回:{{"action": "respond", "new_steps": []}}"""),
    ("placeholder", "{messages}"),
])


async def replanner(state: PlanExecuteState) -> Dict[str, Any]:
    """评估已执行步骤,决定:继续 / 调整 / 收尾"""
    plan = state.get("plan", [])
    past_steps = state.get("past_steps", [])

    # 保险丝:执行步骤过多时强制收尾(防死循环)
    # 优先用显式 step_count(不依赖历史列表),fallback 到 len(past_steps)
    step_count = state.get("step_count") or len(past_steps)
    if step_count >= MAX_EXECUTION_STEPS:
        print(f"[Replanner] 已执行 {step_count} 步,强制收尾")
        return await _generate_response(state)

    # 计划已执行完 → 生成最终响应
    if not plan:
        print("[Replanner] 计划执行完毕,生成最终响应")
        return await _generate_response(state)

    # 还有剩余计划 → 让 LLM 决策
    llm = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8006/v1"),
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )
    chain = REPLANNER_PROMPT | llm.with_structured_output(Act, method="json_mode")

    steps_summary = "\n".join([f"步骤: {s}\n结果: {r[:200]}" for s, r in past_steps])

    act = await chain.ainvoke({
        "messages": [
            ("user", f"原始任务: {state['input']}"),
            ("user", f"已执行的步骤:\n{steps_summary}"),
            ("user", f"剩余计划: {', '.join(plan)}"),
        ]
    })

    if act.action == "respond":
        print("[Replanner] 决策: 信息足够,生成最终响应")
        return await _generate_response(state)

    if act.action == "replan" and act.new_steps:
        print(f"[Replanner] 决策: 调整计划 → {len(act.new_steps)} 个新步骤")
        return {"plan": act.new_steps}

    print("[Replanner] 决策: 继续执行")
    return {}   # 不修改状态 → 图继续跑 executor


async def _generate_response(state: PlanExecuteState) -> Dict[str, Any]:
    """生成最终响应(诊断报告)"""
    input_text = state.get("input", "")
    past_steps = state.get("past_steps", [])

    execution_history = "\n\n".join([
        f"### 步骤: {s}\n**结果:**\n{r}" for s, r in past_steps
    ])

    llm = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8006/v1"),
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )

    response = await llm.ainvoke([
        SystemMessage(content="根据原始任务和已执行步骤的结果,生成结构化的最终响应。要求:清晰、基于实际数据、使用 Markdown 格式。"),
        HumanMessage(content=f"原始任务: {input_text}\n\n执行历史:\n{execution_history}"),
    ])

    return {"response": response.content}
