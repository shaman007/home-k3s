"""Multi-intent tool dispatch and restart-safe reminder edits and temporary pauses."""

import importlib
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiy_gateway_fixture import prompt_environment

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))
reminders = importlib.import_module("reminders")
server = importlib.import_module("server")
devices = importlib.import_module("device_tools")


def at(value):
    """Use explicit local clocks rather than changing any live reminder."""
    return datetime.fromisoformat(value).replace(tzinfo=reminders.ZONE).timestamp()


def add(store, identity):
    """Create a synthetic daily fixture with independent acknowledgement state."""
    store.create(identity, reminders.ReminderSpec(identity, "10:00", "22:00", 60, "сделал"),
                 b"\x00\x00", first_date="2026-11-16", stamp=at("2026-11-16T08:00"))


class ReminderEditsTests(unittest.TestCase):
    """Preserve state and recurrence while changing only requested reminder fields."""

    def setUp(self):
        """Give every test a fresh database with two unrelated tasks."""
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = reminders.Reminders(self.db)
        add(self.store, "fish")
        add(self.store, "cats")

    def test_long_pause_survives_reopen_and_automatically_resumes(self):
        """A pause longer than a week must still have a correct next notification."""
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "reminders.sqlite3")
            db = sqlite3.connect(path)
            store = reminders.Reminders(db)
            add(store, "fish")
            result = store.suspend("fish", "2026-12-01", at("2026-11-16T12:00"))["reminder"]
            self.assertTrue(result["paused"])
            self.assertTrue(result["enabled"])
            self.assertFalse(result["acknowledged_today"])
            self.assertTrue(result["next_notification"].startswith("2026-12-01T10:00"))
            db.close()
            db = sqlite3.connect(path)
            self.addCleanup(db.close)
            store = reminders.Reminders(db)
            self.assertEqual(store.due(at("2026-11-30T20:00")), [])
            self.assertEqual(len(store.due(at("2026-12-01T10:00"))), 1)

    def test_resume_skips_old_slots_and_does_not_affect_other_tasks(self):
        """Early return resumes the next scheduled slot instead of replaying absence."""
        now = at("2026-11-16T12:10")
        self.store.suspend("fish", "2026-11-20", now)
        self.assertEqual([x["id"] for x in self.store.due(now)], ["cats"])
        self.store.resume("fish", now)
        self.assertNotIn("fish", [x["id"] for x in self.store.due(now)])
        self.assertIn("fish", [x["id"] for x in self.store.due(at("2026-11-16T13:00"))])

    def test_edit_preserves_completion_pause_and_identity(self):
        """Edit content and schedule in place while keeping existing acknowledgements."""
        now = at("2026-11-16T12:00")
        self.store.acknowledge("сделал", "fish", now)
        self.store.suspend("fish", "2026-11-20", now)
        result = self.store.update("fish", {
            "text": "Проверь аквариум", "start_time": "11:00", "end_time": "21:00",
            "repeat_minutes": 120, "weekdays": [0, 4], "jitter_minutes": 5,
            "confirmation_phrase": "аквариум проверил",
        }, b"\x01\x00", now)["reminder"]
        self.assertEqual(result["id"], "fish")
        self.assertEqual(result["paused_until"], "2026-11-20")
        self.assertTrue(result["acknowledged_today"])
        self.assertEqual(result["weekdays"], [0, 4])
        self.assertEqual(self.store.row("fish")["audio"], b"\x01\x00")
        self.assertEqual(self.store.describe("cats", now)["repeat_minutes"], 60)

    def test_invalid_edits_are_atomic_and_need_new_speech_for_new_text(self):
        """Invalid partial edits cannot corrupt an existing schedule or audio cache."""
        before = self.store.row("fish")
        for changes in ({}, {"enabled": False}, {"weekdays": []},
                        {"end_time": "09:00"}, {"text": "Changed without speech"}):
            with self.assertRaises(ValueError):
                self.store.update("fish", changes, stamp=at("2026-11-16T12:00"))
            self.assertEqual(self.store.row("fish"), before)

    def test_shared_verb_completes_both_selected_tasks_but_negation_does_not(self):
        """Both pets can be completed today; an ambiguous negated clause stays guarded."""
        now = at("2026-11-16T12:00")
        for identity in ("fish", "cats"):
            self.assertIn("error", self.store.acknowledge(
                "Я покормил рыб, но не кошек", identity, now))
            self.assertTrue(self.store.acknowledge(
                "Я покормил рыб и кошек", identity, now)["ok"])
        self.assertTrue(all(x["acknowledged_today"] for x in self.store.list(now)))


