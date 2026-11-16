"""Home Assistant Assist MCP bridge: exposed entities, no administrative API tools."""

import asyncio
import json
import os
from pathlib import Path

from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_transport import authenticated_http

URL = "https://ha.andreybondarenko.com/api/mcp/assist"
CATALOG = json.loads(
    Path(__file__).with_name("homeassistant_tools.json").read_text(encoding="utf-8")
)
NAMES = {"ha_" + item["name"]: item["name"] for item in CATALOG}


def schemas():
    """Use the inspected Assist schema snapshot, never auto-expose future admin tools."""
    return [
        {
            "type": "function",
            "name": "ha_" + item["name"],
            "description": item["description"],
            "parameters": item["schema"],
        }
        for item in CATALOG
    ]


async def call_home_assistant(name, arguments):
    """Call only the fixed Assist endpoint and allowlisted native MCP tools."""
    if name not in NAMES or not isinstance(arguments, dict):
        return {"error": "Unsupported Home Assistant operation"}
    token = os.environ.get("HOME_ASSISTANT_TOKEN")
    if not token:
        return {"error": "Home Assistant is not configured"}
    try:
        async with asyncio.timeout(25):
            async with authenticated_http(token) as http:
                async with Client(
                    streamable_http_client(URL, http_client=http), read_timeout_seconds=20
                ) as ha:
                    result = await ha.call_tool(NAMES[name], arguments)
        if result.is_error:
            return {
                "error": "Home Assistant rejected the request",
                "details": "\n".join(
                    block.text for block in result.content if block.type == "text"
                )[:3000],
            }
        return {
            "result": (
                result.structured_content
                or "\n".join(block.text for block in result.content if block.type == "text")[:20000]
            )
        }
    except Exception:  # pylint: disable=broad-exception-caught
        # SDK exceptions can include request metadata; never expose them to model/logs.
        return {"error": "Home Assistant unavailable; do not claim success"}
