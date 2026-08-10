"""LLM 微网关 - 统一模型入口  Agent 只需把 base_url 指向 http://localhost:8006/v1,网关负责转发。
"""
import os
from pathlib import Path

# 加载 .env(若有):DEEPSEEK_API_KEY 等从 .env 读取
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="LLM Gateway")

PROVIDERS = [
    {
        "name": "deepseek",
        "base_url": "https://api.deepseek.com",
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "model": "deepseek-v4-flash",
    },
    {
        "name": "ollama-qwen-vl",
        "base_url": "http://127.0.0.1:11434/v1",   # Ollama 的 OpenAI 兼容端点
        "api_key": "ollama",                        # 本地不需要 key
        "model": "qwen2.5vl:7b",                    # 多模态:既能看图也能纯文本,做 fallback
    },
]


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    last_error = None

    for provider in PROVIDERS:
        try:
            # 构造转发请求:替换 model 为当前供应商的模型名
            forward_body = {**body, "model": provider["model"]}
            headers = {
                "Authorization": f"Bearer {provider['api_key']}",
                "Content-Type": "application/json",
            }
            url = f"{provider['base_url']}/chat/completions"

            # 流式请求:边收边转
            if body.get("stream"):
                async with httpx.AsyncClient(timeout=300) as client:
                    upstream = await client.post(url, json=forward_body, headers=headers)
                    upstream.raise_for_status()
                    return StreamingResponse(
                        upstream.aiter_bytes(),
                        media_type="text/event-stream",
                    )

            # 非流式:直接透传 JSON
            async with httpx.AsyncClient(timeout=120) as client:
                upstream = await client.post(url, json=forward_body, headers=headers)
                upstream.raise_for_status()
                return JSONResponse(content=upstream.json())

        except Exception as e:
            last_error = e
            print(f"[Gateway] 供应商 {provider['name']} 失败: {e},尝试下一个...")

    return JSONResponse(
        status_code=502,
        content={"error": f"所有供应商均失败: {last_error}"},
    )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8006)
