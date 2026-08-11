"""LLM 客户端"""

import base64
import os
from typing import AsyncGenerator

import httpx
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from app.services.memory_store import memory_store
from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.query_metrics_alerts import query_prometheus_alerts
from app.tools.time_tool import get_current_time
from app.tools.web_search_tool import web_search

# ollama 原生 API(多模态绕过 OpenAI 兼容层)
OLLAMA_NATIVE_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_VL_MODEL = "qwen2.5vl:7b"
MODEL = "deepseek-v4-flash"
# 统一走微网关(环境变量可覆盖;网关负责供应商路由与故障切换)
BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8006/v1")
SYSTEM_PROMPT = "你是一个专业的AI助手,能使用工具获取实时信息。回答要简洁、准确。"

# 可用工具列表 —— 以后加知识库/MCP 工具都往这里塞
AVAILABLE_TOOLS = [get_current_time, retrieve_knowledge, query_prometheus_alerts, web_search]


def _create_llm():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 DEEPSEEK_API_KEY")
    return ChatOpenAI(model=MODEL, base_url=BASE_URL, api_key=api_key)


# ---- Agent 单例:整个应用共用一个 Agent + 一份记忆仓库 ----
_agent = None
_checkpointer = MemorySaver()


def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(
            _create_llm(),
            tools=AVAILABLE_TOOLS,
            checkpointer=_checkpointer,
        )
    return _agent


def _build_messages(question: str, image_url: str | None = None, memory_context: str = ""):
    """构造消息:纯文本 or 多模态(text + image_url),可注入向量记忆

    注意:这只是构造 OpenAI 格式的多模态消息;真正调 ollama 时,
    由于 ollama 的 OpenAI 兼容层对 image_url 支持不完整,
    多模态请求会走 ollama 原生 API(_call_ollama_native_multimodal)。
    """
    system_content = SYSTEM_PROMPT
    if memory_context:
        system_content += (
            "\n\n## 相关历史对话记忆(供参考)\n"
            f"{memory_context}\n"
            "(以上是你和用户以前对话的片段,如果相关可以引用,不要编造)"
        )
    user_content = [{"type": "text", "text": question}]
    if image_url:
        user_content.append({"type": "image_url", "image_url": {"url": image_url}})
    return [
        SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ]


def _extract_base64(image_url: str) -> str:
    """从 image_url 中提取纯 base64

    data URL 格式: data:image/png;base64,XXXX  ← 注意是 ;base64, 不是 ,base64,
    """
    if image_url.startswith("data:") and ";base64," in image_url:
        return image_url.split(";base64,", 1)[1]
    return image_url


async def _call_ollama_native_multimodal_stream(question: str, image_url: str):
    """多模态流式:原生 /api/chat + stream"""
    base64_data = _extract_base64(image_url)
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            OLLAMA_NATIVE_URL,
            json={
                "model": OLLAMA_VL_MODEL,
                "messages": [{"role": "user", "content": question, "images": [base64_data]}],
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = line  # ollama 原生是 NDJSON(每行一个 JSON)
                try:
                    import json
                    chunk = json.loads(data)
                    if not chunk.get("done"):
                        yield chunk.get("message", {}).get("content", "")
                except Exception:
                    continue


async def stream_chat(question: str, session_id: str = "default", image_url: str | None = None) -> AsyncGenerator[str, None]:
    """流式对话(可选多模态 + 向量记忆)"""
    # 检索向量记忆(跨会话)
    memory_context = memory_store.recall(question)

    if image_url:
        # 多模态:先看图描述,再走 create_agent(带记忆),一次性 yield
        description = await _call_ollama_native_multimodal(question, image_url, session_id)
        enriched = f"{question}\n\n[图片内容参考]: {description}"
        result = await _get_agent().ainvoke(
            {"messages": _build_messages(enriched, None, memory_context)},
            {"configurable": {"thread_id": session_id}},
        )
        answer = result["messages"][-1].content
        yield answer
        memory_store.save_conversation(session_id, question, answer)
        return

    full_answer = ""
    async for event in _get_agent().astream(
        {"messages": _build_messages(question, None, memory_context)},
        {"configurable": {"thread_id": session_id}},
        stream_mode="messages",
    ):
        token, metadata = event
        if hasattr(token, "content") and token.content:
            full_answer += token.content
            yield token.content

    # 流结束后保存记忆
    memory_store.save_conversation(session_id, question, full_answer)