import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""测试 create_react_agent 一键 Agent + 会话记忆 - 里程碑 6.5"""

import asyncio
import os

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

from app.tools.time_tool import get_current_time


async def main():
    # ---- 1. 拉取远程 MCP 工具 ----
    mcp_client = MultiServerMCPClient({
        "clock": {
            "transport": "streamable-http",
            "url": "http://127.0.0.1:8003/mcp",
        }
    })
    mcp_tools = await mcp_client.get_tools()

    # ---- 2. 一行建 Agent:模型 + 工具 + 记忆 ----
    llm = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )

    agent = create_agent(
        llm,
        tools=[get_current_time] + mcp_tools,  # 本地 + 远程工具
        checkpointer=MemorySaver(),            # ← 记忆仓库
    )

    # thread_id = 会话钥匙:同一个钥匙 = 同一个会话
    config = {"configurable": {"thread_id": "session-001"}}

    # ---- 3. 第一轮:自我介绍 ----
    r1 = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "你好,我叫小明"}]},
        config,
    )
    print("第一轮:", r1["messages"][-1].content)

    # ---- 4. 第二轮:不自我介绍,直接问 —— 看它记不记得 ----
    r2 = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "我叫什么名字?顺便告诉我现在几点了"}]},
        config,
    )
    print("第二轮:", r2["messages"][-1].content)

    # ---- 5. 换个 thread_id —— 记忆就没了(新会话) ----
    config2 = {"configurable": {"thread_id": "session-002"}}
    r3 = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "我叫什么名字?"}]},
        config2,
    )
    print("新会话:", r3["messages"][-1].content)


asyncio.run(main())