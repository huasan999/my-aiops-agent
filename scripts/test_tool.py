import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""测试工具调用完整版 - 里程碑 3"""

import os

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.tools.time_tool import get_current_time

llm = ChatOpenAI(
    model="deepseek-v4-flash",
    base_url="https://api.deepseek.com",
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
)
llm_with_tools = llm.bind_tools([get_current_time])

# 消息历史(会持续追加)
messages = [HumanMessage(content="现在北京时间几点了？")]

# 第一轮:模型提出工具调用申请
response = llm_with_tools.invoke(messages)
print("模型提出调用:", response.tool_calls)

# ---- 关键部分:代码执行工具,把结果还给模型 ----

# 1. 把模型的"调用申请"加入消息历史
messages.append(response)

# 2. 对每个申请,代码真正执行工具,把结果包成 ToolMessage 加回历史
for tc in response.tool_calls:
    result = get_current_time.invoke(tc["args"])   # ← 真正执行函数
    print(f"代码执行了 {tc['name']}, 结果: {result}")
    messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

# 3. 再问一次模型 —— 这次它手上有了真实时间
final = llm_with_tools.invoke(messages)
print("最终回答:", final.content)