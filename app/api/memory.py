"""记忆管理接口 - 向量记忆的清理"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.memory_store import memory_store

router = APIRouter()


class MemoryClearRequest(BaseModel):
    session_id: str | None = None   # 传了 = 只清这个会话;不传 = 清空全部


@router.post("/memory/clear")
async def clear_memory(request: MemoryClearRequest):
    """清理向量记忆

    - 传 session_id:只删除该会话的记忆
    - 不传:清空全部记忆
    """
    if request.session_id:
        deleted = memory_store.delete_session_memory(request.session_id)
        message = f"已清除会话 {request.session_id} 的 {deleted} 条记忆"
    else:
        deleted = memory_store.clear_all_memory()
        message = f"已清空全部记忆({deleted} 条)"

    return {"code": 200, "message": message, "data": {"deleted": deleted}}
