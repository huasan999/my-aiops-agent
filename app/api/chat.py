"""对话接口 - 流式(SSE)"""

import json

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.llm_client import stream_chat

router = APIRouter()


class ChatRequest(BaseModel):
    Id: str = "default"        # 会话 ID(对齐原项目的字段名)
    Question: str
    image_url: str | None = None   # 多模态:图片 URL 或 data URL(base64)


@router.post("/chat_stream")
async def chat_stream_endpoint(request: ChatRequest):
    """流式对话(SSE) —— 打字机效果

    多模态:如果 image_url 不为空,会构造多模态消息
    """

    async def event_generator():
        # 逐 token 产出 → 包装成 SSE 事件
        async for text in stream_chat(
            request.Question,
            session_id=request.Id,
            image_url=request.image_url,
        ):
            yield {
                "event": "message",
                "data": json.dumps({"type": "content", "data": text}, ensure_ascii=False),
            }
        # 结束信号
        yield {
            "event": "message",
            "data": json.dumps({"type": "done"}, ensure_ascii=False),
        }

    return EventSourceResponse(event_generator())