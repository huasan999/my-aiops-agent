"""诊断任务管理器 - 异步执行 AIOps 诊断

企业级模式:POST /api/aiops 立即返回 task_id,诊断在后台任务执行,
客户端通过 GET /api/aiops/{task_id}/events 订阅 SSE 事件(先回放历史,再实时推送)。

设计:
- 进程内 asyncio 后台任务(单机够用;多实例时需换 Redis/Celery 队列)
- 事件按 task_id 存内存队列,SSE 订阅者先回放已产生事件,再实时接收
- 任务完成/失败后保留事件供查询,带 TTL 自动清理
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

# 任务结果保留时长(秒):完成后可查询窗口,之后清理
TASK_TTL_SECONDS = 3600
# 单任务事件上限(防内存暴涨;诊断最多 6 步,正常 < 50 条)
MAX_EVENTS_PER_TASK = 200


class DiagnosisTask:
    """单个诊断任务:状态 + 事件流"""

    def __init__(self, task_id: str, session_id: str):
        self.task_id = task_id
        self.session_id = session_id
        self.status = "running"          # running | done | error
        self.events: List[Dict[str, Any]] = []
        self._subscribers: List[asyncio.Queue] = []
        self.created_at = time.time()
        self.finished_at: Optional[float] = None
        self._lock = asyncio.Lock()

    async def publish(self, event: Dict[str, Any]):
        """追加事件并推送给所有订阅者"""
        async with self._lock:
            if len(self.events) >= MAX_EVENTS_PER_TASK:
                return
            self.events.append(event)
            for q in self._subscribers:
                await q.put(event)

    async def subscribe(self) -> asyncio.Queue:
        """注册 SSE 订阅者(先回放历史,再实时)"""
        q = asyncio.Queue()
        async with self._lock:
            self._subscribers.append(q)
            # 新订阅者立即回放已有事件
            for ev in self.events:
                await q.put(ev)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    def finish(self, status: str):
        self.status = status
        self.finished_at = time.time()

    @property
    def expired(self) -> bool:
        base = self.finished_at or self.created_at
        return (time.time() - base) > TASK_TTL_SECONDS


class DiagnosisManager:
    """诊断任务注册表(懒初始化单例)"""

    def __init__(self):
        self._tasks: Dict[str, DiagnosisTask] = {}
        self._lock = asyncio.Lock()

    async def create(self, session_id: str) -> DiagnosisTask:
        """创建任务并登记(不启动;调用方负责启动后台协程)"""
        task_id = f"diag-{int(time.time() * 1000)}-{len(self._tasks) + 1}"
        task = DiagnosisTask(task_id, session_id)
        async with self._lock:
            self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> Optional[DiagnosisTask]:
        return self._tasks.get(task_id)

    async def cleanup(self):
        """清理过期任务(由 main lifespan 定时调用)"""
        async with self._lock:
            expired = [tid for tid, t in self._tasks.items() if t.expired]
            for tid in expired:
                del self._tasks[tid]
        if expired:
            print(f"[DiagnosisManager] 清理 {len(expired)} 个过期任务")


# 全局单例(懒初始化:无 import 期副作用)
diagnosis_manager = DiagnosisManager()
