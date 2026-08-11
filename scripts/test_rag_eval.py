"""RAG 评测 - RAGAS 打分(忠实度 / 答案相关性 / 上下文精确率)

用法:
    python scripts/test_rag_eval.py

流程:
1. 5 个典型故障排查问题(对应 aiops-docs 五篇知识)
2. 检索:真实走 Milvus 知识库(retriever k=3)
3. 生成:DeepSeek(经网关 :8006),注入"禁止编造"规则
4. 打分:RAGAS faithfulness / answer_relevancy / context_precision
   - LLM 判官走本地网关,embedding 走 Ollama

指标含义:
- faithfulness     回答是否忠于检索到的知识(越高越少编造)
- answer_relevancy 回答是否切题(越高越少答非所问)
- context_precision 检到的文档是否相关(越高检索越准)
"""

import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---- ragas 0.4.3 兼容 shim ----
# ragas 无条件 import langchain_community.chat_models.vertexai,
# 而 langchain-community 0.4+ 已移除该模块。它仅用于 isinstance 检查
# (MULTIPLE_COMPLETION_SUPPORTED),注入占位类即可,不影响评测逻辑。
_Dummy = type("_DummyVertexAI", (), {})
_shim_chat = types.ModuleType("langchain_community.chat_models.vertexai")
_shim_chat.ChatVertexAI = _Dummy
sys.modules.setdefault("langchain_community.chat_models.vertexai", _shim_chat)
_shim_llms = types.ModuleType("langchain_community.llms.vertexai")
_shim_llms.VertexAI = _Dummy
sys.modules.setdefault("langchain_community.llms.vertexai", _shim_llms)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaEmbeddings
from langchain_openai import ChatOpenAI
from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
from ragas.run_config import RunConfig
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import _LLMContextPrecisionWithoutReference
from ragas.metrics._answer_relevance import AnswerRelevancy
from ragas.metrics._faithfulness import Faithfulness

from app.services.vector_store_manager import vector_store_manager

# 5 个典型故障排查问题(对应 aiops-docs 五篇知识)
QUESTIONS = [
    "CPU 使用率持续高于 90%,如何定位是哪个进程导致的?",
    "服务器内存持续增长并触发 OOM,排查思路是什么?",
    "磁盘使用率达到 95%,应该怎么处理?",
    "某服务突然不可用,健康检查失败,如何排查?",
    "接口响应变慢,如何定位瓶颈?",
]

LLM = ChatOpenAI(
    model="deepseek-v4-flash",
    base_url=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8006/v1"),
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
)
EMBEDDINGS = OllamaEmbeddings(
    model="nomic-embed-text-v2-moe:latest",
    base_url="http://127.0.0.1:11434",
)

ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是运维专家。基于提供的参考资料回答问题,不要编造参考资料之外的内容。回答要简洁、有条理。"),
    ("human", "问题: {question}\n\n参考资料:\n{contexts}"),
])


def retrieve(query: str) -> list:
    """真实检索知识库,返回分块文本列表"""
    retriever = vector_store_manager.get_retriever(k=3)
    docs = retriever.invoke(query)
    if not docs:
        return ["(未检索到相关资料)"]
    return [d.page_content for d in docs]


def answer(question: str, contexts: list) -> str:
    """基于检索结果生成回答(带禁止编造约束)"""
    chain = ANSWER_PROMPT | LLM
    return chain.invoke({
        "question": question,
        "contexts": "\n\n".join(contexts),
    }).content


def main():
    print(f"=== RAG 评测: {len(QUESTIONS)} 个问题 ===")
    samples = []
    for q in QUESTIONS:
        print(f"\n[1/3 检索] {q[:24]}...")
        contexts = retrieve(q)
        print(f"          检到 {len(contexts)} 块")
        print(f"[2/3 生成] DeepSeek 回答...")
        ans = answer(q, contexts)
        print(f"          回答: {ans[:40]}...")
        samples.append(SingleTurnSample(
            user_input=q,
            retrieved_contexts=contexts,
            response=ans,
        ))

    print(f"\n[3/3 打分] RAGAS 评测中(LLM 判官:DeepSeek,每指标多轮)...")
    dataset = EvaluationDataset(samples=samples)
    result = evaluate(
        dataset,
        metrics=[Faithfulness(), AnswerRelevancy(), _LLMContextPrecisionWithoutReference()],
        llm=LangchainLLMWrapper(LLM),
        embeddings=LangchainEmbeddingsWrapper(EMBEDDINGS),
        run_config=RunConfig(timeout=300, max_retries=3, max_workers=3),
        raise_exceptions=True,
    )

    df = result.to_pandas()
    print("\n=== 每题得分 ===")
    print(df.to_string(index=False))

    scores = result.scores
    n = len(scores)
    if n:
        print("\n=== 平均分 ===")
        for key in scores[0]:
            avg = sum(s[key] for s in scores) / n
            print(f"  {key}: {avg:.3f}")


if __name__ == "__main__":
    main()
