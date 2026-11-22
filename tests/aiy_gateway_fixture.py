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


def prompt_environment():
    """Use a clearly synthetic prompt bundle; production has no built-in fallback."""
    return patch.dict(os.environ, {
        "AIY_PROMPTS_FILE": str(Path(__file__).with_name("fixtures") / "aiy-prompts.json")
    })


@asynccontextmanager
async def gateway(backend, provider, *, memory=False):
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
            if not memory:
                # Protocol fixtures isolate voice/tool streaming from memory generation;
                # dedicated memory integration tests enable the real path explicitly.
                bridge_type = backend.VoiceBridge
                def isolate(app_arg, device_arg):
                    bridge = bridge_type(app_arg, device_arg)
                    bridge.memory = None
                    return bridge
            else:
                isolate = backend.VoiceBridge
            with patch.object(backend, "VoiceBridge", isolate):
                async with TestClient(TestServer(app)) as device:
                    await app["http"].close()
                    app["http"] = redirect
                    yield app, device


async def provider_events(ws, *, updates=None):
    """Acknowledge setup and yield remaining JSON events for tool-response fixtures."""
    async for message in ws:
        event = json.loads(message.data)
        if event["type"] == "session.update":
            if updates is not None:
                updates.append(event["session"]["instructions"])
            await ws.send_json({"type": "session.updated"})
        else:
            yield event
