"""FastAPI 应用入口"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 加载 .env(若有):在 import 任何读取环境变量的模块之前
try:
    from dotenv import load_dotenv

    # 明确指定项目根 .env(兼容任意工作目录启动)
    _root = Path(__file__).resolve().parent.parent
    load_dotenv(_root / ".env")
except ImportError:
    pass

# Windows 平台:psycopg(async)不支持 ProactorEventLoop,必须用 Selector
# 必须在事件循环创建前设置(main.py 是最早被导入的入口模块)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


from app.api.aiops import router as aiops_router
from app.api.chat import router as chat_router
from app.api.file import router as file_router
from app.api.health import router as health_router
from app.api.memory import router as memory_router
from app.config import APP_NAME, PORT
from app.services.diagnosis_manager import diagnosis_manager
from app.services.memory_cleaner import memory_cleanup_loop


async def _diagnosis_cleanup_loop():
    """定时清理过期诊断任务(内存事件保留窗口)"""
    while True:
        await asyncio.sleep(600)   # 每 10 分钟
        try:
            await diagnosis_manager.cleanup()
        except Exception as e:
            print(f"[Cleanup] 诊断任务清理失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时挂载后台任务(记忆清理 + 诊断任务清理),关闭时取消"""
    task = asyncio.create_task(memory_cleanup_loop())
    diag_cleanup = asyncio.create_task(_diagnosis_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        diag_cleanup.cancel()
        try:
            await task
            await diag_cleanup
        except asyncio.CancelledError:
            pass


# 创建应用实例
app = FastAPI(title=APP_NAME, lifespan=lifespan)

app.include_router(health_router)
app.include_router(chat_router, prefix="/api")
app.include_router(aiops_router, prefix="/api")
app.include_router(file_router, prefix="/api")
app.include_router(memory_router, prefix="/api")

# 挂载静态文件(前端页面)
static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """根路径 - 返回前端页面"""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": f"Welcome to {APP_NAME}"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)