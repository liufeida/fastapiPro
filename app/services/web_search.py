"""联网搜索工具模块。

基于 Bing HTML 搜索提供免费、无需 API Key 的网页搜索能力，
并通过 LangChain @tool 装饰器暴露为可被 LLM bind_tools 调用的工具。

选择 Bing 而非 DuckDuckGo Lite 的原因：
  - DuckDuckGo Lite 反爬严格，频繁请求会被 IP 限流 (HTTP 202)
  - Bing HTML 端点稳定、无 Key、反爬宽松

代理支持：
  - 优先读取环境变量 SEARCH_PROXY（专用于搜索的代理）
  - 其次读取 HTTPS_PROXY / HTTP_PROXY（通用代理）
  - 未配置则直连
"""

from __future__ import annotations

import os

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

_BING_URL = "https://www.bing.com/search"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _get_proxy() -> str | None:
    return (
        os.getenv("SEARCH_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
        or None
    )


def _parse_bing(html: str, max_results: int) -> list[dict]:
    """解析 Bing HTML 搜索结果，提取标题、链接、摘要。"""
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.find_all("li", class_="b_algo")

    results: list[dict] = []
    for block in blocks[:max_results]:
        title_el = block.find("h2")
        link_el = title_el.find("a") if title_el else None
        snippet_el = (
            block.find("p")
            or block.find("div", class_="b_caption")
            or block.find("p", class_="b_lineclamp2")
        )

        if not link_el:
            continue

        results.append({
            "title": link_el.get_text(strip=True),
            "href": link_el.get("href", ""),
            "body": snippet_el.get_text(strip=True) if snippet_el else "",
        })

    return results


def do_search(query: str, max_results: int = 5) -> str:
    """执行 Bing 文本搜索并格式化返回结果。

    Args:
        query: 搜索关键词。
        max_results: 最大返回条数，默认 5。

    Returns:
        格式化后的搜索结果文本；搜索失败时返回 "搜索失败: {错误信息}"，
        无结果时返回 "未找到相关结果"。
    """
    proxy = _get_proxy()
    try:
        client_kwargs: dict = {"timeout": 15}
        if proxy:
            client_kwargs["proxy"] = proxy
        with httpx.Client(**client_kwargs) as client:
            r = client.get(
                _BING_URL,
                params={"q": query, "setlang": "zh-CN"},
                headers={"User-Agent": _UA},
                follow_redirects=True,
            )
            r.raise_for_status()
    except Exception as exc:
        return f"搜索失败: {exc}"

    results = _parse_bing(r.text, max_results)

    if not results:
        return "未找到相关结果"

    blocks: list[str] = []
    for i, item in enumerate(results, 1):
        blocks.append(
            f"{i}. {item['title']}\n"
            f"   {item['body']}\n"
            f"   链接: {item['href']}"
        )

    return "\n\n".join(blocks)


@tool
def web_search(query: str) -> str:
    """当需要获取实时信息、最新新闻、天气、股价、日期等互联网上的内容时调用此工具。query 为搜索关键词。"""
    return do_search(query)
