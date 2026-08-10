"""文件上传接口 - 上传文档并自动建立向量索引"""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger

from app.services.vector_index_service import vector_index_service

router = APIRouter()

# 文件保存目录
UPLOAD_DIR = Path("./uploads")
# 单个文件最大 100MB
MAX_FILE_SIZE = 100 * 1024 * 1024


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文档并自动建立向量索引

    - 支持格式:txt / md / pdf / docx(图片格式待 OCR 扩展)
    - 上传后自动:分割 → 向量化 → 入库(可被 Agent 检索)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    # 规范化文件名(防路径注入)
    safe_filename = file.filename.replace(" ", "_")
    for ch in ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]:
        safe_filename = safe_filename.replace(ch, "_")

    # 保存文件
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / safe_filename

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过限制(最大 100MB)")

    file_path.write_bytes(content)
    logger.info(f"文件已保存: {file_path}")

    # 建立向量索引(失败不影响文件已保存的事实,但返回错误)
    try:
        chunk_count = vector_index_service.index_single_file(str(file_path))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"索引失败: {file_path}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"向量索引失败: {e}")

    return {
        "code": 200,
        "message": "success",
        "data": {
            "filename": safe_filename,
            "size": len(content),
            "chunks": chunk_count,
        },
    }


@router.post("/index_directory")
async def index_directory(directory_path: str = None):
    """批量索引目录下的所有支持文件(默认 uploads 目录)"""
    target = directory_path or str(UPLOAD_DIR)
    dir_path = Path(target)

    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(status_code=400, detail=f"目录不存在: {target}")

    results = {"success": [], "failed": []}
    for path in dir_path.iterdir():
        if not path.is_file():
            continue
        suffix = path.suffix.lower().lstrip(".")
        if suffix not in vector_index_service.ALLOWED_EXTENSIONS:
            continue
        try:
            chunks = vector_index_service.index_single_file(str(path))
            results["success"].append({"file": path.name, "chunks": chunks})
        except Exception as e:
            results["failed"].append({"file": path.name, "error": str(e)})

    return {
        "code": 200,
        "message": "success",
        "data": results,
    }
