"""Real libopus round trips, transport validation and gateway negotiation."""

import base64
import importlib
import json
import math
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import WSMsgType, web
from aiy_gateway_fixture import gateway, prompt_environment

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))
codec = importlib.import_module("opus_audio")
server = importlib.import_module("server")
client = importlib.import_module("pi_client")


class OpusTests(unittest.TestCase):
    """Exercise the native codec rather than mock compression or packet parsing."""

    def test_round_trip_chunk_boundaries_tail_and_compression(self):
        """Retain all sample time including tail while reducing payload over 14x."""
        encoder, decoder = codec.OpusEncoder(), codec.OpusDecoder()
        self.addCleanup(encoder.close)
        self.addCleanup(decoder.close)
        pcm = b"".join(struct.pack("<h", round(6000 * math.sin(i * 0.13)))
                       for i in range(codec.RATE * 2 + 101))
        wire = bytearray()
        for offset in range(0, len(pcm), 614):
            wire.extend(encoder.feed(pcm[offset:offset + 614]))
        wire.extend(encoder.finish())
        self.assertEqual(encoder.finish(), b"")
        # Split at real WebSocket batch boundaries (20 packets per batch).
        decoded = bytearray()
        offset = 0
        while offset < len(wire):
            end = offset
            for _ in range(20):
                if end == len(wire):
                    break
                end += 2 + struct.unpack_from("!H", wire, end)[0]
            decoded.extend(decoder.decode(bytes(wire[offset:end])))
            offset = end
        self.assertGreaterEqual(len(decoded), len(pcm))
        self.assertLess(len(decoded) - len(pcm), codec.FRAME_BYTES * 2)
        self.assertGreater(len(pcm) / len(wire), 14)
        samples = struct.unpack('<' + 'h' * (len(decoded) // 2), decoded)
        self.assertGreater(max(abs(value) for value in samples), 1000)
        encoder.reset()
        decoder.reset()
        self.assertEqual(encoder.feed(b""), b"")

    def test_invalid_frames_and_unaligned_pcm_fail_closed(self):
        """Malformed framing cannot request unbounded native output buffers."""
        decoder, encoder = codec.OpusDecoder(), codec.OpusEncoder()
        self.addCleanup(decoder.close)
        self.addCleanup(encoder.close)
        for wire in (b"", b"\x00", b"\x00\x00", b"\xff\xff", b"\x00\x10x"):
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                decoder.decode(wire)
        with self.assertRaises(ValueError):
            encoder.feed(b"x")


class OpusGatewayTests(unittest.IsolatedAsyncioTestCase):
    """Negotiate compressed downlink while upstream microphone remains PCM."""

    async def test_client_decodes_before_counting_adaptive_reserve(self):
        """Reserve duration and the turn limit count decoded PCM, not compressed bytes."""
        encoder = codec.OpusEncoder()
        self.addCleanup(encoder.close)
        wire = encoder.feed(bytes(48000)) + encoder.finish()

        class Socket:
            """Supply one encoded batch followed by connection closure."""

            # This fixture implements only the asynchronous iteration protocol.
            # pylint: disable=too-few-public-methods
            async def __aiter__(self):
                yield SimpleNamespace(type=WSMsgType.BINARY, data=wire)

        instance = client.Client(Socket(), Mock(), AsyncMock())
        instance.configure_audio("opus-24k-v1")
        self.addCleanup(instance.player.decoder.close)
        instance.timing.released = client.time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "connection closed"):
            await instance.receive()
        self.assertGreaterEqual(instance.player.reply.total, 48000)
        self.assertLess(len(wire), 4000)
        self.assertEqual(instance.player.buffer_seconds, 3)
        instance.player.audio.play.assert_not_awaited()

    async def test_negotiated_opus_stream_and_final_tail(self):
        """The real bridge emits decodable frames before done, then flushes its tail."""
        async def provider(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for message in ws:
                event = json.loads(message.data)
                if event["type"] == "session.update":
                    await ws.send_json({"type": "session.updated"})
                elif event["type"] == "response.create":
                    await ws.send_json({"type": "response.output_audio.delta",
                                        "delta": base64.b64encode(bytes(48002)).decode()})
                    await ws.send_json({"type": "response.done", "response": {
                        "id": "opus-test", "status": "completed", "usage": {}}})
            return ws

        with prompt_environment():
            async with gateway(server, provider) as (_app, device):
                headers = {"Authorization": "Bearer " + "x" * 48}
                async with device.ws_connect('/v1/voice?audio=opus', headers=headers) as ws:
                    self.assertEqual((await ws.receive_json())["audio_format"], "opus-24k-v1")
                    await ws.send_json({"type": "start"})
                    await ws.send_bytes(bytes(10000))
                    await ws.send_json({"type": "stop"})
                    decoder = codec.OpusDecoder()
                    try:
                        decoded, messages = bytearray(), 0
                        while True:
                            message = await ws.receive(timeout=5)
                            if message.type == WSMsgType.BINARY:
                                decoded.extend(decoder.decode(message.data))
                                messages += 1
                            else:
                                self.assertEqual(json.loads(message.data)["type"], "done")
                                break
                        self.assertEqual(messages, 2)
                        self.assertGreaterEqual(len(decoded), 48002)
                    finally:
                        decoder.close()
