"""Audio privacy and physical-button protocol regressions."""
import asyncio
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

SPEC = importlib.util.spec_from_file_location('voice_client', Path(__file__).resolve().parents[1] / 'aiy-voice/pi_client.py')
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)


class VoiceClientTests(unittest.IsolatedAsyncioTestCase):
    def test_origin_validation(self):
        for url in ['http://example.org', 'https://a:b@example.org', 'https://example.org/path', 'https://example.org?x=1']:
            with self.assertRaises(ValueError):
                client.voice_url(url)
        self.assertEqual(client.voice_url('https://example.org/'), 'wss://example.org/v1/voice')

    async def test_idle_audio_is_discarded(self):
        ws = AsyncMock()
        instance = client.Client(ws)
        source = asyncio.StreamReader()
        source.feed_data(b'\x00\x00' * 1000)
        source.feed_eof()
        with self.assertRaises(RuntimeError):
            await instance.capture(source)
        ws.send_bytes.assert_not_called()

    async def test_batched_gpio_edges_commit_exactly_once(self):
        ws = AsyncMock()
        instance = client.Client(ws)
        source = asyncio.StreamReader()
        source.feed_data(b'falling 23\nrising 23\n')
        source.feed_eof()
        with patch.object(client, 'led'), self.assertRaises(RuntimeError):
            await instance.buttons(source)
        self.assertEqual([call.args[0]['type'] for call in ws.send_json.call_args_list], ['start', 'stop'])
        self.assertFalse(instance.recording)
        self.assertTrue(instance.busy)


if __name__ == '__main__':
    unittest.main()
