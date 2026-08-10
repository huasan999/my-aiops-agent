"""向量记忆存储 - 把历史对话存入 Milvus,支持跨会话回忆

对比:
- MemorySaver = 短期记忆(内存,只记当前 thread_id,重启丢)
- 本模块     = 长期记忆(向量库,所有会话的历史,可跨会话检索)
"""

import asyncio
import uuid
from datetime import datetime

from langchain_core.documents import Document
from langchain_milvus import Milvus

from app.services.vector_embedding_service import embedding_service

COLLECTION_NAME = "memories"      # 和知识库 biz 分开,互不干扰
MEMORY_TOP_K = 3                  # 每次最多回忆几条
MEMORY_RETENTION_DAYS = 30        # 记忆保留天数,超过自动清理


class MemoryStore:
    """向量记忆:对话 → 向量化入库;新问题 → 检索相关历史"""

    def __init__(self):
        self.vector_store = None

    # 懒初始化:直接同步构造(FastAPI 环境有 running loop,无需临时 loop)
    def _ensure_store(self):
        if self.vector_store is None:
            self.vector_store = Milvus(
                embedding_function=embedding_service,
                collection_name=COLLECTION_NAME,
                connection_args={"host": "127.0.0.1", "port": "19530"},
                auto_id=False,
                drop_old=False,
                text_field="content",
                vector_field="vector",
                primary_field="id",
                enable_dynamic_field=True,
            )

    def save_conversation(self, session_id: str, question: str, answer: str):
        """保存一轮对话(问题 + 回答)进记忆库"""
        self._ensure_store()
        ts = datetime.now().isoformat()
        docs = [
            Document(page_content=question, metadata={"thread_id": session_id, "role": "user", "ts": ts}),
            Document(page_content=answer, metadata={"thread_id": session_id, "role": "assistant", "ts": ts}),
        ]
        ids = [str(uuid.uuid4()) for _ in docs]
        self.vector_store.add_documents(docs, ids=ids)

    def recall(self, question: str, k: int = MEMORY_TOP_K) -> str:
        """检索与当前问题最相关的历史对话(跨会话)"""
        self._ensure_store()
        docs = self.vector_store.similarity_search(question, k=k)
        if not docs:
            return ""
        parts = []
        for d in docs:
            role = d.metadata.get("role", "?")
            ts = d.metadata.get("ts", "")[:16]
            parts.append(f"[{ts} {role}] {d.page_content}")
        return "\n".join(parts)

    def delete_session_memory(self, session_id: str) -> int:
        """删除指定会话的所有记忆(按 thread_id)"""
        self._ensure_store()
        collection = self.vector_store.col
        expr = f'metadata["thread_id"] == "{session_id}"'
        result = collection.delete(expr)
        return result.delete_count if hasattr(result, "delete_count") else 0

    def clear_all_memory(self) -> int:
        """清空全部记忆"""
        self._ensure_store()
        collection = self.vector_store.col
        total = collection.num_entities
        expr = 'metadata["thread_id"] != ""'
        result = collection.delete(expr)
        return total

    def purge_expired(self, days: int = MEMORY_RETENTION_DAYS) -> int:
        """定期清理:删除超过 days 天的记忆(按 ts 时间戳)

        用于后台定时任务,防止记忆库无限膨胀。
        """
        from datetime import datetime, timedelta

        self._ensure_store()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        collection = self.vector_store.col
        # ISO 时间戳字符串,字典序 = 时间序,可以直接 < 比较
        expr = f'metadata["ts"] < "{cutoff}"'
        result = collection.delete(expr)
        return result.delete_count if hasattr(result, "delete_count") else 0


# 全局单例
memory_store = MemoryStore()
