"""Langfuse 可观测性接入(懒初始化)

约定:
- 未配置 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 时静默禁用,不阻塞业务
- 禁止在模块 import 期创建 Langfuse 客户端(与全项目懒初始化约定一致)
- 所有 LangGraph/LLM 调用通过 get_callbacks() 注入,一次请求一条 trace
"""

import os


def _langfuse_enabled() -> bool:
    """是否已配置 Langfuse 凭据"""
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
        and os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    )


def get_callbacks():
    """返回注入 graph/agent 的 callbacks 列表(懒创建,未配置则空列表)

    用法:
        config = {"configurable": {...}, "callbacks": get_callbacks()}
    """
    if not _langfuse_enabled():
        return []

def get_callbacks():
    """返回注入 graph/agent 的 callbacks 列表(懒创建,未配置则空列表)

    用法:
        config = {"configurable": {...}, "callbacks": get_callbacks()}
    """
    if not _langfuse_enabled():
        return []

    try:
        # 关键:CallbackHandler() 不带任何参数 —— SDK 从环境变量
        # (LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST)初始化单例 client。
        # 显式传 public_key 会让 get_client() 在 active_instances 里
        # 找不到该 key 的实例而返回 disabled client(数据静默丢失)。
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler()
        return [handler]
    except Exception as e:
        print(f"[Tracing] Langfuse 初始化失败,本次调用禁用追踪: {e}")
        return []
