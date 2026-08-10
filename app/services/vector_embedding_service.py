"""向量嵌入服务"""

from langchain_ollama import OllamaEmbeddings

# Ollama 嵌入模型(768 维,本地运行)
MODEL = "nomic-embed-text-v2-moe:latest"
BASE_URL = "http://127.0.0.1:11434"


class LocalEmbeddings:
    """Ollama 嵌入模型封装

    职责:把"文本"变成"向量"(一串数字)。
    - embed_documents: 批量嵌入文档(入库时用)
    - embed_query: 嵌入单个查询(检索时用)
    """

    def __init__(self, model=MODEL, base_url=BASE_URL):
        self._embeddings = OllamaEmbeddings(model=model, base_url=base_url)

    def embed_documents(self, texts):
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text):
        return self._embeddings.embed_query(text)


# 全局单例
embedding_service = LocalEmbeddings()