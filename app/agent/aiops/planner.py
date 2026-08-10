"""Planner 节点 - 制定执行计划"""

import os
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agent.aiops.state import PlanExecuteState


class Plan(BaseModel):
    steps: List[str] = Field(description="完成任务所需的步骤列表,每步是完整描述")

PLANNER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专家级规划者,负责把复杂任务分解为可执行的步骤。
要求:
- 将任务分解为逻辑独立的步骤
- 步骤描述要具体、可操作(最好说明用哪个工具、传什么参数)
- 步骤之间有清晰依赖关系
- 一般 4-6 步,不要过多

重要:必须返回 JSON 格式,steps 是字符串数组:
{{"steps": ["步骤1: ...", "步骤2: ..."]}}"""),
    ("placeholder", "{messages}"),
])


async def planner(state: PlanExecuteState) -> Dict[str, Any]:
    """制定执行计划:任务 → 步骤列表"""
    input_text = state.get("input", "")

    llm = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8006/v1"),
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )

    # 结构化输出:强制模型返回 Plan(steps) 格式
    chain = PLANNER_PROMPT | llm.with_structured_output(Plan, method="json_mode")
    result = await chain.ainvoke({"messages": [("user", input_text)]})

    return {"plan": result.steps}