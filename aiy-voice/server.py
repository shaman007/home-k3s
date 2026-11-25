"""Authenticated PCM streaming bridge to OpenAI Realtime; no audio/transcript logs."""

import asyncio
import base64
import hmac
import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientSession, ClientTimeout, WSMsgType, web
from conversation_memory import TOOLS as MEMORY_TOOLS
from conversation_memory import ConversationMemory
from device_tools import ACTIONS, TOOLS, DeviceTools
from home_assistant import NAMES as HA_NAMES
from home_assistant import call_home_assistant
from home_assistant import schemas as ha_schemas
from memory_search import search_memory
from opus_audio import OpusEncoder
from prompts import describe_tools, load_prompts
from reminder_speech import synthesize as synthesize_reminder
from web_search import search_web

LOG = logging.getLogger("aiy")
RATE = 24000
MODEL = os.environ.get("AIY_MODEL", "gpt-realtime-2.1")


def session_config(bundle=None):
    """Explicit push-to-talk session; no automatic microphone-triggered responses."""
    bundle = load_prompts() if bundle is None else bundle
    config = {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": MODEL,
            "output_modalities": ["audio"],
            "instructions": (
                bundle["voice"]
                + bundle["session_time_prefix"]
                + datetime.now(ZoneInfo("Europe/Prague")).isoformat(timespec="minutes")
            ),
            "max_output_tokens": 2048,
            "tools": [
                {
                    "type": "function",
                    "name": "search_memory",
                    "description": "",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "",
                            }
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
                {
                    "type": "function",
                    "name": "search_web",
                    "description": "",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": (
                                    ""
                                ),
                            }
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "audio": {
                "input": {"format": {"type": "audio/pcm", "rate": RATE}, "turn_detection": None},
                "output": {"format": {"type": "audio/pcm", "rate": RATE}, "voice": "marin"},
            },
        },
    }
    config["session"]["tools"].extend(TOOLS)
    config["session"]["tools"].extend(MEMORY_TOOLS)
    config["session"]["tools"].extend(ha_schemas())
    config["session"]["tools"] = describe_tools(config["session"]["tools"], bundle)
    return config


def reminder_context(items, bundle=None):
    """Bounded live appliance facts override stale conversation history each turn."""
    if not isinstance(items, list) or len(items) > 16:
        raise ValueError("Invalid reminder snapshot")
    facts = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("acknowledged_today"), bool):
            raise ValueError("Invalid reminder state")
        row = {}
        for key, limit in (("id", 100), ("text", 120), ("confirmation_phrase", 100)):
            value = item.get(key)
            if not isinstance(value, str) or not 1 <= len(value) <= limit:
                raise ValueError("Invalid reminder metadata")
            row[key] = value
        row["acknowledged_today"] = item["acknowledged_today"]
        days = item.get("weekdays", list(range(7)))
        if (
            not isinstance(days, list)
            or not days
            or len(days) > 7
            or any((not isinstance(x, int) or isinstance(x, bool)) or not 0 <= x <= 6 for x in days)
        ):
            raise ValueError("Invalid reminder weekdays")
        scheduled = item.get("scheduled_today", True)
        if not isinstance(scheduled, bool):
            raise ValueError("Invalid reminder occurrence")
        row["weekdays"] = days
        row["scheduled_today"] = scheduled
        paused_until = item.get("paused_until")
        if paused_until is not None:
            if not isinstance(paused_until, str):
                raise ValueError("Invalid reminder suspension date")
            date.fromisoformat(paused_until)
            row["paused_until"] = paused_until
        facts.append(row)
    bundle = load_prompts() if bundle is None else bundle
    return (
        bundle["live_reminder_prefix"]
        + datetime.now(ZoneInfo("Europe/Prague")).isoformat(timespec="seconds")
        + bundle["task_data_prefix"]
        + json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    )


class Ledger:
    """Durable provider-reported token usage, without conversation contents."""

    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS usage (response_id TEXT PRIMARY KEY, timestamp REAL, model"
            " TEXT, status TEXT, first_audio_ms REAL, usage TEXT)"
        )
        self.db.commit()

    def record(self, response, latency, model=MODEL):
        """Persist provider response metadata and usage statistics to the database."""
        self.db.execute(
            "INSERT OR IGNORE INTO usage VALUES (?, ?, ?, ?, ?, ?)",
            (
                response["id"],
                time.time(),
                model,
                response.get("status"),
                latency,
                json.dumps(response.get("usage") or {}),
            ),
        )
        self.db.commit()

    def rows(self):
        """Retrieve all recorded usage entries from the database."""
        return [
            {
                "response_id": row[0],
                "timestamp": row[1],
                "model": row[2],
                "status": row[3],
                "first_audio_ms": row[4],
                "usage": json.loads(row[5]),
            }
            for row in self.db.execute("SELECT * FROM usage ORDER BY timestamp")
        ]


