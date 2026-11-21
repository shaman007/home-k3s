"""Audio privacy and physical-button protocol regressions."""

import asyncio
import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))

SPEC = importlib.util.spec_from_file_location(
    "voice_client", Path(__file__).resolve().parents[1] / "aiy-voice/pi_client.py"
)
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)


class VoiceClientTests(unittest.IsolatedAsyncioTestCase):
    """Verify physical-button control and idle-microphone privacy."""

    def test_indicator_schedule_boundaries(self):
        """Cover dusk, midnight and morning for status and effect colors."""
        for hour, minute, expected in [
            (23, 29, (12, 3, 0)),
            (23, 30, (1, 0, 0)),
            (23, 59, (1, 0, 0)),
            (0, 0, (0, 0, 0)),
            (5, 59, (0, 0, 0)),
            (6, 0, (12, 3, 0)),
        ]:
            with self.subTest(hour=hour, minute=minute):
                now = datetime(2026, 11, 21, hour, minute)
                self.assertEqual(client.scheduled_color((64, 16, 0), now), expected)
                self.assertEqual(client.scheduled_color((0, 0, 0), now), (0, 0, 0))
        self.assertEqual(
            client.scheduled_color((0, 16, 0), datetime(2026, 11, 21, 23, 30)),
            (0, 1, 0),
        )

    def test_idle_indicator_refreshes_without_a_status_event(self):
        """A clock transition updates idle light and preserves the requested color."""
        colors = [(0, 3, 0), (0, 1, 0), (0, 0, 0), (0, 3, 0)]
        with (
            patch.object(client, "led") as write,
            patch.object(client, "scheduled_color", side_effect=colors),
        ):
            indicator = client.ScheduledIndicator()
            indicator((0, 16, 0))
            for _ in range(3):
                indicator.refresh()
            self.assertEqual(
                [call.args[0] for call in write.call_args_list],
                colors,
            )
            self.assertEqual(indicator.rgb, (0, 16, 0))

    async def test_each_press_sends_fresh_reminders_even_before_first_alert(self):
        """Verify each press sends fresh reminders even before first alert."""
        ws = AsyncMock()
        resources = Mock()
        resources.reminders.list.side_effect = [
            [],
            [{"id": "created-externally", "acknowledged_today": False}],
        ]
        instance = client.Client(ws, resources)
        await instance.start()
        await instance.stop()
        instance.busy = False
        await instance.start()
        await instance.stop()
        starts = [
            call.args[0] for call in ws.send_json.call_args_list if call.args[0]["type"] == "start"
        ]
        self.assertEqual(starts[0]["reminders"], [])
        self.assertEqual(starts[1]["reminders"][0]["id"], "created-externally")

    def test_origin_validation(self):
        """Verify origin validation."""
        for url in [
            "http://example.org",
            "https://a:b@example.org",
            "https://example.org/path",
            "https://example.org?x=1",
        ]:
            with self.assertRaises(ValueError):
                client.voice_url(url)
        self.assertEqual(client.voice_url("https://example.org/"), "wss://example.org/v1/voice")

    async def test_idle_audio_is_discarded(self):
        """Verify idle audio is discarded."""
        ws = AsyncMock()
        instance = client.Client(ws)
        source = asyncio.StreamReader()
        source.feed_data(b"\x00\x00" * 1000)
        source.feed_eof()
        with self.assertRaises(RuntimeError):
            await instance.capture(source)
        ws.send_bytes.assert_not_called()

    async def test_batched_gpio_edges_commit_exactly_once(self):
        """Verify batched gpio edges commit exactly once."""
        ws = AsyncMock()
        instance = client.Client(ws)
        source = asyncio.StreamReader()
        source.feed_data(b"falling 23\nrising 23\n")
        source.feed_eof()
        with patch.object(client, "led"), self.assertRaises(RuntimeError):
            await instance.buttons(source)
        self.assertEqual(
            [call.args[0]["type"] for call in ws.send_json.call_args_list], ["start", "stop"]
        )
        self.assertFalse(instance.recording)
        self.assertTrue(instance.busy)


if __name__ == "__main__":
    unittest.main()
