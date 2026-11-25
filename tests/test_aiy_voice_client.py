"""Audio privacy and physical-button protocol regressions."""

import asyncio
import importlib.util
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))

SPEC = importlib.util.spec_from_file_location(
    "voice_client", Path(__file__).resolve().parents[1] / "aiy-voice/pi_client.py"
)
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)


class VoiceClientTests(unittest.IsolatedAsyncioTestCase):
    """Verify physical-button control and idle-microphone privacy."""

    async def test_short_reply_waits_for_done_and_keeps_receiver_running(self):
        """Short replies flush on completion; receive remains free during playback."""
        audio = AsyncMock()
        resources = Mock()
        release_playback = asyncio.Event()
        instance = None

        async def play(_pcm):
            await release_playback.wait()

        audio.play.side_effect = play

        class Socket:
            async def __aiter__(self):
                for chunk in (b"a" * 4800, b"b" * 48000):
                    yield SimpleNamespace(type=client.aiohttp.WSMsgType.BINARY, data=chunk)
                    await asyncio.sleep(0)
                    audio.play.assert_not_awaited()
                yield SimpleNamespace(type=client.aiohttp.WSMsgType.TEXT,
                                      data=json.dumps({"type": "done", "status": "completed"}))
                await asyncio.sleep(0)
                audio.play.assert_awaited_once_with(b"a" * 4800 + b"b" * 48000)
                self.received_while_playing = True

        socket = Socket()
        instance = client.Client(socket, resources, audio)
        instance.timing.released = client.time.monotonic()
        instance.busy = True
        playback = asyncio.create_task(instance.playback())
        try:
            with self.assertRaisesRegex(RuntimeError, "connection closed"):
                await instance.receive()
            self.assertTrue(socket.received_while_playing)
            self.assertTrue(instance.busy)
            release_playback.set()
            await asyncio.sleep(0)
            audio.finish.assert_awaited_once()
            self.assertFalse(instance.busy)
        finally:
            playback.cancel()
            await asyncio.gather(playback, return_exceptions=True)

    async def test_incomplete_short_and_oversized_replies_never_play(self):
        """A short incomplete reply waits; an oversized chunk fails before playback."""
        for size in (100, client.RATE * 2 * 300 + 2):
            class Socket:
                def __init__(self, payload_size):
                    self.payload_size = payload_size

                async def __aiter__(self):
                    yield SimpleNamespace(type=client.aiohttp.WSMsgType.BINARY,
                                          data=bytes(self.payload_size))

            audio = AsyncMock()
            instance = client.Client(Socket(size), Mock(), audio)
            instance.timing.released = client.time.monotonic()
            with self.assertRaises(RuntimeError):
                await instance.receive()
            audio.play.assert_not_awaited()
            self.assertFalse(instance.reply.done)

    async def test_three_second_reserve_starts_before_done(self):
        """Initial playback begins at three seconds without waiting for completion."""
        instance = client.Client(Mock(), Mock(), AsyncMock())
        reply = client.ReplyAudio()
        task = asyncio.create_task(instance.play_reply(reply))
        try:
            reply.pcm.extend(bytes(client.RATE * 2 * 2))
            reply.changed.set()
            await asyncio.sleep(0)
            instance.audio.play.assert_not_awaited()
            reply.pcm.extend(bytes(client.RATE * 2))
            reply.changed.set()
            await asyncio.sleep(0)
            instance.audio.play.assert_awaited_once_with(bytes(client.RATE * 2 * 3))
            self.assertFalse(reply.done)
            reply.done = True
            reply.changed.set()
            await task
            instance.audio.finish.assert_awaited_once()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_starvation_refills_larger_reserve_without_losing_samples(self):
        """A drained stream waits for four seconds and preserves every PCM byte."""
        instance = client.Client(Mock(), Mock(), AsyncMock())
        reply = client.ReplyAudio()
        reply.pcm.extend(b"a" * (client.RATE * 2 * 3))
        async def timeout(waiter, _seconds):
            waiter.close()
            raise TimeoutError

        with patch.object(client.asyncio, "wait_for", side_effect=timeout):
            task = asyncio.create_task(instance.play_reply(reply))
            try:
                await asyncio.sleep(0)
                self.assertEqual(instance.buffer_seconds, 4)
                instance.audio.finish.assert_awaited_once()
                reply.pcm.extend(b"b" * (client.RATE * 2 * 3))
                reply.changed.set()
                await asyncio.sleep(0)
                self.assertEqual(instance.audio.play.await_count, 1)
                reply.pcm.extend(b"c" * (client.RATE * 2))
                reply.done = True
                reply.changed.set()
                await task
                self.assertEqual(instance.audio.play.await_args_list[1].args[0],
                                 b"b" * (client.RATE * 2 * 3) + b"c" * (client.RATE * 2))
                self.assertEqual(instance.buffer_seconds, 4)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_stable_long_reply_reduces_reserve_gradually(self):
        """Stable turns reduce the reserve by half a second, never below 1.5s."""
        instance = client.Client(Mock(), Mock(), AsyncMock())
        for expected in (2.5, 2, 1.5, 1.5):
            reply = client.ReplyAudio()
            reply.total = client.RATE * 2 * 10
            reply.pcm.extend(bytes(reply.total))
            reply.done = True
            await instance.play_reply(reply)
            self.assertEqual(instance.buffer_seconds, expected)

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
