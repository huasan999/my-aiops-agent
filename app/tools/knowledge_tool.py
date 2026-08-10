"""知识检索工具 - 从 Milvus 知识库检索相关文档"""

from langchain_core.tools import tool

from app.services.vector_store_manager import vector_store_manager


@tool
def retrieve_knowledge(query: str) -> str:
    """从知识库中检索相关文档来回答问题。

    当用户的问题涉及专业知识、运维经验、故障排查方案时,使用此工具。

    Args:
        query: 要检索的问题或关键词
    """
    retriever = vector_store_manager.get_retriever(k=3)
    docs = retriever.invoke(query)

    if not docs:
        return "没有找到相关信息。"

    parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("_file_name", "未知来源")
        parts.append(f"【参考资料{i} 来源:{source}】\n{doc.page_content}")

    return "\n\n".join(parts)