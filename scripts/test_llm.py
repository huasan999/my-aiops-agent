import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""测试 LLM 联通性 - 里程碑 2"""

import os
from openai import OpenAI

# 从环境变量读 API Key
api_key = os.environ.get("DEEPSEEK_API_KEY")
if not api_key:
    raise ValueError("请设置环境变量 DEEPSEEK_API_KEY")

# 创建客户端(指向 DeepSeek,OpenAI 兼容)
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)

# 调用模型
response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[
        {"role": "user", "content": "你好，请用一句话介绍你自己"}
    ],
)

# 打印结果
print("=" * 50)
print("LLM 回复:")
print(response.choices[0].message.content)
print("=" * 50)