import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""测试 LangGraph Agent + MCP 远程工具 - 里程碑 6"""

import asyncio
import os
from typing import Annotated, TypedDict

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.tools.time_tool import get_current_time


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


async def main():
    # ---- 1. 连接 MCP 服务器,拉取"远程"工具 ----
    mcp_client = MultiServerMCPClient({
        "clock": {
            "transport": "streamable-http",
            "url": "http://127.0.0.1:8003/mcp",
        }
    })
    mcp_tools = await mcp_client.get_tools()
    print("远程 MCP 工具:", [t.name for t in mcp_tools])

    # ---- 2. 混合:本地工具 + 远程工具(原项目的模式) ----
    # all_tools = [get_current_time] + mcp_tools
    all_tools = mcp_tools
    print("Agent 全部工具:", [t.name for t in all_tools])

    # ---- 3. 模型绑定所有工具 ----
    llm = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )
    llm_with_tools = llm.bind_tools(all_tools)

    # ---- 4. 建图 —— 和里程碑 4 的图一模一样,没改任何结构 ----
    def model_node(state: AgentState):
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    tool_node = ToolNode(all_tools)

    def route_after_model(state: AgentState) -> str:
        last = state["messages"][-1]
        return "tools" if last.tool_calls else END

    workflow = StateGraph(AgentState)
    workflow.add_node("model", model_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("model")
    workflow.add_edge("tools", "model")
    workflow.add_conditional_edges("model", route_after_model, {"tools": "tools", END: END})
    graph = workflow.compile()

    # ---- 5. 跑:故意问"本地工具管不着"的问题(纽约时间) ----
    result = await graph.ainvoke({
        "messages": [{"role": "user", "content": "现在纽约时间几点？"}],
    })

    # 打印完整对话流转,看工具是怎么被调用的
    print("\n--- 对话流转过程 ---")
    for m in result["messages"]:
        if getattr(m, "tool_calls", None):  # ← getattr 带默认值,没有这属性就返回 None
            print(f"  {type(m).__name__}: 申请调用 {[tc['name'] for tc in m.tool_calls]}")
        elif m.content:
            print(f"  {type(m).__name__}: {str(m.content)[:80]}")

    print("\n最终回答:", result["messages"][-1].content)


asyncio.run(main())