"""时钟 MCP 服务器 - 里程碑 5

把"获取时间"这个工具发布成独立 MCP 服务器,
让任何 Agent/程序都能通过 HTTP 调用它。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import FastMCP

# 1. 创建 MCP 服务器实例
mcp = FastMCP("Clock")


# 2. 定义工具 —— 注意装饰器是 @mcp.tool(),不是 @tool
@mcp.tool()
def get_time(timezone: str = "Asia/Shanghai") -> str:
    """获取指定时区的当前时间

    Args:
        timezone: 时区,默认为 Asia/Shanghai
    """
    now = datetime.now(ZoneInfo(timezone))
    return now.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    # 3. 以 HTTP 模式运行在 8003 端口
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8003, path="/mcp")