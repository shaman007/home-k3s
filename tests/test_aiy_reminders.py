"""Daily-cycle acceptance, early dismiss, quiet hours, catch-up and restart regressions."""

import asyncio
import base64
import importlib
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiy_gateway_fixture import prompt_environment

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))
Reminders = importlib.import_module("reminders").Reminders
ReminderSpec = importlib.import_module("reminders").ReminderSpec
ZONE = importlib.import_module("reminders").ZONE
LocalResources = importlib.import_module("local_resources").LocalResources
AudioOutput = importlib.import_module("local_resources").AudioOutput
synthesize = importlib.import_module("reminder_speech").synthesize


def stamp(value):
    """Convert a local ISO date and time to a Prague timestamp."""
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()



def setUpModule():  # pylint: disable=invalid-name
    """Supply only synthetic prompts to tests, never read production secrets."""
    unittest.enterModuleContext(prompt_environment())


class RemindersTests(unittest.TestCase):
    """Verify independent reminder cycles, recurrence and day-specific completion."""

    def setUp(self):
        """Create an isolated in-memory reminder database."""
        self.db = sqlite3.connect(":memory:")
        self.store = Reminders(self.db)

    def tearDown(self):
        """Close the test database."""
        self.db.close()

    def add(self, identity="fish", phrase="покормил рыбок"):
        """Create a daily fixture with a fixed start date and reference clock."""
        return self.store.create(
            identity,
            ReminderSpec(
                "Покорми рыбок" if identity == "fish" else "Покорми кошек",
                "10:00",
                "22:00",
                30,
                phrase,
            ),
            b"\x00\x00" * 24000,
            first_date="2026-11-16",
            stamp=stamp("2026-11-16T08:00"),
        )

    def test_each_slot_fires_once_and_stops_at_22(self):
        """Verify each slot fires once and stops at 22."""
        self.add()
        self.assertEqual(self.store.due(stamp("2026-11-16T09:59")), [])
        event = self.store.due(stamp("2026-11-16T10:00"))[0]
        self.store.delivered(event)
        self.assertEqual(self.store.due(stamp("2026-11-16T10:29")), [])
        self.assertEqual(len(self.store.due(stamp("2026-11-16T10:30"))), 1)
        self.assertEqual(self.store.due(stamp("2026-11-16T22:00")), [])
        self.assertEqual(self.store.due(stamp("2026-11-17T09:59")), [])
        self.assertEqual(len(self.store.due(stamp("2026-11-17T10:00"))), 1)

    def test_early_completion_closes_only_today_and_only_that_task(self):
        """Verify early completion closes only today and only that task."""
        self.add()
        self.add("cats", "покормил кошек")
        result = self.store.acknowledge("Я уже покормил рыбок", stamp=stamp("2026-11-16T08:15"))
        self.assertTrue(result["ok"])
        self.assertEqual([x["id"] for x in self.store.due(stamp("2026-11-16T10:00"))], ["cats"])
        self.assertEqual(
            {x["id"] for x in self.store.due(stamp("2026-11-17T10:00"))}, {"fish", "cats"}
        )

    def test_semantic_completion_with_explicit_task_and_negative_guards(self):
        """Verify semantic completion with explicit task and negative guards."""
        self.add()
        self.assertTrue(
            self.store.acknowledge(
                "Рыбок накормил сегодня", reminder_id="fish", stamp=stamp("2026-11-16T08:00")
            )["ok"]
        )
        for text in [
            "не покормил рыбок",
            "покормлю рыбок позже",
            "я покормил рыбок?",
            "я вчера покормил рыбок",
            "я забыл покормить рыбок",
            "если я покормил рыбок",
            "я скажу покормил рыбок",
        ]:
            self.db.execute("DELETE FROM reminder_acknowledgements")
            self.db.commit()
            self.assertIn(
                "error",
                self.store.acknowledge(text, reminder_id="fish", stamp=stamp("2026-11-16T11:00")),
            )
            self.assertFalse(
                self.store.describe("fish", stamp("2026-11-16T11:00"))["acknowledged_today"]
            )

    def test_duplicate_phrases_require_clarification(self):
        """Verify duplicate phrases require clarification."""
        self.add("fish", "сделал")
        self.add("cats", "сделал")
        self.assertIn("error", self.store.acknowledge("сделал", stamp=stamp("2026-11-16T11:00")))
        self.assertEqual(len(self.store.due(stamp("2026-11-16T11:00"))), 2)
        self.store.acknowledge("сделал", reminder_id="fish", stamp=stamp("2026-11-16T11:00"))
        self.assertIn("error", self.store.acknowledge("сделал", stamp=stamp("2026-11-16T11:01")))
        self.assertFalse(
            self.store.describe("cats", stamp("2026-11-16T11:01"))["acknowledged_today"]
        )

    def test_restart_preserves_ack_and_no_backlog_storm(self):
        """Verify restart preserves ack and no backlog storm."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite"
            db = sqlite3.connect(path)
            r = Reminders(db)
            r.create(
                "a",
                ReminderSpec("Проверь задачу", "10:00", "22:00", 30, "сделал"),
                b"\x00\x00",
                first_date="2026-11-16",
                stamp=stamp("2026-11-16T08:00"),
            )
            due = r.due(stamp("2026-11-16T15:17"))
            self.assertEqual(len(due), 1)
            r.delivered(due[0])
            r.acknowledge("сделал", stamp=stamp("2026-11-16T15:18"))
            db.close()
            db = sqlite3.connect(path)
            r = Reminders(db)
            self.assertEqual(r.due(stamp("2026-11-16T16:00")), [])
            self.assertEqual(len(r.due(stamp("2026-11-17T10:00"))), 1)
            db.close()

    def test_dst_uses_local_calendar_day(self):
        """Verify dst uses local calendar day."""
        self.store.create(
            "dst",
            ReminderSpec("Проверь задачу", "10:00", "22:00", 30, "сделал"),
            b"\x00\x00",
            first_date="2026-10-24",
            stamp=stamp("2026-10-24T08:00"),
        )
        result = self.store.acknowledge("сделал", stamp=stamp("2026-10-24T11:00"))
        self.assertTrue(result["reminder"]["next_notification"].endswith("+01:00"))
        self.assertEqual(len(self.store.due(stamp("2026-10-25T10:00"))), 1)

    def test_default_first_start_is_tomorrow_if_start_already_passed(self):
        """Verify default first start is tomorrow if start already passed."""
        result = self.store.create(
            "a",
            ReminderSpec("Проверь задачу", "10:00", "22:00", 30, "сделал"),
            b"\x00\x00",
            stamp=stamp("2026-11-16T15:00"),
        )
        self.assertEqual(result["first_date"], "2026-11-17")
        self.assertEqual(self.store.due(stamp("2026-11-16T15:00")), [])
        self.assertTrue(self.store.acknowledge("сделал", stamp=stamp("2026-11-16T15:00"))["ok"])
        self.assertEqual(len(self.store.due(stamp("2026-11-17T10:00"))), 1)

    def test_disabling_differs_from_daily_ack(self):
        """Verify disabling differs from daily ack."""
        self.add()
        self.store.disable("fish", stamp=stamp("2026-11-16T12:00"))
        self.assertEqual(self.store.due(stamp("2026-11-17T10:00")), [])

    def weekly(self, **extra):
        """Create a Monday fixture with caller-specified jitter settings."""
        return self.store.create(
            "weekly",
            ReminderSpec("Проверь задачу", "12:00", "22:00", 30, "сделал", weekdays=[0], **extra),
            b"\x00\x00",
            first_date="2026-11-16",
            stamp=stamp("2026-11-15T23:00"),
        )

    def test_monday_only_and_early_completion_reopens_next_monday(self):
        """Verify monday only and early completion reopens next monday."""
        self.weekly(jitter_minutes=10)
        result = self.store.acknowledge(
            "сделал", reminder_id="weekly", stamp=stamp("2026-11-16T08:00")
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["reminder"]["next_notification"].startswith("2026-11-23T"))
        self.assertEqual(self.store.due(stamp("2026-11-16T14:00")), [])
        for day in range(17, 23):
            self.assertEqual(self.store.due(stamp(f"2026-11-{day}T14:00")), [])
            self.assertIn(
                "error",
                self.store.acknowledge(
                    "сделал", reminder_id="weekly", stamp=stamp(f"2026-11-{day}T08:00")
                ),
            )
        self.assertEqual(len(self.store.due(stamp("2026-11-23T14:00"))), 1)

    def test_offsets_stay_in_bounds_are_stable_and_include_first_slot(self):
        """Verify offsets stay in bounds are stable and include first slot."""
        self.weekly(jitter_minutes=10)
        self.db.execute(
            "UPDATE reminder_recurrence SET seed=? WHERE id=?", ("test-early", "weekly")
        )
        self.db.commit()
        row = self.store.row("weekly")
        day = datetime.fromisoformat("2026-11-16").date()
        slots = self.store.slots(row, day)
        offsets = [
            (at - datetime.combine(day, datetime.min.time(), ZONE)).total_seconds()
            - (12 * 60 + i * 30) * 60
            for i, at in slots
        ]
        self.assertTrue(all(-600 <= x <= 600 for x in offsets))
        self.assertLess(offsets[0], 0)  # First alert really may precede the nominal start.
        self.assertTrue(all(slots[i][1] < slots[i + 1][1] for i in range(len(slots) - 1)))
        restarted = Reminders(self.db)
        self.assertEqual(slots, restarted.slots(restarted.row("weekly"), day))
        self.assertNotEqual(
            slots[0][1].time(),
            restarted.slots(row, datetime.fromisoformat("2026-11-23").date())[0][1].time(),
        )

    def test_actual_jitter_deadline_not_nominal_grid_controls_delivery(self):
        """Verify actual jitter deadline not nominal grid controls delivery."""
        self.weekly(jitter_minutes=10)
        row = self.store.row("weekly")
        first, second = self.store.slots(row, datetime.fromisoformat("2026-11-16").date())[:2]
        self.assertEqual(self.store.due(first[1].timestamp() - 0.01), [])
        event = self.store.due(first[1].timestamp())[0]
        self.assertEqual(event["slot"], 0)
        self.store.delivered(event)
        self.assertEqual(self.store.due(second[1].timestamp() - 0.01), [])
        self.assertEqual(self.store.due(second[1].timestamp())[0]["slot"], 1)
        self.assertEqual(self.store.due(stamp("2026-11-16T22:00")), [])

    def test_late_recovery_plays_only_latest_slot_with_jitter(self):
        """Verify late recovery plays only latest slot with jitter."""
        self.weekly(jitter_minutes=10)
        events = self.store.due(stamp("2026-11-16T21:50"))
        self.assertEqual(len(events), 1)
        self.store.delivered(events[0])
        self.assertEqual(Reminders(self.db).due(stamp("2026-11-16T21:51")), [])

    def test_old_rows_keep_daily_exact_schedule_without_destructive_migration(self):
        """Verify old rows keep daily exact schedule without destructive migration."""
        self.add()
        self.db.execute("DROP TABLE reminder_recurrence")
        self.db.commit()
        restored = Reminders(self.db)
        item = restored.describe("fish", stamp("2026-11-16T08:00"))
        self.assertEqual(item["weekdays"], list(range(7)))
        self.assertEqual(item["jitter_minutes"], 0)
        self.assertEqual(len(restored.due(stamp("2026-11-17T10:00"))), 1)

    def test_free_form_affirmative_adjectives_and_past_verbs(self):
        """Verify free form affirmative adjectives and past verbs."""
        cases = [
            ("pill", "Прими таблетку", "Таблетка принята"),
            ("cats", "Покорми кошек", "Кошки сыты"),
            ("tank", "Обслужи аквариум", "С аквариумом закончил"),
            ("fish", "Покорми рыбок", "Рыбки уже накормлены"),
        ]
        for identity, text, phrase in cases:
            self.store.create(
                identity,
                ReminderSpec(text, "10:00", "22:00", 30, "сделал"),
                b"\x00\x00",
                stamp=stamp("2026-11-16T08:00"),
            )
            self.assertTrue(
                self.store.acknowledge(
                    phrase, reminder_id=identity, stamp=stamp("2026-11-16T08:00")
                )["ok"]
            )
        self.assertIn(
            "error",
            self.store.acknowledge(
                "Кошки не сыты", reminder_id="cats", stamp=stamp("2026-11-16T08:00")
            ),
        )

    def test_invalid_recurrence_parameters(self):
        """Verify invalid recurrence parameters."""
        for args in [
            {"weekdays": []},
            {"weekdays": [True]},
            {"weekdays": [7]},
            {"jitter_minutes": True},
            {"jitter_minutes": 11},
            {"jitter_minutes": -1},
        ]:
            with self.assertRaises(ValueError):
                self.store.create(
                    "bad",
                    ReminderSpec("Проверь задачу", "10:00", "22:00", 30, "сделал", **args),
                    b"\x00\x00",
                    stamp=stamp("2026-11-16T08:00"),
                )


class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    """Verify alarms wait for conversations and can be interrupted."""

    async def test_reminders_wait_for_conversation_and_play_offline(self):
        """Verify reminders wait for conversation and play offline."""
        resources = LocalResources(":memory:", Mock(), AsyncMock())
        resources.reminders.now = lambda _stamp=None: datetime(2026, 11, 16, 10, tzinfo=ZONE)
        resources.reminders.create(
            "test",
            ReminderSpec("Проверь задачу", "10:00", "22:00", 30, "сделал"),
            b"\x00\x00",
            first_date="2026-11-16",
        )
        resources.engaged = True
        task = asyncio.create_task(resources.scheduler())
        try:
            await asyncio.sleep(0.01)
            resources.play_alarm.assert_not_awaited()
            resources.engaged = False
            await asyncio.sleep(0.3)
            resources.play_alarm.assert_awaited_once_with(b"\0\0")
            self.assertEqual(resources.reminders.due(), [])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await resources.close()

    async def test_press_interrupts_playback_without_waiting_for_audio_lock(self):
        """Verify press interrupts playback without waiting for audio lock."""
        output = AudioOutput("unused")
        process = Mock(returncode=None)
        process.wait = AsyncMock()
        output.process = process
        async with output.lock:
            await asyncio.wait_for(output.interrupt(), 0.1)
        process.terminate.assert_called_once()
        self.assertIs(output.interrupted, process)

    async def test_audio_prefill_short_reply_and_interrupt(self):
        """Prefill streaming speech, flush short replies and discard interrupted audio."""
        output = AudioOutput("unused")
        process = Mock(returncode=None)
        process.stdin.drain = AsyncMock()
        process.wait = AsyncMock()
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as start:
            await output.play(b"a" * 4800)
            start.assert_not_awaited()
            await output.play(b"b" * 19200)
            process.stdin.write.assert_called_once_with(b"a" * 4800 + b"b" * 19200)
            process.returncode = 0
            await output.finish()
            await output.play(b"short")
            await output.finish()
            self.assertEqual(process.stdin.write.call_args.args[0], b"short")
            await output.play(b"discard")
            await output.interrupt()
            self.assertEqual(output.pending, b"")


class SpeechTests(unittest.IsolatedAsyncioTestCase):
    """Verify literal reminder audio and provider usage are retained."""

    async def run_speech(self, transcript):
        """Feed deterministic Realtime events to the speech renderer."""
        pcm = b"\0\0" * 100
        events = [
            {"type": "session.updated"},
            {"type": "response.output_audio.delta", "delta": base64.b64encode(pcm).decode()},
            {"type": "response.output_audio_transcript.done", "transcript": transcript},
            {
                "type": "response.done",
                "response": {"id": "test", "status": "completed", "usage": {}},
            },
        ]

        class Socket:
            """Provide the minimal protocol required by this test fixture."""

            send_json = AsyncMock()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def __aiter__(self):
                for event in events:
                    yield SimpleNamespace(data=json.dumps(event))

        http = Mock()
        http.ws_connect.return_value = Socket()
        ledger = Mock()
        try:
            return await synthesize(http, "fake", "Проверь задачу", ledger)
        finally:
            ledger.record.assert_called_once()

    async def test_literal_audio_and_usage_are_retained(self):
        """Verify literal audio and usage are retained."""
        self.assertEqual(base64.b64decode(await self.run_speech("Проверь задачу.")), b"\0\0" * 100)

    async def test_changed_spoken_text_is_not_installed(self):
        """Verify changed spoken text is not installed."""
        with self.assertRaisesRegex(ValueError, "did not match"):
            await self.run_speech("Конечно, проверь задачу")
