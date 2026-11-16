"""Shared bounded HTTP transport for the two fixed authenticated MCP consumers."""

from contextlib import asynccontextmanager

import httpx2


@asynccontextmanager
async def authenticated_http(token):
    """Keep bearer credentials on verified TLS requests without redirects or proxy inheritance."""
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + token},
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    ) as http:
        yield http
