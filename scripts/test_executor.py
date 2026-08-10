import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""测试 Executor - 只跑执行节点"""

import asyncio

from app.agent.aiops.executor import executor


async def main():
    state = {
        "input": "诊断当前系统是否存在告警",
        "plan": ["步骤1: 查询当前时间", "步骤2: 综合分析并生成报告"],
        "past_steps": [],
        "response": "",
    }
    result = await executor(state)
    print("\n剩余计划:", result["plan"])
    print("执行历史:", result["past_steps"][0][0][:20], "... 结果长度:", len(result["past_steps"][0][1]))


asyncio.run(main())