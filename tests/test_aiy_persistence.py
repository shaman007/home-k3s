"""Appliance state survives process replacement and repeat changes preserve completion."""

import asyncio
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))
from local_resources import LocalResources
from reminders import Reminders, ReminderSpec


class PersistenceTests(unittest.TestCase):
    """Exercise the actual on-disk stores across independent connections."""

    def test_note_survives_restart(self):
        """Reconstruct appliance resources and retrieve a saved note."""
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.sqlite3")
            first = LocalResources(path, lambda _: None, lambda _: None)
            result = asyncio.run(
                first.command({"action": "save_note", "id": "note-1", "text": "Проверить фильтр"})
            )
            self.assertTrue(result["ok"])
            first.timers.db.close()
            second = LocalResources(path, lambda _: None, lambda _: None)
            notes = asyncio.run(second.command({"action": "list_notes"}))["notes"]
            self.assertEqual(notes[0]["text"], "Проверить фильтр")
            second.timers.db.close()

    def test_interval_change_preserves_completion_and_does_not_replay(self):
        """Changing the grid skips elapsed slots and keeps acknowledgement rows."""
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.sqlite3")
            db = sqlite3.connect(path)
            store = Reminders(db)
            store.create(
                "task",
                ReminderSpec("Задача", "10:00", "22:00", 30, "сделал"),
                b"\x00\x00",
                first_date="2026-11-16",
                stamp=1794812400,
            )
            now = store.now(1794826800).timestamp()
            store.update_interval("task", 60, stamp=now)
            self.assertEqual(store.due(now), [])
            db.execute(
                "INSERT INTO reminder_acknowledgements VALUES (?, ?, ?)",
                ("task", store.now(now).date().isoformat(), now),
            )
            db.commit()
            store.update_interval("task", 90, stamp=now)
            with self.assertRaises(ValueError):
                store.update_interval("task", True, stamp=now)
            db.close()
            db = sqlite3.connect(path)
            restored = Reminders(db).describe("task", stamp=now)
            self.assertEqual(restored["repeat_minutes"], 90)
            self.assertTrue(restored["acknowledged_today"])
            db.close()
