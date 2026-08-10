"""网页搜索工具 - 通过 DuckDuckGo HTML 端点搜索(无需 API key,零新依赖)"""

import html as html_lib
import json
import re
import urllib.parse

import httpx
from langchain_core.tools import tool

# DuckDuckGo HTML 搜索端点;免 key,但限流较严,适合轻量使用
SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}


def _extract_real_url(href: str) -> str:
    """DDG 结果链接是 /l/?uddg=<encoded>&rut=... 重定向,解出真实 URL"""
    if "uddg=" in href:
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        if parsed.get("uddg"):
            return urllib.parse.unquote(parsed["uddg"][0])
    return href


def _strip_tags(fragment: str) -> str:
    """去掉 HTML 标签 + 反转义,保留纯文本"""
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return html_lib.unescape(fragment).strip()


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """搜索互联网获取最新信息(新闻、文档、技术方案等)。

    适用场景:用户问实时信息、外部知识、当前热点,或本地知识库查不到的内容时使用。
    返回搜索结果列表(标题、URL、摘要)。无结果或失败时返回错误信息,不要编造。

    Args:
        query: 搜索关键词,尽量具体(如"FastAPI 文件上传 最佳实践 2026")
        max_results: 返回结果条数,1-10,默认 5
    """
    if not query.strip():
        return json.dumps({"success": False, "error": "query 不能为空"}, ensure_ascii=False)
    max_results = max(1, min(int(max_results), 10))

    params = {"q": query, "kl": "cn-zh"}
    try:
        with httpx.Client(timeout=15.0, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
            resp = client.get(SEARCH_ENDPOINT, params=params)
            resp.raise_for_status()
            page = resp.text
    except Exception as e:
        # 网络/连接失败:返回错误信息(让 LLM 如实报告,不编造)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to search the web",
        }, ensure_ascii=False, indent=2)

    # 解析 DDG HTML 结构:result__a(标题+链接)与 result__snippet(摘要)成对出现
    title_matches = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        page,
        re.DOTALL,
    )
    snippet_matches = re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        page,
        re.DOTALL,
    )

    results = []
    for i, (href, title) in enumerate(title_matches[:max_results]):
        results.append({
            "title": _strip_tags(title),
            "url": _extract_real_url(href),
            "snippet": _strip_tags(snippet_matches[i]) if i < len(snippet_matches) else "",
        })

    if not results:
        return json.dumps({
            "success": False,
            "error": "no results",
            "message": "未找到相关结果,可尝试更换关键词",
        }, ensure_ascii=False, indent=2)

    return json.dumps({
        "success": True,
        "query": query,
        "results": results,
        "total": len(results),
    }, ensure_ascii=False, indent=2)
