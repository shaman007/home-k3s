"""Regression checks for Realtime session configuration and durable usage."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'aiy-voice'))

SPEC = importlib.util.spec_from_file_location('voice_server', Path(__file__).resolve().parents[1] / 'aiy-voice/server.py')
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class VoiceTests(unittest.TestCase):
    def test_push_to_talk_and_native_audio(self):
        config = server.session_config()['session']
        self.assertIsNone(config['audio']['input']['turn_detection'])
        self.assertEqual(config['audio']['output']['format']['rate'], 24000)
        self.assertEqual(config['output_modalities'], ['audio'])
        self.assertEqual({t['name'] for t in config['tools']}, {'search_web', 'search_memory', 'blink_light', 'set_timer', 'list_timers', 'cancel_timer', 'device_status', 'set_volume', 'adjust_volume'})

    def test_ledger_is_durable_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'usage.sqlite3')
            ledger = server.Ledger(path)
            response = {'id': 'r1', 'status': 'completed', 'usage': {'input_tokens': 100}}
            ledger.record(response, 900)
            ledger.record(response, 900)
            ledger.db.close()
            reopened = server.Ledger(path)
            rows = reopened.rows()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['usage'], {'input_tokens': 100})
            self.assertEqual(rows[0]['first_audio_ms'], 900)
            reopened.db.close()


class CostTests(unittest.TestCase):
    def test_cached_audio_and_text_are_not_double_counted(self):
        spec = importlib.util.spec_from_file_location('usage_cost', Path(__file__).resolve().parents[1] / 'aiy-voice/usage_cost.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        usage = {'input_token_details': {'text_tokens': 100, 'audio_tokens': 200,
                 'cached_tokens': 150, 'cached_tokens_details': {'text_tokens': 50, 'audio_tokens': 100}},
                 'output_token_details': {'text_tokens': 20, 'audio_tokens': 40}}
        self.assertEqual(str(module.cost(usage)), '0.0065')

class BridgeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_stream_before_done_and_persist_usage(self):
        import asyncio
        import base64
        import json
        import os
        from unittest.mock import patch
        from aiohttp import web, ClientSession, WSMsgType
        from aiohttp.test_utils import TestServer, TestClient
        released = asyncio.Event()
        received = bytearray()

        async def provider(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for message in ws:
                event = json.loads(message.data)
                if event['type'] == 'session.update':
                    await ws.send_json({'type': 'session.updated'})
                elif event['type'] == 'input_audio_buffer.append':
                    received.extend(base64.b64decode(event['audio']))
                elif event['type'] == 'response.create':
                    await ws.send_json({'type': 'response.output_audio.delta', 'delta': base64.b64encode(b'\x01\x02' * 100).decode()})
                    await released.wait()
                    await ws.send_json({'type': 'response.done', 'response': {'id': 'integration-1', 'status': 'completed', 'usage': {'input_tokens': 42}}})
            return ws

        fake = web.Application()
        fake.router.add_get('/realtime', provider)
        async with TestServer(fake) as upstream, ClientSession() as transport:
            class RedirectProvider:
                def ws_connect(self, _url, **kwargs):
                    return transport.ws_connect(upstream.make_url('/realtime'), **kwargs)
                async def close(self):
                    pass
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'OPENAI_API_KEY': 'fake', 'AIY_BEARER_TOKEN': 'x' * 48}):
                app = server.create_app(str(Path(directory) / 'usage.sqlite3'))
                async with TestClient(TestServer(app)) as device:
                    original = app['http']
                    app['http'] = RedirectProvider()
                    await original.close()
                    response = await device.get('/v1/usage')
                    self.assertEqual(response.status, 401)
                    headers = {'Authorization': 'Bearer ' + 'x' * 48}
                    async with device.ws_connect('/v1/voice', headers=headers) as ws:
                        self.assertEqual((await ws.receive_json())['type'], 'ready')
                        await ws.send_json({'type': 'start'})
                        pcm = b'\x00\x00' * 6000
                        await ws.send_bytes(pcm)
                        await ws.send_json({'type': 'stop'})
                        first = await asyncio.wait_for(ws.receive(), 2)
                        self.assertEqual(first.type, WSMsgType.BINARY)
                        self.assertEqual(bytes(received), pcm)
                        self.assertFalse(released.is_set())
                        released.set()
                        self.assertEqual((await ws.receive_json())['status'], 'completed')
                    response = await device.get('/v1/usage', headers=headers)
                    self.assertEqual((await response.json())['responses'][0]['usage']['input_tokens'], 42)


if __name__ == '__main__':
    unittest.main()
