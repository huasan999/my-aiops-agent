"""向量索引服务 - 负责读取文件、分割、向量化、入库"""

from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from app.services.ocr_service import IMAGE_EXTENSIONS
from app.services.vector_store_manager import vector_store_manager

# 支持的文件类型(文本/文档用加载器;图片走 OCR)
ALLOWED_EXTENSIONS = {"txt", "md", "pdf", "docx"} | IMAGE_EXTENSIONS


class VectorIndexService:
    """向量索引服务

    职责:文件 → 文本 → 分割 → 向量化 → Milvus 入库
    """

    def __init__(self):
        self.upload_path = "./uploads"
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    def index_single_file(self, file_path: str) -> int:
        """索引单个文件

        Args:
            file_path: 文件路径

        Returns:
            int: 入库的分片数量

        Raises:
            ValueError: 文件不存在或类型不支持
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise ValueError(f"文件不存在: {file_path}")

        suffix = path.suffix.lower().lstrip(".")
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的文件类型: {suffix},仅支持: {sorted(ALLOWED_EXTENSIONS)}")

        # 1. 提取文本(按类型分派)
        text = self._extract_text(path, suffix)
        if not text.strip():
            logger.warning(f"文件内容为空: {file_path}")
            return 0

        # 2. 分割
        docs = self.splitter.create_documents(
            [text],
            metadatas=[{"_file_name": path.name, "_source": str(path)}],
        )
        logger.info(f"文件 {path.name} 分割为 {len(docs)} 个分片")

        # 3. 入库(自动向量化)
        if docs:
            vector_store_manager.add_documents(docs)

        return len(docs)

    # ---------- 文本提取(按扩展名分派) ----------
    @staticmethod
    def _extract_text(path: Path, suffix: str) -> str:
        """把文件内容变成纯文本"""
        if suffix == "pdf":
            # PyMuPDFLoader:纯文本 PDF(扫描件 PDF 可先转图片再走 OCR)
            from langchain_community.document_loaders import PyMuPDFLoader

            docs = PyMuPDFLoader(str(path)).load()
            return "\n".join(d.page_content for d in docs)

        if suffix == "docx":
            from langchain_community.document_loaders import Docx2txtLoader

            docs = Docx2txtLoader(str(path)).load()
            return "\n".join(d.page_content for d in docs)

        if suffix in IMAGE_EXTENSIONS:
            # 图片:OCR 识别成文本(懒加载引擎)
            from app.services.ocr_service import ocr_service

            return ocr_service.image_to_text(str(path))

        # txt / md:直接读文本(UTF-8 优先,回退 GBK 兼容 Windows 中文)
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="gbk", errors="ignore")


# 全局单例
vector_index_service = VectorIndexService()
