import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""把 aiops-docs 下的文档索引进 Milvus - 里程碑 10"""

from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.vector_store_manager import vector_store_manager

# 1. 读取 + 切分:每篇文档切成若干"分片"(chunk)
def load_and_split(doc_dir: str = "aiops-docs"):
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    all_docs = []

    for path in Path(doc_dir).glob("*.md"):
        content = path.read_text(encoding="utf-8")
        docs = splitter.create_documents(
            [content],
            metadatas=[{"_file_name": path.name, "_source": str(path)}],
        )
        all_docs.extend(docs)
        print(f"  {path.name}: {len(docs)} 个分片")

    return all_docs


if __name__ == "__main__":
    print("开始切分文档...")
    docs = load_and_split()
    print(f"共 {len(docs)} 个分片,开始入库(Milvus + Ollama 向量化)...")
    vector_store_manager.add_documents(docs)
    print("[OK] 入库完成!")