@dataclass
class TurnState:
    """Track capture and response progress for one connected appliance."""

    started: float = 0.0
    latency: float | None = None
    recording: bool = False
    count: int = 0
    responding: bool = False
    tool_rounds: int = 0
    tool_calls: int = 0


class VoiceBridge:
    """Keep device and provider events within the authenticated session lifetime."""

    # The connection owns independent provider, device, timing and memory state.
    # pylint: disable=too-many-instance-attributes

    def __init__(self, app, device):
        self.app = app
        self.device = device
        self.reminder_snapshot = None
        self.state = TurnState()
        self.initial_config = None
        self.codec = None
        self.memory = app.get("memory")
        self.memory_context = ""
        self.memory_session = uuid.uuid4().hex
        self.summary_pending = False
        self.summary_dirty = False
        self.tools = DeviceTools(device, app["ledger"].db, speech=self.reminder_audio)

    async def reminder_audio(self, text):
        """Render cached reminder speech and account for its provider usage."""
        return await synthesize_reminder(
            self.app["http"], os.environ["OPENAI_API_KEY"], text, self.app["ledger"]
        )

    async def _call_tool(self, call):
        name = call.get("name")
        if name == "search_web":
            try:
                query = json.loads(call["arguments"]).get("query")
                return await search_web(
                    self.app["http"], os.environ["OPENAI_API_KEY"], query, self.app["ledger"]
                )
            except (TimeoutError, ValueError, OSError, ClientError):
                return {"error": "Search failed; do not invent current facts"}
        if name == "search_memory":
            try:
                query = json.loads(call["arguments"]).get("query")
                return await search_memory(query)
            # SDK errors can contain credentials; retain a sanitized isolation boundary.
            except Exception:  # pylint: disable=broad-exception-caught
                LOG.warning("memory_lookup_failed")
                return {"error": "Memory lookup failed; do not invent memories"}
        return await self._call_action(call)

    async def _call_action(self, call):
        # Each allowlisted consumer returns its own bounded, sanitized failure.
        # pylint: disable=too-many-return-statements
        if call.get("name") == "remember_memory" and self.memory is not None:
            try:
                arguments = json.loads(call["arguments"])
                return await self.memory.remember(arguments.get("key"), arguments.get("content"))
            except (ValueError, TypeError, AttributeError):
                return {"error": "Invalid memory arguments"}
        if call.get("name") in HA_NAMES:
            try:
                return await call_home_assistant(call["name"], json.loads(call["arguments"]))
            except ValueError:
                return {"error": "Invalid Home Assistant arguments"}
        if call.get("name") in ACTIONS:
            try:
                return await self.tools.call(call["name"], json.loads(call["arguments"]))
            except (ValueError, OSError, ClientError):
                return {"error": "Device command failed"}
        return {"error": "Unsupported tool"}

    async def _response_done(self, upstream, response):
        summary = (response.get("metadata") or {}).get("purpose") == "memory_context"
        self.app["ledger"].record(response, None if summary else self.state.latency)
        if summary:
            self.summary_pending = False
            if response.get("status") == "completed" and self.memory is not None:
                text = "".join(part.get("text", "")
                               for item in response.get("output", [])
                               if item.get("type") == "message"
                               for part in item.get("content", [])
                               if part.get("type") == "output_text")
                try:
                    self.memory.queue(self.memory_session, "conversations", text)
                    self.memory.queue("latest_context", "continuity", text)
                except ValueError:
                    LOG.warning("memory_summary_invalid")
            if self.summary_dirty:
                await self._summarize(upstream)
            return
        calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
        if calls:
            self.state.tool_rounds += 1
            for call in calls:
                self.state.tool_calls += 1
                result = (await self._call_tool(call) if self.state.tool_calls <= 32
                          else {"error": "Turn action budget exhausted; operation not executed"})
                await upstream.send_json(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": json.dumps(result, ensure_ascii=False),
                        },
                    }
                )
            # A lookup, multiple household/shopping actions and memory must fit one turn.
            await upstream.send_json(
                {
                    "type": "response.create",
                    "response": {
                        "tool_choice": "auto" if (self.state.tool_rounds < 18
                                                  and self.state.tool_calls < 32) else "none"
                    },
                }
            )
        else:
            self.state.responding = False
            if self.codec and response.get("status") == "completed":
                tail = self.codec.finish()
                if tail:
                    await self.device.send_bytes(tail)
            await self.device.send_json(
                {"type": "done", "status": response["status"], "first_audio_ms": self.state.latency}
            )
            if response.get("status") == "completed":
                await self._summarize(upstream)

    async def _summarize(self, upstream):
        """Request a silent context snapshot without adding it to the spoken conversation."""
        if self.memory is None:
            return
        if self.summary_pending:
            self.summary_dirty = True
            return
        self.summary_dirty = False
        self.summary_pending = True
        await upstream.send_json({
            "type": "response.create", "event_id": "memory_summary", "response": {
                "conversation": "none", "metadata": {"purpose": "memory_context"},
                "output_modalities": ["text"], "tools": [], "tool_choice": "none",
                "max_output_tokens": 800,
                "instructions": load_prompts()["memory_summary"],
            },
        })

    async def receive_provider(self, upstream):
        """Forward audio immediately and record every completed response before tool dispatch."""
        async for msg in upstream:
            if msg.type != WSMsgType.TEXT:
                break
            event = json.loads(msg.data)
            kind = event["type"]
            if kind == "response.output_audio.delta":
                if self.state.latency is None and self.state.started:
                    self.state.latency = round((time.monotonic() - self.state.started) * 1000, 1)
                pcm = base64.b64decode(event["delta"])
                wire = self.codec.feed(pcm) if self.codec else pcm
                if wire:
                    await self.device.send_bytes(wire)
            elif kind == "response.done":
                await self._response_done(upstream, event["response"])
            elif kind == "error":
                if event.get("error", {}).get("event_id") == "memory_summary":
                    self.summary_pending = False
                    LOG.warning("memory_summary_failed")
                    continue
                LOG.warning("provider_error code=%s", event.get("error", {}).get("code"))
                await self.device.send_json({"type": "error"})
                await self.device.close()
                return
        await self.device.close()

    async def _command(self, upstream, event):
        command = event.get("type")
        if command == "device_ack":
            self.tools.acknowledge(event)
        elif command == "start" and not self.state.recording and not self.state.responding:
            if self.codec:
                self.codec.reset()
            # Read one coherent projected secret version for this entire turn.
            bundle = load_prompts()
            config = session_config(bundle)["session"]
            snapshot = event.get("reminders", self.reminder_snapshot)
            context = ""
            if "reminders" in event or snapshot is not None:
                context = reminder_context(snapshot, bundle)
            await upstream.send_json(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "instructions": config["instructions"] + context + self.memory_context,
                        "tools": config["tools"],
                    },
                }
            )
            self.reminder_snapshot = snapshot
            self.state.recording, self.state.count = True, 0
            await upstream.send_json({"type": "input_audio_buffer.clear"})
        elif command == "stop" and self.state.recording:
            await self._stop(upstream)
        else:
            raise ValueError("Invalid command")

    async def _stop(self, upstream):
        self.state.recording = False
        if self.state.count < RATE * 2 // 5:
            await upstream.send_json({"type": "input_audio_buffer.clear"})
            await self.device.send_json({"type": "done", "status": "empty"})
            return
        self.state.started = time.monotonic()
        self.state.latency, self.state.responding, self.state.tool_rounds = None, True, 0
        self.state.tool_calls = 0
        await upstream.send_json({"type": "input_audio_buffer.commit"})
        await upstream.send_json({"type": "response.create"})

    async def receive_device(self, upstream):
        """Accept bounded PCM and allowlisted control events from the appliance."""
        async with asyncio.timeout(3000):
            async for msg in self.device:
                if msg.type == WSMsgType.BINARY:
                    if not self.state.recording or len(msg.data) % 2:
                        raise ValueError("Unexpected audio")
                    self.state.count += len(msg.data)
                    if self.state.count > RATE * 2 * 30:
                        raise ValueError("Recording exceeds 30 seconds")
                    await upstream.send_json(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(msg.data).decode("ascii"),
                        }
                    )
                elif msg.type == WSMsgType.TEXT:
                    await self._command(upstream, json.loads(msg.data))
                else:
                    break

    async def run(self, upstream):
        """Gate recording on provider setup and finish billed usage on disconnect."""
        self.initial_config = session_config()
        if self.memory is not None:
            data = await self.memory.restore()
            self.memory_context = load_prompts()["memory_context_prefix"] + data
            self.initial_config["session"]["instructions"] += self.memory_context
        await upstream.send_json(self.initial_config)
        await _wait_for_session(upstream)
        await self.device.send_json({
            "type": "ready", "model": MODEL, "rate": RATE,
            "audio_format": "opus-24k-v1" if self.codec else "pcm16",
        })
        receiver = asyncio.create_task(self.receive_provider(upstream))
        try:
            await self.receive_device(upstream)
        finally:
            if (self.state.responding or self.summary_pending) and not receiver.done():
                try:
                    await asyncio.wait_for(asyncio.shield(receiver), 5)
                except (TimeoutError, ConnectionError):
                    pass
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)


