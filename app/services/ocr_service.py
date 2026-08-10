"""OCR 服务 - 基于 RapidOCR(PaddleOCR 模型的 ONNX 实现)

为什么用 RapidOCR 而不是 PaddleOCR:
- 同一个模型(PP-OCR),识别效果一致
- 推理引擎是 onnxruntime,不依赖 paddle 框架(规避 paddle 3.3 在部分
  环境的执行器 bug,且安装轻量)
"""

from loguru import logger
from rapidocr_onnxruntime import RapidOCR

# 支持的图片格式
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "webp"}


class OCRService:
    """图片文字识别服务"""

    def __init__(self):
        self._engine = None   # 懒加载:首次识别时才初始化(模型加载较慢)

    def _get_engine(self):
        if self._engine is None:
            logger.info("初始化 RapidOCR 引擎(首次调用需加载模型)...")
            self._engine = RapidOCR()
        return self._engine

    def image_to_text(self, image_path: str) -> str:
        """识别图片中的文字,按行拼接返回

        Args:
            image_path: 图片路径

        Returns:
            str: 识别出的文本(识别不到返回空串)
        """
        engine = self._get_engine()
        result, _ = engine(image_path)

        if not result:
            logger.warning(f"图片未识别到文字: {image_path}")
            return ""

        text = "\n".join(line[1] for line in result)
        logger.info(f"OCR 识别完成: {image_path}, {len(result)} 行")
        return text


# 全局单例(懒加载,不占启动时间)
ocr_service = OCRService()
