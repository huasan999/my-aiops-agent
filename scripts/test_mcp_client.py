import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""测试 MCP 客户端 - 里程碑 5"""

import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient


async def main():
    # 1. 创建客户端,指向时钟服务器
    client = MultiServerMCPClient({
        "clock": {
            "transport": "streamable-http",
            "url": "http://127.0.0.1:8003/mcp",
        }
    })

    # 2. 拉取服务器发布的工具列表
    tools = await client.get_tools()
    print("MCP 服务器发布的工具:", [t.name for t in tools])

    # 3. 像调用本地工具一样调用远程工具
    result = await tools[0].ainvoke({"timezone": "Asia/Shanghai"})
    print("远程调用结果:", result)


asyncio.run(main())