async def _wait_for_session(upstream):
    """Require a provider acknowledgement before the device may submit audio."""
    async with asyncio.timeout(30):
        async for msg in upstream:
            event = json.loads(msg.data)
            if event["type"] == "error":
                raise RuntimeError(
                    "Provider session rejected: " + event["error"].get("code", "unknown")
                )
            if event["type"] == "session.updated":
                return
        raise RuntimeError("Provider disconnected during setup")


async def bridge(request):
    """Accept only a bounded device protocol, never arbitrary provider commands."""
    app = request.app
    if app["busy"].locked():
        raise web.HTTPConflict()
    async with app["busy"]:
        device = web.WebSocketResponse(max_msg_size=65536, heartbeat=30)
        await device.prepare(request)
        session = VoiceBridge(app, device)
        try:
            if request.query.get("audio") == "opus":
                session.codec = OpusEncoder()
            async with app["http"].ws_connect(
                "wss://api.openai.com/v1/realtime?model=" + MODEL,
                headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                heartbeat=20,
                max_msg_size=4 * 1024 * 1024,
            ) as upstream:
                await session.run(upstream)
        except (TimeoutError, ValueError, RuntimeError, ConnectionError, ClientError) as exc:
            LOG.warning("session_failed kind=%s", type(exc).__name__)
            if not device.closed:
                await device.send_json({"type": "error"})
        finally:
            if session.codec:
                session.codec.close()
            await device.close()
        return device


