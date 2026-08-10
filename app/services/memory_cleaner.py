"""长期记忆定期清理任务 - 后台 asyncio 循环

FastAPI 启动时挂载,每天清理一次超过保留期的记忆。
"""

import asyncio

from loguru import logger

from app.services.memory_store import MEMORY_RETENTION_DAYS, memory_store

# 清理间隔(小时)
CLEANUP_INTERVAL_HOURS = 24


async def memory_cleanup_loop():
    """后台循环:每隔 CLEANUP_INTERVAL_HOURS 清理一次过期记忆"""
    logger.info(f"记忆清理任务启动:每 {CLEANUP_INTERVAL_HOURS} 小时清理超过 "
                f"{MEMORY_RETENTION_DAYS} 天的记忆")
    while True:
        try:
            deleted = memory_store.purge_expired(MEMORY_RETENTION_DAYS)
            if deleted:
                logger.info(f"定期清理:删除 {deleted} 条过期记忆")
        except Exception as e:
            logger.warning(f"定期清理记忆失败: {e}")
        # 等待下一个周期(启动后先等一轮,避免服务刚起就全量清理)
        await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)
