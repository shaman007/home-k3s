"""Audio privacy and physical-button protocol regressions."""

import asyncio
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))

SPEC = importlib.util.spec_from_file_location(
    "voice_client", Path(__file__).resolve().parents[1] / "aiy-voice/pi_client.py"
)
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)


class VoiceClientTests(unittest.IsolatedAsyncioTestCase):
    """Verify physical-button control and idle-microphone privacy."""

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
