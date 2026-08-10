import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""测试完整 AIOps 诊断流程"""

import asyncio

from app.services.aiops_service import aiops_service


async def main():
    report = await aiops_service.execute(
        "诊断当前系统是否存在告警,如果有请分析告警原因并给出处理建议"
    )
    print("=" * 50)
    print("最终诊断报告:")
    print(report)


asyncio.run(main())