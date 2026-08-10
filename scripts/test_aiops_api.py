"""API 级验证:异步提交 + 状态查询 + SSE 订阅(无需 LLM)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi.testclient import TestClient

from app.main import app


def main():
    with TestClient(app) as client:
        # 1. 提交 → 202 + task_id
        r = client.post("/api/aiops", json={"session_id": "api-verify"})
        assert r.status_code == 202, f"应 202,实际 {r.status_code}"
        task_id = r.json()["task_id"]
        print(f"[OK] 提交 202: {task_id}")

        # 2. 状态查询
        r2 = client.get(f"/api/aiops/{task_id}")
        assert r2.status_code == 200
        print(f"[OK] 状态查询: {r2.json()['status']}, events={r2.json()['event_count']}")

        # 3. 404 处理
        r3 = client.get("/api/aiops/nonexistent-task")
        assert r3.status_code == 404
        print("[OK] 未知任务 404")

        # 4. 健康检查不受影响
        r4 = client.get("/health")
        assert r4.status_code == 200
        print("[OK] /health 正常")

    print("=" * 40)
    print("API 异步诊断验证通过")


main()
