import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""测试流式输出 - 里程碑 8"""

import asyncio
import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from app.tools.time_tool import get_current_time


async def main():
    llm = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )

    agent = create_agent(
        llm,
        tools=[get_current_time],
        checkpointer=MemorySaver(),
    )

    config = {"configurable": {"thread_id": "stream-test"}}

    print("开始流式输出(注意文字是逐字出现的):")
    print("=" * 50)

    # astream:一个 token 一个 token 地吐
    async for event in agent.astream(
        {"messages": [{"role": "user", "content": "请用三句话介绍什么是 AIOps"}]},
        config,
        stream_mode="messages",   # ← 按"消息"粒度流式
    ):
        token, metadata = event
        if hasattr(token, "content") and token.content:
            print(token.content, end="", flush=True)   # flush=True:立即打印,不攒缓冲

    print("\n" + "=" * 50)


asyncio.run(main())