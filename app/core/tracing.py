"""LangSmith 可观测性接入(LangChain 自动追踪)

LangSmith 与 Langfuse 不同:不需要手动注入 CallbackHandler。
设置以下环境变量后,LangChain/LangGraph 在首次 LLM 调用时自动初始化
tracer,所有 agent/graph 调用自动上报 trace,零代码改动:

    LANGSMITH_TRACING=true
    LANGSMITH_API_KEY=lsv2_...        # 在 https://smith.langchain.com 生成
    LANGSMITH_PROJECT=my-aiops-agent  # 可选,默认取项目名

约定:
- 未配置 LANGSMITH_API_KEY 时追踪自动禁用,不阻塞业务
- 无 import 期副作用(与全项目懒初始化约定一致)
"""


def get_callbacks():
    """返回注入 graph/agent 的 callbacks 列表(兼容旧调用点)。

    LangSmith 走环境变量自动集成,无需手动回调,恒返回空列表。
    若未来换回需要手动注入的追踪方案(如 Langfuse),在此实现即可。
    """
    return []
