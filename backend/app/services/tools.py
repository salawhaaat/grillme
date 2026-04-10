import re
from urllib.parse import quote_plus

import httpx

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for information about a company, role, or interview topic",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"]
        }
    }
}

TITLE_PATTERN = re.compile(r'<a[^>]*class="[^"]*\bresult__a\b[^"]*"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
SNIPPET_PATTERN = re.compile(r'<a[^>]*class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", TAG_PATTERN.sub("", text)).strip()


async def execute_web_search(query: str) -> str:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=15)
            response.raise_for_status()

        titles = [_strip_html(m) for m in TITLE_PATTERN.findall(response.text)]
        snippets = [_strip_html(m) for m in SNIPPET_PATTERN.findall(response.text)]
        count = min(3, len(titles), len(snippets))
        if count == 0:
            return "No results found."

        lines = []
        for i in range(count):
            lines.append(f"{i + 1}. {titles[i]} — {snippets[i]}")
        return "\n".join(lines)
    except httpx.TimeoutException:
        return "Web search failed: timeout."
    except Exception as e:
        return f"Web search failed: {e}"


TOOL_REGISTRY: dict[str, callable] = {"web_search": execute_web_search}
ALL_TOOLS = [WEB_SEARCH_TOOL]
