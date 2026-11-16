"""Isolated authenticated AIY gateway connected exclusively to a local provider."""

import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer


@asynccontextmanager
async def gateway(backend, provider):
    """Run a fake provider and gateway with disposable usage state and credentials."""
    fake = web.Application()
    fake.router.add_get("/realtime", provider)
    async with TestServer(fake) as upstream, ClientSession() as transport:

        def connect(_url, **kwargs):
            return transport.ws_connect(upstream.make_url("/realtime"), **kwargs)

        redirect = SimpleNamespace(ws_connect=connect, close=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OPENAI_API_KEY": "fake", "AIY_BEARER_TOKEN": "x" * 48}
        ):
            app = backend.create_app(str(Path(directory) / "usage.sqlite3"))
            async with TestClient(TestServer(app)) as device:
                await app["http"].close()
                app["http"] = redirect
                yield app, device


async def provider_events(ws):
    """Acknowledge setup and yield remaining JSON events for tool-response fixtures."""
    async for message in ws:
        event = json.loads(message.data)
        if event["type"] == "session.update":
            await ws.send_json({"type": "session.updated"})
        else:
            yield event
