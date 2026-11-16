"""Tool isolation and billing regressions; no paid API requests."""

import asyncio
import base64
import contextlib
import importlib
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import WSMsgType, web

from aiy_gateway_fixture import gateway, provider_events

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))
search_web = importlib.import_module("web_search").search_web
server = importlib.import_module("server")
redact = importlib.import_module("memory_search").redact
search_memory = importlib.import_module("memory_search").search_memory
cost = importlib.import_module("usage_cost").cost


class ToolTests(unittest.IsolatedAsyncioTestCase):
    """Verify tool isolation, bounded invocation and usage accounting."""

    def test_search_includes_cache_writes_and_tool_calls(self):
        """Verify search includes cache writes and tool calls."""
        usage = {
            "input_tokens": 15251,
            "input_tokens_details": {
                "cached_tokens": 0,
                "cache_write_tokens": 4478,
                "cache_write_tokens_details": {"ttl_30m_tokens": 4478},
            },
            "output_tokens": 242,
            "web_search_calls": 2,
        }
        self.assertEqual(cost(usage, "gpt-6-luna"), Decimal("0.02175805"))

    async def test_memory_rejects_invalid_queries_before_connecting(self):
        """Verify memory rejects invalid queries before connecting."""
        self.assertIn("error", await search_memory("x" * 251))
        self.assertIn("error", await search_memory(""))
        self.assertEqual(
            redact("api_key=secret password:secret sk-abcdefghijklmnopqrstuvwxyz"),
            "api_key=[redacted] password=[redacted] [redacted]",
        )

    async def test_function_roundtrip_keeps_device_busy_until_spoken_answer(self):
        """Verify function roundtrip keeps device busy until spoken answer."""
        result_sent = asyncio.Event()
        allow_result = asyncio.Event()

        async def search(*_args):
            """Return a deterministic grounded search result."""
            result_sent.set()
            await allow_result.wait()
            return {"answer": "Fresh sourced fact", "sources": [{"url": "https://example.org"}]}

        async def provider(request):
            """Serve the deterministic provider protocol without external network access."""
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            replies = 0
            async for event in provider_events(ws):
                if event["type"] == "conversation.item.create":
                    self.assertEqual(event["item"]["type"], "function_call_output")
                    self.assertEqual(event["item"]["call_id"], "call1")
                elif event["type"] == "response.create":
                    replies += 1
                    if replies == 1:
                        output = [
                            {
                                "type": "function_call",
                                "name": "search_web",
                                "call_id": "call1",
                                "arguments": '{"query":"Brno weather today"}',
                            }
                        ]
                        await ws.send_json(
                            {
                                "type": "response.done",
                                "response": {
                                    "id": "tool1",
                                    "status": "completed",
                                    "output": output,
                                    "usage": {},
                                },
                            }
                        )
                    else:
                        self.assertEqual(event["response"]["tool_choice"], "auto")
                        await ws.send_json(
                            {
                                "type": "response.output_audio.delta",
                                "delta": base64.b64encode(b"\x01\x02" * 100).decode(),
                            }
                        )
                        await ws.send_json(
                            {
                                "type": "response.done",
                                "response": {
                                    "id": "voice1",
                                    "status": "completed",
                                    "output": [],
                                    "usage": {},
                                },
                            }
                        )
            return ws

        with patch.object(server, "search_web", search):
            async with gateway(server, provider) as (app, device):
                async with device.ws_connect(
                    "/v1/voice", headers={"Authorization": "Bearer " + "x" * 48}
                ) as ws:
                    await ws.receive_json()
                    await ws.send_json({"type": "start"})
                    await ws.send_bytes(b"\x00\x00" * 6000)
                    await ws.send_json({"type": "stop"})
                    await asyncio.wait_for(result_sent.wait(), 2)
                    self.assertTrue(app["busy"].locked())
                    allow_result.set()
                    self.assertEqual((await ws.receive()).type, WSMsgType.BINARY)
                    self.assertEqual((await ws.receive_json())["type"], "done")
                self.assertEqual(len(app["ledger"].rows()), 2)


class HostedWeatherTests(unittest.IsolatedAsyncioTestCase):
    """Keep weather feeds grounded even when they have no URL citations."""

    async def test_weather_widget_without_url_is_still_grounded(self):
        """Verify weather widget without url is still grounded."""
        body = {
            "id": "weather-1",
            "status": "completed",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "output": [
                {
                    "type": "web_search_call",
                    "action": {"type": "search", "queries": ["weather: Czechia, Brno"]},
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Weather observation at 17:00",
                            "annotations": [],
                        }
                    ],
                },
            ],
        }

        @contextlib.asynccontextmanager
        async def response(*_args, **_kwargs):
            """Yield the in-memory provider response without making an HTTP request."""
            yield SimpleNamespace(status=200, json=AsyncMock(return_value=body))

        http = Mock(post=response)
        ledger = unittest.mock.Mock()
        result = await search_web(http, "fake", "Brno weather", ledger)
        self.assertEqual(result["sources"][0]["kind"], "weather_feed")
        self.assertNotIn("url", result["sources"][0])
        ledger.record.assert_called_once()
        # Ordinary web summaries still need citation evidence.
        body["output"][0]["action"]["queries"] = ["ordinary query"]
        result = await search_web(http, "fake", "ordinary query", ledger)
        self.assertIn("error", result)
