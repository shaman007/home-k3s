"""Durable appliance timers, bounded commands, and acknowledgements."""

import importlib
import base64
from aiohttp import web, WSMsgType

from aiy_gateway_fixture import gateway, provider_events

import asyncio
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))
server = importlib.import_module("server")
Volume = importlib.import_module("local_resources").Volume
TimerStore = importlib.import_module("local_resources").TimerStore
LocalResources = importlib.import_module("local_resources").LocalResources
alarm_pcm = importlib.import_module("local_resources").alarm_pcm
DeviceTools = importlib.import_module("device_tools").DeviceTools


class TimerTests(unittest.IsolatedAsyncioTestCase):
    """Verify persistent timer deadlines, offline alarms and operation limits."""

    def test_deadline_survives_restart_and_duplicate_command(self):
        """Verify deadline survives restart and duplicate command."""
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "timers.sqlite3")
            store = TimerStore(path)
            first = store.create("one", 10, "tea", now=100)
            duplicate = store.create("one", 10, "tea", now=200)
            self.assertEqual(first["due"], duplicate["due"])
            store.db.close()
            store = TimerStore(path)
            self.assertEqual(store.active()[0]["due"], 110)
            self.assertEqual(store.active()[0]["remaining_seconds"], 0)
            store.set_state("one", "cancelled")
            self.assertEqual(store.active(), [])
            store.db.close()

    async def test_overdue_timer_rings_without_any_network_connection(self):
        """Verify overdue timer rings without any network connection."""
        with tempfile.TemporaryDirectory() as directory:
            ring = AsyncMock()
            resources = LocalResources(str(Path(directory) / "timers.sqlite3"), Mock(), ring)
            resources.timers.create("offline", 1, "test", now=0)
            task = asyncio.create_task(resources.scheduler())
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            ring.assert_awaited_once()
            self.assertEqual(resources.timers.list_all()[0]["state"], "done")
            await resources.close()

    async def test_only_allowlisted_resources_are_exposed(self):
        """Verify only allowlisted resources are exposed."""
        with tempfile.TemporaryDirectory() as directory:
            resources = LocalResources(str(Path(directory) / "timers.sqlite3"), Mock(), AsyncMock())
            for event in [
                {"action": "shell", "command": "id"},
                {"action": "blink", "color": "red", "seconds": 1000},
                {"action": "set_timer", "id": "bad", "seconds": True},
            ]:
                with self.assertRaises(ValueError):
                    await resources.command(event)
            self.assertTrue(alarm_pcm())
            await resources.close()

    async def test_device_success_requires_acknowledgement(self):
        """Verify device success requires acknowledgement."""
        ws = AsyncMock()
        db = sqlite3.connect(":memory:")
        tools = DeviceTools(ws, db)
        task = asyncio.create_task(tools.call("set_timer", {"seconds": 10, "label": "test"}))
        await asyncio.sleep(0)
        event = ws.send_json.call_args.args[0]
        self.assertFalse(task.done())
        tools.acknowledge({"id": event["id"], "result": {"ok": True, "due": 10}})
        self.assertTrue((await task)["ok"])
        self.assertEqual(db.execute("SELECT count(*) FROM device_commands").fetchone()[0], 1)
        self.assertIn("error", await tools.call("shell", {}))
        db.close()


class DeviceBridgeTests(unittest.IsolatedAsyncioTestCase):
    """Verify gateway commands require appliance acknowledgements."""

    async def test_command_ack_roundtrip_through_gateway(self):
        """Verify command ack roundtrip through gateway."""

        async def provider(request):
            """Serve the deterministic provider protocol without external network access."""
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            count = 0
            async for event in provider_events(ws):
                if event["type"] == "conversation.item.create":
                    self.assertEqual(json.loads(event["item"]["output"]), {"ok": True})
                elif event["type"] == "response.create":
                    count += 1
                    if count == 1:
                        output = [
                            {
                                "type": "function_call",
                                "name": "blink_light",
                                "call_id": "gpio1",
                                "arguments": '{"color":"blue","seconds":2}',
                            }
                        ]
                        await ws.send_json(
                            {
                                "type": "response.done",
                                "response": {
                                    "id": "gpio-tool",
                                    "status": "completed",
                                    "output": output,
                                    "usage": {},
                                },
                            }
                        )
                    else:
                        await ws.send_json(
                            {
                                "type": "response.output_audio.delta",
                                "delta": base64.b64encode(b"\0\0" * 100).decode(),
                            }
                        )
                        await ws.send_json(
                            {
                                "type": "response.done",
                                "response": {
                                    "id": "gpio-voice",
                                    "status": "completed",
                                    "output": [],
                                    "usage": {},
                                },
                            }
                        )
            return ws

        async with gateway(server, provider) as (app, client):
            async with client.ws_connect(
                "/v1/voice", headers={"Authorization": "Bearer " + "x" * 48}
            ) as ws:
                await ws.receive_json()
                await ws.send_json({"type": "start"})
                await ws.send_bytes(b"\0\0" * 6000)
                await ws.send_json({"type": "stop"})
                command = await asyncio.wait_for(ws.receive_json(), 2)
                self.assertEqual(command["action"], "blink")
                self.assertEqual(command["color"], "blue")
                await ws.send_json(
                    {"type": "device_ack", "id": command["id"], "result": {"ok": True}}
                )
                self.assertEqual((await ws.receive()).type, WSMsgType.BINARY)
                self.assertEqual((await ws.receive_json())["type"], "done")
            self.assertEqual(
                app["ledger"].db.execute("SELECT count(*) FROM device_commands").fetchone()[0],
                1,
            )


class VolumeTests(unittest.IsolatedAsyncioTestCase):
    """Verify mixer bounds and durable volume preferences."""

    async def test_volume_is_bounded_relative_and_persistent(self):
        """Verify volume is bounded relative and persistent."""
        db = sqlite3.connect(":memory:")
        volume = Volume(db)
        volume.mixer = AsyncMock(
            side_effect=[
                "",
                "Playback 16 [41%] [on]",
                "Playback 16 [41%] [on]",
                "",
                "Playback 12 [31%] [on]",
            ]
        )
        self.assertEqual((await volume.set(40))["volume_percent"], 41)
        self.assertEqual((await volume.adjust(-10))["volume_percent"], 31)
        self.assertEqual(
            db.execute('SELECT value FROM preferences WHERE name="volume"').fetchone()[0], 31
        )
        for invalid in [-1, 101, True, "40"]:
            with self.assertRaises(ValueError):
                await volume.set(invalid)
        db.close()
