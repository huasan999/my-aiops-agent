"""健康检查接口"""

from fastapi import APIRouter

from app.config import APP_NAME

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查 - 返回服务状态"""
    return {
        "status": "healthy",
        "service": APP_NAME,
    }