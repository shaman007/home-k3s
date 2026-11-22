"""Durable scoped memories and a retryable MCP outbox, without audio or transcripts."""

import asyncio
import json
import logging
import re
import time

from memory_search import memory_call, redact

LOG = logging.getLogger("aiy.memory")
WING = "aiy_voice"
TOOLS = [{
    "type": "function", "name": "remember_memory", "description": "",
    "parameters": {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "", "maxLength": 64},
            "content": {"type": "string", "description": "", "maxLength": 2000},
        },
        "required": ["key", "content"], "additionalProperties": False,
    },
}]


class ConversationMemory:
    """Keep only AIY-owned writes; acknowledge persistence only after MCP success."""

    def __init__(self, db):
        self.db = db
        self.lock = asyncio.Lock()
        db.execute("CREATE TABLE IF NOT EXISTS memory_outbox ("
                   "key TEXT, room TEXT, content TEXT, updated REAL, PRIMARY KEY(room, key))")
        db.execute("CREATE TABLE IF NOT EXISTS memory_cache ("
                   "key TEXT, room TEXT, content TEXT, updated REAL, PRIMARY KEY(room, key))")
        db.commit()

    def queue(self, key, room, content):
        """Bound and redact before persisting anything locally."""
        if (room not in {"facts", "conversations", "continuity"}
                or not isinstance(content, str) or not content.strip()
                or len(content) > 4000 or redact(content) != content):
            raise ValueError("Invalid memory content")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_-]{1,100}", key):
            raise ValueError("Invalid memory key")
        if room == "facts" and key == "latest_context":
            raise ValueError("Reserved memory key")
        for table in ("memory_cache", "memory_outbox"):
            self.db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?, ?)",
                            (key, room, content.strip(), time.time()))
        self.db.commit()

    async def remember(self, key, content):
        """An explicit fact is immediately queued and synchronously attempted over MCP."""
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", key):
            return {"error": "Invalid memory key"}
        if not isinstance(content, str) or len(content) > 2000:
            return {"error": "Invalid memory content"}
        try:
            self.queue(key, "facts", content)
            async with asyncio.timeout(12):
                await self.flush(only_key=key)
        except ValueError:
            return {"error": "Invalid memory content; never store secrets"}
        except TimeoutError:
            LOG.warning("memory_write_pending")
        pending = self.db.execute(
            "SELECT 1 FROM memory_outbox WHERE key=? AND room='facts'", (key,)
        ).fetchone()
        return {"saved": not bool(pending), "pending": bool(pending)}

    async def _upsert(self, key, room, content):
        source = "aiy:" + room + ":" + key
        # Exact source lookup allows safe retry after a lost write response and updates
        # only a drawer in our own wing/room. No model-controlled IDs or MCP names.
        found = await memory_call("mempalace_search", {
            "query": key[:100], "wing": WING, "room": room,
            "source_file": source, "limit": 1,
        })
        matches = found.get("results", [])
        if matches:
            result = await memory_call("mempalace_update_drawer", {
                "drawer_id": matches[0]["drawer_id"], "content": content,
            })
        else:
            result = await memory_call("mempalace_add_drawer", {
                "wing": WING, "room": room, "content": content,
                "source_file": source, "added_by": "aiy-voice",
            })
        if result.get("success") is not True:
            raise RuntimeError("Memory write unconfirmed")

    async def flush(self, only_key=None):
        """Retry a bounded batch; failures never expose SDK exceptions or memory text."""
        async with self.lock:
            rows = self.db.execute(
                "SELECT key, room, content, updated FROM memory_outbox "
                "WHERE (? IS NULL OR key=?) ORDER BY updated LIMIT 8", (only_key, only_key)
            ).fetchall()
            for key, room, content, updated in rows:
                try:
                    await self._upsert(key, room, content)
                except Exception:  # pylint: disable=broad-exception-caught
                    LOG.warning("memory_write_pending")
                    return
                self.db.execute("DELETE FROM memory_outbox WHERE key=? AND room=? AND updated=?",
                                (key, room, updated))
                if room == "conversations":
                    self.db.execute("DELETE FROM memory_cache WHERE key=? AND room=? AND updated=?",
                                    (key, room, updated))
                self.db.commit()

    async def worker(self):
        """Retry across device disconnections and backend restarts."""
        while True:
            await self.flush()
            await asyncio.sleep(15)

    async def restore(self):
        """Load identity, facts and the latest compact context via MCP at session start."""
        memories = []
        remote_available = False
        try:
            async with asyncio.timeout(12):
                for room in ("identity", "facts", "continuity"):
                    page = await memory_call("mempalace_list_drawers", {
                        "wing": WING, "room": room, "limit": 100,
                    })
                    ids = [item["drawer_id"] for item in page.get("drawers", [])]
                    if ids:
                        data = await memory_call("mempalace_get_drawers", {"drawer_ids": ids})
                        for item in data.get("results", []):
                            memories.append({"room": room,
                                             "content": redact(item.get("content", ""))[:4000],
                                             "metadata": item.get("metadata", {})})
                remote_available = True
        except Exception:  # pylint: disable=broad-exception-caught
            LOG.warning("memory_restore_unavailable")
        # Pending writes are newer than remote copies. Include them last, with status,
        # without misrepresenting the retry queue as a successful MemPalace save.
        local = [{"key": key, "room": room, "content": content, "pending": bool(pending)}
                 for key, room, content, pending in self.db.execute(
                     "SELECT key, room, content, EXISTS (SELECT 1 FROM memory_outbox o "
                     "WHERE o.room=c.room AND o.key=c.key) FROM memory_cache c "
                     "WHERE room != 'conversations' ORDER BY updated DESC LIMIT 32")
                 if pending or not remote_available]
        # Bound structurally, so truncation cannot turn JSON into malformed prompt text.
        result = {"memories": [], "local": []}
        priority = {"identity": 0, "continuity": 1, "facts": 2}
        candidates = [("memories", item) for item in memories]
        candidates.extend(("local", item) for item in local)
        candidates.sort(key=lambda row: (priority[row[1]["room"]], row[0] != "local"))
        for destination, item in candidates:
            result[destination].append(item)
            if len(json.dumps(result, ensure_ascii=False)) > 24000:
                result[destination].pop()
        return json.dumps(result, ensure_ascii=False)
