import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
from typing import Annotated, TypedDict
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.tools.time_tool import get_current_time


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# ============ 2. 定义"节点" ============
# 节点 A:模型节点 —— 调 LLM,可能提出工具调用
def model_node(state: AgentState):
    llm = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )
    llm_with_tools = llm.bind_tools([get_current_time])
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


# 节点 B:工具节点 —— LangGraph 自带的,自动执行所有工具调用
tool_node = ToolNode([get_current_time])


# ============ 3. 定义"路由":决定下一步去哪 ============
def route_after_model(state: AgentState) -> str:
    """看模型的最后一句话:要工具就去工具节点,否则结束"""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


# ============ 4. 组装成图 ============
workflow = StateGraph(AgentState)

workflow.add_node("model", model_node)
workflow.add_node("tools", tool_node)

workflow.set_entry_point("model")                          # 从 model 节点开始
workflow.add_edge("tools", "model")        # 工具执行完,回到模型
workflow.add_conditional_edges(                            # 模型节点后,按路由函数分叉
    "model",
    route_after_model,
    {"tools": "tools", END: END},
)

graph = workflow.compile()                                 # 编译成可执行图

# ============ 5. 跑 ============
result = graph.invoke({
    "messages": [{"role": "user", "content": "现在北京时间几点了？"}],
})
print("最终回答:", result["messages"][-1].content)