from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool


@tool
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """获取指定时区的当前时间。

    当用户询问"现在几点"、"今天日期"、"今天星期几"等时间相关问题时，使用此工具。

    Args:
        timezone: 时区，默认为 Asia/Shanghai
    """
    now = datetime.now(ZoneInfo(timezone))
    return now.strftime("%Y-%m-%d %H:%M:%S")