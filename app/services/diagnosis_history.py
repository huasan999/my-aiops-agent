"""诊断历史存储 - 历史诊断报告归档到 Milvus(独立集合,不参与记忆召回)

与 memory_store 的区别:
- memories 集合:聊天长期记忆,LLM 跨会话召回用,30 天保留
- diagnoses 集合:诊断报告归档,前端历史回放用,不参与 LLM 召回

存储结构(每轮诊断一条):
- page_content = 报告全文(用于 embedding,支持语义检索历史诊断)
- metadata: sid(会话 id)/ title / plan(JSON 步骤计划)/ steps(JSON 已执行步骤)/ ts
"""

import json
import uuid
from datetime import datetime

from langchain_core.documents import Document
from langchain_milvus import Milvus

from app.services.vector_embedding_service import embedding_service

COLLECTION_NAME = "diagnoses"
LIST_LIMIT = 50


class DiagnosisHistory:
    """诊断报告归档:保存 / 列表 / 详情"""

    def __init__(self):
        self.vector_store = None

    # 懒初始化:与 memory_store 同款约定(禁止 import 期建资源)
    def _ensure_store(self):
        if self.vector_store is None:
            self.vector_store = Milvus(
                embedding_function=embedding_service,
                collection_name=COLLECTION_NAME,
                connection_args={"host": "127.0.0.1", "port": "19530"},
                auto_id=False,
                drop_old=False,
                text_field="content",
                vector_field="vector",
                primary_field="id",
                enable_dynamic_field=True,
            )

    def save(self, session_id: str, plan: list, steps: list, report: str,
             title: str = "系统诊断报告"):
        """保存一轮诊断(幂等:同 session 重复诊断会新增一条)"""
        self._ensure_store()
        ts = datetime.now().isoformat()
        doc = Document(
            page_content=report,
            metadata={
                "sid": session_id,
                "title": title,
                "plan": json.dumps(plan, ensure_ascii=False),
                "steps": json.dumps(steps, ensure_ascii=False),
                "ts": ts,
            },
        )
        self.vector_store.add_documents([doc], ids=[str(uuid.uuid4())])

    def list_recent(self, limit: int = LIST_LIMIT) -> list:
        """按时间倒序返回最近诊断摘要列表(不含报告正文,省流量)

        注意:enable_dynamic_field=True 时 metadata 展开为顶层字段,
        query 的 output_fields 直接列字段名,取值用 r.get("sid") 等。
        """
        self._ensure_store()
        try:
            result = self.vector_store.col.query(
                expr='sid != ""',
                output_fields=["sid", "title", "ts"],
                limit=500,
            )
        except Exception as e:
            print(f"[DiagnosisHistory] 查询失败: {e}")
            return []

        items = []
        for r in result:
            items.append({
                "session_id": r.get("sid", ""),
                "title": r.get("title", "系统诊断报告"),
                "ts": r.get("ts", ""),
            })
        items.sort(key=lambda x: x["ts"], reverse=True)
        return items[:limit]

    def get(self, session_id: str) -> dict | None:
        """按会话 id 取完整诊断(plan/steps/report,报告在 content 字段)"""
        self._ensure_store()
        try:
            result = self.vector_store.col.query(
                expr=f'sid == "{session_id}"',
                output_fields=["sid", "title", "plan", "steps", "ts", "content"],
                limit=1,
            )
        except Exception as e:
            print(f"[DiagnosisHistory] 查询失败: {e}")
            return None
        if not result:
            return None

        r = result[0]
        try:
            plan = json.loads(r.get("plan", "[]"))
        except Exception:
            plan = []
        try:
            steps = json.loads(r.get("steps", "[]"))
        except Exception:
            steps = []
        return {
            "session_id": r.get("sid", session_id),
            "title": r.get("title", "系统诊断报告"),
            "plan": plan,
            "steps": steps,
            "report": r.get("content", ""),
            "ts": r.get("ts", ""),
        }


# 全局单例
diagnosis_history = DiagnosisHistory()
