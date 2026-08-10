"""Prometheus 告警查询工具 - 通过 HTTP API 拉取当前活动告警"""

import json
import os

import httpx
from langchain_core.tools import tool

# 地址可配置:环境变量 PROMETHEUS_BASE_URL 优先,默认 9090
PROMETHEUS_BASE_URL = os.environ.get("PROMETHEUS_BASE_URL", "http://127.0.0.1:9090").rstrip("/")
ALERTS_API_PATH = "/api/v1/alerts"


@tool
def query_prometheus_alerts() -> str:
    """查询 Prometheus 服务端当前活动告警。

    适用场景:用户问"有没有告警"、"哪些告警在触发"、"排查监控告警"等运维问题。
    无需参数,直接调用即可获取告警列表(名称、级别、状态、触发时间等)。

    Returns:
        str: JSON 字符串,含 success、alerts、state_counts 等字段
    """
    api_url = f"{PROMETHEUS_BASE_URL}{ALERTS_API_PATH}"

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(api_url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        # 网络/连接失败:返回错误信息(让 LLM 如实报告,不编造)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to query Prometheus alerts",
        }, ensure_ascii=False, indent=2)

    if data.get("status") != "success":
        return json.dumps({
            "success": False,
            "error": data.get("error", "unknown"),
            "message": "Prometheus returned non-success status",
        }, ensure_ascii=False, indent=2)

    # 简化告警列表(每条的 labels 是唯一标识,不用 alertname 去重)
    alerts = data.get("data", {}).get("alerts", [])
    simplified = []
    for alert in alerts:
        labels = alert.get("labels", {})
        simplified.append({
            "alert_name": labels.get("alertname", ""),
            "severity": labels.get("severity", ""),
            "state": alert.get("state", ""),
            "active_at": alert.get("activeAt", ""),
            "description": alert.get("annotations", {}).get("description", ""),
        })

    return json.dumps({
        "success": True,
        "alerts": simplified,
        "total": len(simplified),
        "message": f"获取到 {len(simplified)} 条告警",
    }, ensure_ascii=False, indent=2)