"""联网搜索工具模块。

基于 DuckDuckGo Lite (HTML 版本) 提供免费、无需 API Key 的网页搜索能力，
并通过 LangChain @tool 装饰器暴露为可被 DeepSeek bind_tools 调用的工具。

代理支持：
  - 优先读取环境变量 SEARCH_PROXY（专用于搜索的代理）
  - 其次读取 HTTPS_PROXY / HTTP_PROXY（通用代理）
  - 未配置则直连
"""

import os
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

# DuckDuckGo Lite 搜索端点（HTML 版本，反爬虫较弱）
_LITE_URL = "https://lite.duckduckgo.com/lite/"
# 默认 User-Agent，避免被识别为爬虫
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _get_proxy() -> str | None:
    """从环境变量读取代理地址。"""
    return (
        os.getenv("SEARCH_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
        or None
    )


def _parse_results(html: str, max_results: int) -> list[dict]:
    """解析 DuckDuckGo Lite 的 HTML，提取标题、链接、摘要。"""
    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("a", class_="result-link")
    snippets = soup.find_all("td", class_="result-snippet")

    results: list[dict] = []
    for link, snippet in zip(links, snippets):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        # 解码真实 URL: //duckduckgo.com/l/?uddg=https%3A%2F%2F...
        if "uddg=" in href:
            parsed = parse_qs(urlparse(href).query)
            real_url = unquote(parsed.get("uddg", [""])[0])
        else:
            real_url = href
        body = snippet.get_text(strip=True)
        results.append({"title": title, "href": real_url, "body": body})
        if len(results) >= max_results:
            break
    return results


def do_search(query: str, max_results: int = 5) -> str:
    """执行 DuckDuckGo 文本搜索并格式化返回结果。

    Args:
        query: 搜索关键词。
        max_results: 最大返回条数，默认 5。

    Returns:
        格式化后的搜索结果文本；搜索失败时返回 "搜索失败: {错误信息}"，
        无结果时返回 "未找到相关结果"。
    """
    proxy = _get_proxy()
    try:
        with httpx.Client(proxy=proxy, timeout=15) as client:
            r = client.get(
                _LITE_URL,
                params={"q": query, "kl": "us-en"},
                headers={"User-Agent": _UA},
            )
            r.raise_for_status()
    except Exception as exc:
        return f"搜索失败: {exc}"

    results = _parse_results(r.text, max_results)

    if not results:
        return "未找到相关结果"

    formatted_blocks: list[str] = []
    for index, item in enumerate(results, start=1):
        title = item.get("title", "")
        body = item.get("body", "")
        href = item.get("href", "")
        formatted_blocks.append(
            f"{index}. {title}\n"
            f"   {body}\n"
            f"   链接: {href}"
        )

    return "\n\n".join(formatted_blocks)


@tool
def web_search(query: str) -> str:
    """当需要获取实时信息、最新新闻、天气、股价等互联网上的内容时调用此工具。query 为搜索关键词。"""
    return do_search(query)
