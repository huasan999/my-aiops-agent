"""向量存储管理器 - 封装 Milvus 的增/查操作"""

import asyncio

from langchain_milvus import Milvus

from app.services.vector_embedding_service import embedding_service

COLLECTION_NAME = "knowledge"


class VectorStoreManager:
    """向量存储管理器

    职责:
    - 连接 Milvus,管理 collection(自动创建)
    - add_documents: 文档入库(自动向量化)
    - get_retriever: 获取检索器(给 Agent 用)

    注意:懒初始化 —— 不在模块导入期创建(避免触碰事件循环,
    PyCharm 调试器的 asyncio hook 会缓存当前 loop,导入期创建
    又关闭的 loop 会污染它,导致 "Event loop is closed")。
    首次使用时才创建;FastAPI 请求环境已有 running loop,
    AsyncMilvusClient 能直接创建成功,无警告。
    """

    def __init__(self):
        self.vector_store = None

    # ---------- 懒初始化 ----------
    def _ensure_store(self):
        """首次使用时才创建 VectorStore"""
        if self.vector_store is None:
            self._initialize()

    def _initialize(self):
        # 判断当前有没有运行中的事件循环
        try:
            asyncio.get_running_loop()
            has_running_loop = True
        except RuntimeError:
            has_running_loop = False

        if has_running_loop:
            # FastAPI 等异步环境:直接构造,AsyncMilvusClient 复用当前 loop
            self.vector_store = self._build_store()
        else:
            # 同步脚本环境(如 test_index.py):临时 loop 里构造,
            # 让 AsyncMilvusClient 能拿到 running loop
            loop = asyncio.new_event_loop()
            try:
                self.vector_store = loop.run_until_complete(self._async_build())
            finally:
                loop.close()

    async def _async_build(self):
        return self._build_store()

    def _build_store(self):
        """创建 LangChain Milvus VectorStore"""
        # langchain-milvus 会自动:连接 Milvus → 建 collection → 建索引
        return Milvus(
            embedding_function=embedding_service,      # 用哪个嵌入模型
            collection_name=COLLECTION_NAME,          # collection 名
            connection_args={"host": "127.0.0.1", "port": "19530"},
            auto_id=False,                            # 我们自己管 id
            drop_old=False,                           # 不清旧数据
            text_field="content",                     # 文本存哪个字段
            vector_field="vector",
            primary_field="id",
            enable_dynamic_field=True,                # 元数据走动态字段(替代废弃的 metadata_field)
        )

    # ---------- 对外接口(全部先确保已初始化) ----------
    def add_documents(self, documents, ids=None):
        """文档入库(自动切成向量)"""
        self._ensure_store()
        return self.vector_store.add_documents(documents, ids=ids)

    def get_retriever(self, k: int = 3):
        """获取检索器:给定问题,返回最相似的 k 个文档"""
        self._ensure_store()
        return self.vector_store.as_retriever(search_kwargs={"k": k})


# 全局单例(注意:此时 vector_store 还是 None,首次使用才真正连接)
vector_store_manager = VectorStoreManager()
