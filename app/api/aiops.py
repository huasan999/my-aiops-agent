"""AIOps 诊断接口 - 异步提交 + SSE 订阅

企业级模式:
- POST /api/aiops            提交诊断,立即返回 task_id(不占 HTTP 连接)
- GET  /api/aiops/{task_id}/events   SSE 订阅诊断事件(先回放历史,再实时)
- GET  /api/aiops/{task_id}  查询任务状态

SSE 事件:
- {"type":"plan", "plan": [...]}              计划生成
- {"type":"step_complete", "current_step": ...} 步骤完成
- {"type":"report", "report": "..."}          最终报告
- {"type":"complete"}                         完成
- {"type":"error", "message": "..."}          错误
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.services.aiops_service import aiops_service
from app.services.diagnosis_manager import diagnosis_manager

router = APIRouter()

# 内置诊断任务(和 test_aiops.py 一致)
DIAGNOSIS_TASK = (
    "诊断当前系统是否存在告警,如果有请详细分析告警原因并生成诊断报告,"
    "报告需包含:告警清单、根因分析、处理建议、风险评估"
)


class AIOpsRequest(BaseModel):
    session_id: str = "default"


async def _run_diagnosis(task_id: str, session_id: str):
    """后台执行诊断,事件写入任务流"""
    task = diagnosis_manager.get(task_id)
    if task is None:
        return

    try:
        async for event in aiops_service.stream_execute(
            DIAGNOSIS_TASK,
            session_id=session_id,
        ):
            await task.publish(event)
            if event.get("type") in ("complete", "error"):
                break
        task.finish("done" if task.status == "running" else task.status)
    except Exception as e:
        await task.publish({"type": "error", "stage": "error", "message": f"诊断出错: {str(e)}"})
        task.finish("error")


@router.post("/aiops", status_code=202)
async def aiops_submit(request: AIOpsRequest):
    """提交诊断任务:立即返回 task_id,后台异步执行

    202 Accepted + task_id(企业模式:不阻塞 HTTP 连接等分钟级诊断)
    """
    task = await diagnosis_manager.create(request.session_id)
    asyncio.create_task(_run_diagnosis(task.task_id, request.session_id))
    return {
        "code": 202,
        "task_id": task.task_id,
        "session_id": request.session_id,
        "status": task.status,
        "message": "诊断任务已提交",
    }


@router.get("/aiops/{task_id}/events")
async def aiops_events(task_id: str):
    """SSE 订阅诊断事件:先回放已产生事件,再实时推送"""
    task = diagnosis_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    async def event_generator():
        queue = await task.subscribe()
        try:
            while True:
                event = await queue.get()
                yield {
                    "event": "message",
                    "data": json.dumps(event, ensure_ascii=False),
                }
                # 终态事件后结束;或任务已完成且事件队列耗尽
                if event.get("type") in ("complete", "error"):
                    break
                if task.status in ("done", "error") and queue.empty():
                    break
        finally:
            task.unsubscribe(queue)

    return EventSourceResponse(event_generator())


@router.get("/aiops/{task_id}")
async def aiops_status(task_id: str):
    """查询任务状态(轮询式客户端用)"""
    task = diagnosis_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {
        "code": 200,
        "task_id": task.task_id,
        "session_id": task.session_id,
        "status": task.status,
        "event_count": len(task.events),
        "last_event": task.events[-1] if task.events else None,
    }


@router.get("/aiops/state/{session_id}")
async def aiops_state(session_id: str):
    """按 session_id 从持久化 checkpointer 读取诊断状态(崩溃恢复用)

    应用重启后,内存中的任务注册表(diagnosis_manager)会丢失,
    但 Postgres 检查点保留了诊断进度 —— 通过本接口可找回崩溃前的状态。
    """
    state = await aiops_service.get_persisted_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="该会话无持久化诊断状态")
    return {
        "code": 200,
        "session_id": session_id,
        "step_count": state.get("step_count"),
        "plan": state.get("plan", []),
        "past_steps": state.get("past_steps", []),
        "response": state.get("response", ""),
    }
