"""Bounded MemPalace transport; model never selects MCP names, URLs or namespaces."""

import asyncio
import json
import os
import re

from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_transport import authenticated_http
from prompts import load_prompts


def redact(text):
    """Defense in depth: memory should contain no secrets; redact recognizable values."""
    text = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[redacted]", text)
    text = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
        "[redacted private key]",
        text,
        flags=re.S,
    )
    return re.sub(
        r"(?i)\b(password|passwd|bearer_token|api_key|access_token|refresh_token)"
        r"\s*[:=]\s*[^\s,;]+",
        r"\1=[redacted]",
        text,
    )


async def search_memory(query):
    """Only this fixed server tool is callable; model cannot choose name/URL/wing."""
    if not isinstance(query, str) or not query.strip() or len(query) > 250:
        return {"error": "Invalid memory query"}
    data, own = await asyncio.gather(
        memory_call("mempalace_search", {"query": query, "wing": "codex", "limit": 4}),
        memory_call("mempalace_search", {"query": query, "wing": "aiy_voice", "limit": 4}),
    )
    return {
        "matches": [
            {"text": redact(item.get("text", ""))[:2800],
             "room": item.get("room"), "filed_at": item.get("filed_at")}
            for item in (own.get("results", []) + data.get("results", []))[:8]
        ],
        "notice": load_prompts()["memory_notice"],
    }


async def memory_call(name, arguments):
    """Call a code-selected MCP operation and decode its error envelope safely."""
    token = os.environ.get("MEMPALACE_MCP_HTTP_TOKEN")
    if not token:
        raise RuntimeError("Memory is not configured")
    url = os.environ.get("AIY_MEMORY_URL", "https://mempalace.int.andreybondarenko.com/mcp")
    async with asyncio.timeout(25):
        async with authenticated_http(token) as http:
            async with Client(
                streamable_http_client(url, http_client=http), read_timeout_seconds=20
            ) as memory:
                result = await memory.call_tool(name, arguments)
    if result.is_error:
        raise RuntimeError("Memory unavailable")
    data = result.structured_content
    if not data:
        text = "\n".join(block.text for block in result.content if block.type == "text")
        data = json.loads(text)
    if not isinstance(data, dict) or data.get("error") or data.get("errors"):
        raise RuntimeError("Memory unavailable")
    return data
