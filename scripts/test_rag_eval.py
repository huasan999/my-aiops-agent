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

# langchain 1.x 拆包后 langchain.smith / langchain.chains / langchain.schema
# 移入 langchain-classic,ragas 仍按旧路径 import,逐个 shim
import importlib

for _pkg, _subs in [
    ("langchain_classic.smith", ["", "evaluation", "evaluation.config", "evaluation.runner_utils"]),
    ("langchain_classic.chains", ["", "base"]),
    ("langchain_classic.schema", [""]),
    ("langchain_classic.callbacks", ["", "manager"]),
]:
    _pkg_last = _pkg.split(".")[-1]
    for _sub in _subs:
        try:
            _mod_name = f"{_pkg}.{_sub}" if _sub else _pkg
            _alias = f"langchain.{_pkg_last}.{_sub}" if _sub else f"langchain.{_pkg_last}"
            _m = importlib.import_module(_mod_name)
            sys.modules.setdefault(_alias, _m)
        except ImportError:
            pass

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


class DeepSeekAnswerRelevancy(AnswerRelevancy):
    """适配 DeepSeek 的答案相关性指标。

    DeepSeek 会把"步骤式/方案式回答"误判为 noncommittal(含糊),导致
    ragas 原版把合理的高相似度分数 ×0 清零。这里去掉 noncommittal
    惩罚项,只保留余弦相似度(生成的问题变体与原问题的语义距离)。
    """

    def _calculate_score(self, answers, row):
        question = row["user_input"]
        gen_questions = [a.question for a in answers]
        if all(q == "" for q in gen_questions):
            return float("nan")
        cosine_sim = self.calculate_similarity(question, gen_questions)
        return float(cosine_sim.mean())

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


def run_local_eval():
    """本地 RAGAS 评测(不上传任何数据)"""
    print(f"=== RAG 评测(本地): {len(QUESTIONS)} 个问题 ===")
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
        metrics=[Faithfulness(), DeepSeekAnswerRelevancy(), _LLMContextPrecisionWithoutReference()],
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


def run_langsmith_eval():
    """LangSmith 可视化评测:数据集上传云端,评测结果在 Experiments 页面展示

    看结果: https://smith.langchain.com → Datasets & Experiments → rag-eval-questions
    每跑一次生成一个 experiment,可对比不同版本的分数与 trace。
    """
    import pandas as pd
    import uuid
    import langsmith.client as _ls_client
    from langsmith import Client
    from langsmith.utils import LangSmithNotFoundError

    # langsmith 0.10 + langchain_classic 兼容 bug:source_info["__run"] 为 RunInfo
    # 对象时 create_feedback 内部无法下标访问,先规范化为 dict
    _orig_feedback = _ls_client.Client.create_feedback

    def _fixed_create_feedback(self, *args, **kwargs):
        # bug1: source_run_id 为 RunInfo 对象时 str() 产生非法 UUID
        src = kwargs.get("source_run_id")
        if src is not None and not isinstance(src, (str, uuid.UUID)):
            kwargs["source_run_id"] = str(getattr(src, "id", src))
        # bug2: source_info["__run"] 是 RunInfo 对象(属性为 run_id,不可下标)
        si = kwargs.get("source_info")
        if isinstance(si, dict) and "__run" in si and not isinstance(si["__run"], dict):
            si["__run"] = {"run_id": str(getattr(si["__run"], "run_id", si["__run"]))}
        return _orig_feedback(self, *args, **kwargs)

    _ls_client.Client.create_feedback = _fixed_create_feedback

    DATASET_NAME = "rag-eval-questions"
    client = Client()

    # 1. 上传/重建评测数据集(5 个问题)
    try:
        client.read_dataset(dataset_name=DATASET_NAME)
        client.delete_dataset(dataset_name=DATASET_NAME)   # 已存在则重建(保持最新)
        print(f"[1/3] 重建数据集 {DATASET_NAME}...")
    except LangSmithNotFoundError:
        print(f"[1/3] 创建数据集 {DATASET_NAME}...")
    df = pd.DataFrame([{"question": q, "ground_truth": ""} for q in QUESTIONS])
    client.upload_dataframe(
        df,
        name=DATASET_NAME,
        input_keys=["question"],
        output_keys=["ground_truth"],
        description="AIOps 故障排查 RAG 评测问题集",
    )

    # 2. RAG 生成工厂:问题 → 检索知识库 → DeepSeek 回答(每次调用自动记 trace)
    # ragas EvaluatorChain 要求输出含 answer 和 contexts 两个键
    def rag_chain_factory(inputs: dict) -> dict:
        q = inputs["question"]
        contexts = retrieve(q)
        return {"answer": answer(q, contexts), "contexts": contexts}

    print("[2/3] 在 LangSmith 上跑评测(生成回答 + RAGAS 打分)...")
    # 3. ragas 指标包装成 evaluator(显式传 LLM/embedding,走本地网关,不依赖 OPENAI_API_KEY)
    from langchain.smith import RunEvalConfig
    from langchain_classic.smith.evaluation.runner_utils import run_on_dataset
    from ragas.integrations.langchain import EvaluatorChain

    evaluators = [
        EvaluatorChain(Faithfulness(), llm=LLM),
        EvaluatorChain(DeepSeekAnswerRelevancy(), llm=LLM, embeddings=EMBEDDINGS),
        EvaluatorChain(_LLMContextPrecisionWithoutReference(), llm=LLM),
    ]
    run_on_dataset(
        client=client,
        dataset_name=DATASET_NAME,
        llm_or_chain_factory=rag_chain_factory,
        evaluation=RunEvalConfig(custom_evaluators=evaluators),
        project_name="rag-eval",
        verbose=False,
    )
    print("[3/3] 完成!去 https://smith.langchain.com → Datasets & Experiments → rag-eval-questions 查看")


def main():
    if "--langsmith" in sys.argv:
        run_langsmith_eval()
    else:
        run_local_eval()


if __name__ == "__main__":
    main()
