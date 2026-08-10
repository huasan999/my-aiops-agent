import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

﻿"""测试 Planner - 只跑规划节点"""

import asyncio

from app.agent.aiops.planner import planner


async def main():
    state = {
        "input": "诊断当前系统是否存在告警,如果有请分析告警原因并给出处理建议",
        "plan": [],
        "past_steps": [],
        "response": "",
    }
    result = await planner(state)
    print("\n[OK] 计划生成:", result["plan"])


asyncio.run(main())