class MultiActionBridgeTests(unittest.IsolatedAsyncioTestCase):
    """Account for each action and preserve per-item failures without live HA writes."""

    # Exercise the private provider/tool boundary rather than a mirror of dispatch logic.
    # pylint: disable=protected-access

    def setUp(self):
        """Build an isolated bridge with synthetic prompts and mocked consumers."""
        self.enterContext(prompt_environment())
        self.ledger = server.Ledger(":memory:")
        self.addCleanup(self.ledger.db.close)
        self.bridge = server.VoiceBridge({"ledger": self.ledger}, AsyncMock())

    async def test_lookup_and_two_shopping_completions_fit_one_voice_turn(self):
        """A shopping lookup must not consume the budget needed to finish two items."""
        upstream = AsyncMock()
        self.bridge._call_tool = AsyncMock(return_value={"success": True})
        for index, (name, args) in enumerate([
            ("ha_todo__get_items", {"todo_list": "Shopping list"}),
            ("ha_todo__HassListCompleteItem", {"item": "кофе"}),
            ("ha_todo__HassListCompleteItem", {"item": "молоко"}),
        ]):
            await self.bridge._response_done(upstream, {
                "id": str(index), "status": "completed", "output": [{
                    "type": "function_call", "name": name, "arguments": json.dumps(args),
                    "call_id": str(index),
                }],
            })
            self.assertEqual(upstream.send_json.await_args.args[0]["response"]["tool_choice"],
                             "auto")
        self.assertEqual(self.bridge._call_tool.await_count, 3)

    async def test_all_returned_calls_get_results_and_failure_is_not_hidden(self):
        """Do not silently discard a third call or flatten mixed results into success."""
        upstream = AsyncMock()
        self.bridge._call_tool = AsyncMock(side_effect=[{"ok": True}, {"error": "missing"},
                                                       {"ok": True}])
        await self.bridge._response_done(upstream, {
            "id": "batch", "status": "completed", "output": [{
                "type": "function_call", "name": "acknowledge_reminder",
                "call_id": str(i), "arguments": "{}",
            } for i in range(3)],
        })
        results = [c.args[0]["item"] for c in upstream.send_json.await_args_list
                   if c.args[0]["type"] == "conversation.item.create"]
        self.assertEqual(len(results), 3)
        self.assertIn("error", json.loads(results[1]["output"]))

    async def test_text_edit_regenerates_speech_before_device_dispatch(self):
        """The spoken reminder cache changes together with its visible text."""
        socket = AsyncMock()
        speech = AsyncMock(return_value="AQA=")
        tool = devices.DeviceTools(socket, self.ledger.db, speech=speech)
        async def acknowledge(event):
            tool.acknowledge({"id": event["id"], "result": {"ok": True}})
        socket.send_json.side_effect = acknowledge
        result = await tool.call("update_daily_reminder", {
            "reminder_id": "fish", "changes": {"text": "Проверь аквариум"}})
        self.assertTrue(result["ok"])
        speech.assert_awaited_once_with("Проверь аквариум")
        self.assertEqual(socket.send_json.await_args.args[0]["audio"], "AQA=")

    async def test_exhausted_budget_returns_errors_and_new_turn_resets_it(self):
        """A pathological tool loop is bounded without silently losing call results."""
        upstream = AsyncMock()
        self.bridge.state.tool_calls = 32
        self.bridge._call_tool = AsyncMock()
        await self.bridge._response_done(upstream, {
            "id": "exhausted", "status": "completed", "output": [{
                "type": "function_call", "name": "acknowledge_reminder",
                "call_id": "excess", "arguments": "{}",
            }],
        })
        self.bridge._call_tool.assert_not_awaited()
        result = upstream.send_json.await_args_list[0].args[0]["item"]["output"]
        self.assertIn("not executed", result)
        self.bridge.state.count = server.RATE
        await self.bridge._stop(upstream)
        self.assertEqual(self.bridge.state.tool_calls, 0)

    async def test_local_dispatch_for_edit_pause_and_resume(self):
        """The Pi command path applies all new operations to a disposable database."""
        module = importlib.import_module("local_resources")
        with tempfile.TemporaryDirectory() as directory:
            resource = module.LocalResources(str(Path(directory) / "state.sqlite3"),
                                             lambda _: None, AsyncMock())
            try:
                add(resource.reminders, "fish")
                now = datetime.fromtimestamp(at("2026-11-16T12:00"), reminders.ZONE)
                with patch.object(resource.reminders, "now", return_value=now):
                    for action, args in [
                        ("update_daily_reminder", {"changes": {"repeat_minutes": 120}}),
                        ("suspend_daily_reminder", {"until_date": "2026-11-20"}),
                        ("resume_daily_reminder", {}),
                    ]:
                        result = await resource.command(dict(args, action=action,
                                                             reminder_id="fish"))
                        self.assertTrue(result["ok"])
            finally:
                await resource.close()


class PromptMigrationTests(unittest.TestCase):
    """The release requires an additive secret catalog migration, not runtime defaults."""

    def test_operator_texts_extend_the_current_catalog_without_mutating_it(self):
        """Synthetic descriptions satisfy the runtime's exact schema-slot contract."""
        spec = importlib.util.spec_from_file_location(
            "reminder_upgrade", Path(__file__).resolve().parents[1]
            / "tools/aiy/reminder_prompt_upgrade.py")
        upgrade = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(upgrade)
        with prompt_environment():
            bundle = server.load_prompts()
            descriptions = {name: bundle["tools"].pop(name)
                            for name in upgrade.DESCRIPTION_PATHS}
            previous = json.dumps(bundle)
            updated = upgrade.upgrade(bundle, policy="Synthetic multi-intent policy",
                                      descriptions=descriptions)
            server.session_config(updated)
            self.assertEqual(json.dumps(bundle), previous)