@web.middleware
async def authenticate(request, handler):
    """Health probes are public; every audio/accounting route requires device auth."""
    if request.path not in ("/healthz", "/readyz"):
        expected = "Bearer " + os.environ["AIY_BEARER_TOKEN"]
        if not hmac.compare_digest(request.headers.get("Authorization", ""), expected):
            raise web.HTTPUnauthorized()
    return await handler(request)


async def resources(app):
    """Manage the lifecycle of the HTTP client session and database connection."""
    app["http"] = ClientSession(timeout=ClientTimeout(total=None, sock_connect=15), trust_env=True)
    memory_worker = asyncio.create_task(app["memory"].worker())
    yield
    memory_worker.cancel()
    await asyncio.gather(memory_worker, return_exceptions=True)
    await app["http"].close()
    app["ledger"].db.close()


def create_app(path=None):
    """Create health, streaming and authenticated usage endpoints."""
    session_config()  # Fail startup before serving if the required prompt secret is invalid.
    app = web.Application(middlewares=[authenticate], client_max_size=16384)
    app["busy"] = asyncio.Lock()
    app["ledger"] = Ledger(path or os.environ.get("AIY_USAGE_DB", "/state/usage.sqlite3"))
    app["memory"] = ConversationMemory(app["ledger"].db)
    app.cleanup_ctx.append(resources)

    async def health(_request):
        """Return a JSON response indicating the service is healthy."""
        try:
            session_config()
        except RuntimeError:
            return web.json_response({"ok": False}, status=503)
        return web.json_response({"ok": True, "model": MODEL})

    async def usage(_request):
        """Return a JSON response containing recorded usage statistics."""
        return web.json_response({"responses": app["ledger"].rows()})

    app.router.add_get("/healthz", health)
    app.router.add_get("/readyz", health)
    app.router.add_get("/v1/voice", bridge)
    app.router.add_get("/v1/usage", usage)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(os.environ["AIY_BEARER_TOKEN"]) < 32:
        raise ValueError("Device token is too short")
    Path("/state").mkdir(exist_ok=True)
    # Service/probes require the isolated Pod bind; application routes require bearer auth.
    web.run_app(
        create_app(),
        host="0.0.0.0",  # nosec B104
        port=8080,
        access_log=None,
    )
