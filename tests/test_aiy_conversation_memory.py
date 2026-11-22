"""Memory persistence, safe retries, corrections and silent Realtime checkpoints."""

import asyncio
import importlib
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiohttp import web

from aiy_gateway_fixture import gateway, prompt_environment, provider_events

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))
memory_module = importlib.import_module("conversation_memory")
server = importlib.import_module("server")


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    """Use a realistic in-memory MCP store, never production or paid API requests."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.memory = memory_module.ConversationMemory(self.db)
        self.drawers = {}
        self.calls = []

        async def mcp(name, args):
            self.calls.append((name, args))
            if name == "mempalace_search":
                return {"results": [{"drawer_id": key} for key, row in self.drawers.items()
                                    if row["source_file"] == args["source_file"]]}
            if name == "mempalace_add_drawer":
                drawer_id = str(len(self.drawers) + 1)
                self.drawers[drawer_id] = dict(args, drawer_id=drawer_id)
                return {"success": True, "drawer_id": drawer_id}
            if name == "mempalace_update_drawer":
                self.drawers[args["drawer_id"]]["content"] = args["content"]
                return {"success": True}
            if name == "mempalace_list_drawers":
                return {"drawers": [row for row in self.drawers.values()
                                    if row["room"] == args["room"]]}
            if name == "mempalace_get_drawers":
                return {"results": [self.drawers[key] for key in args["drawer_ids"]]}
            raise AssertionError(name)

        self.mcp = AsyncMock(side_effect=mcp)
        self.enterContext(patch.object(memory_module, "memory_call", self.mcp))

    async def test_fact_correction_reuses_only_owned_drawer(self):
        """A stable fact key supersedes the previous value instead of creating conflicts."""
        for content in ("Assistant is called Alice", "Assistant is called Bob"):
            result = await self.memory.remember("assistant_name", content)
            self.assertEqual(result, {"saved": True, "pending": False})
        self.assertEqual(len(self.drawers), 1)
        self.assertEqual(self.drawers["1"]["content"], "Assistant is called Bob")
        for name, args in self.calls:
            if name != "mempalace_update_drawer":
                self.assertEqual(args.get("wing", "aiy_voice"), "aiy_voice")
        restored = json.loads(await self.memory.restore())
        self.assertEqual(restored["memories"][0]["content"], "Assistant is called Bob")

    async def test_lost_write_reply_does_not_duplicate_on_retry(self):
        """A committed write with a lost response remains safely retryable."""
        real_call = self.mcp.side_effect
        async def lost_reply(name, args):
            result = await real_call(name, args)
            if name == "mempalace_add_drawer":
                raise TimeoutError("must never appear in logs")
            return result
        self.mcp.side_effect = lost_reply
        with self.assertLogs("aiy.memory", level="WARNING") as logs:
            result = await self.memory.remember("preference", "A lasting preference")
        self.assertFalse(result["saved"])
        self.assertNotIn("must never appear", str(logs.output))
        self.mcp.side_effect = real_call
        await self.memory.flush()
        self.assertEqual(len(self.drawers), 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM memory_outbox").fetchone()[0], 0)

    async def test_restart_restores_retry_queue_and_offline_context(self):
        """Pending memory survives a process restart while the MCP server is offline."""
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "memory.sqlite3")
            db = sqlite3.connect(path)
            memory_module.ConversationMemory(db).queue("latest_context", "continuity", "Topic")
            db.close()
            reopened = sqlite3.connect(path)
            self.addCleanup(reopened.close)
            memory = memory_module.ConversationMemory(reopened)
            self.mcp.side_effect = RuntimeError("private-marker")
            with self.assertLogs("aiy.memory", level="WARNING"):
                data = json.loads(await memory.restore())
            self.assertEqual(data["local"][0]["content"], "Topic")
            count = reopened.execute("SELECT COUNT(*) FROM memory_outbox").fetchone()[0]
            self.assertEqual(count, 1)

    async def test_secret_invalid_content_and_reserved_keys_never_reach_mcp(self):
        """Reject malformed or recognizable secret-bearing content before storage."""
        for key, content in (("latest_context", "x"), ("../other", "x"),
                             ("x", "api_key=private-value"), ("x", ""),
                             ("x", "a" * 2001)):
            self.assertIn("error", await self.memory.remember(key, content))
        self.mcp.assert_not_awaited()

    async def test_background_summary_queues_context_without_speaking_or_recursion(self):
        """Account for the silent response and archive it without another voice response."""
        self.enterContext(prompt_environment())
        ledger = server.Ledger(":memory:")
        self.addCleanup(ledger.db.close)
        bridge = server.VoiceBridge({"ledger": ledger, "memory": self.memory}, AsyncMock())
        upstream = AsyncMock()
        await bridge._response_done(upstream, {  # pylint: disable=protected-access
            "id": "spoken", "status": "completed", "output": [], "usage": {},
        })
        request = upstream.send_json.await_args.args[0]["response"]
        self.assertEqual(request["conversation"], "none")
        self.assertEqual(request["output_modalities"], ["text"])
        self.assertEqual(request["tools"], [])
        upstream.reset_mock()
        bridge.device.reset_mock()
        await bridge._response_done(upstream, {  # pylint: disable=protected-access
            "id": "summary", "metadata": {"purpose": "memory_context"},
            "status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "A compact conversation context"}]}],
            "usage": {"output_tokens": 12},
        })
        upstream.send_json.assert_not_awaited()
        bridge.device.send_json.assert_not_awaited()
        self.assertFalse(bridge.summary_pending)
        await self.memory.flush()
        self.assertEqual({row["room"] for row in self.drawers.values()},
                         {"conversations", "continuity"})
        self.assertEqual(len(ledger.rows()), 2)

    async def test_reconnect_restores_real_gateway_memory_and_keeps_audio_protocol(self):
        """Exercise provider events, queue/MCP writes and a fresh connected session."""
        self.enterContext(prompt_environment())
        await self.memory.remember("assistant_name", "The assistant is Alice")
        instructions = []
        async def provider(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for event in provider_events(ws, updates=instructions):
                if event["type"] == "response.create":
                    summary = (event.get("response", {}).get("metadata") or {})
                    await ws.send_json({"type": "response.done", "response": {
                        "id": "summary" if summary else "spoken", "status": "completed",
                        "metadata": summary, "usage": {},
                        "output": [{"type": "message", "content": [{
                            "type": "output_text", "text": "We discussed a blue bicycle",
                        }]}] if summary else [],
                    }})
            return ws

        async with gateway(server, provider, memory=True) as (app, device):
            headers = {"Authorization": "Bearer " + "x" * 48}
            async with device.ws_connect("/v1/voice", headers=headers) as ws:
                self.assertEqual((await ws.receive_json())["type"], "ready")
                await ws.send_json({"type": "start"})
                await ws.send_bytes(b"\x00\x00" * 6000)
                await ws.send_json({"type": "stop"})
                self.assertEqual((await ws.receive_json())["type"], "done")
                for _ in range(50):
                    if app["ledger"].db.execute(
                            "SELECT 1 FROM memory_cache WHERE room='continuity'").fetchone():
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("Silent summary did not reach the durable queue")
                await app["memory"].flush()
            for _ in range(50):
                if not app["busy"].locked():
                    break
                await asyncio.sleep(0.01)
            async with device.ws_connect("/v1/voice", headers=headers) as ws:
                self.assertEqual((await ws.receive_json())["type"], "ready")
                self.assertIn("blue bicycle", instructions[-1])
                self.assertIn("Alice", instructions[-1])


class PromptUpgradeTests(unittest.TestCase):
    """Prepare additive secret migrations without changing the active prompt bundle."""

    def test_separate_bundle_preserves_original_and_matches_runtime_contract(self):
        """Validate operator-supplied synthetic text without production secret access."""
        spec = importlib.util.spec_from_file_location(
            "memory_prompt_upgrade", Path(__file__).resolve().parents[1]
            / "tools/aiy/memory_prompt_upgrade.py")
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with prompt_environment():
            bundle = server.load_prompts()
            # Recreate the pre-memory catalog and fields.
            del bundle["tools"]["remember_memory"]
            del bundle["memory_summary"]
            del bundle["memory_context_prefix"]
            previous = json.loads(json.dumps(bundle))
            updated = migration.upgrade(
                bundle, voice_memory="Synthetic policy", memory_summary="Synthetic summary",
                memory_context_prefix="Synthetic data prefix",
                remember_description="Synthetic tool",
                key_description="Synthetic key", content_description="Synthetic content")
            self.assertEqual(bundle, previous)
            config = server.session_config(updated)
            self.assertIn("remember_memory", {t["name"] for t in config["session"]["tools"]})
