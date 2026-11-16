"""Assist-only MCP bridge contracts; no physical home actions in unit tests."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'aiy-voice'))
import home_assistant as bridge


class HomeAssistantTests(unittest.IsolatedAsyncioTestCase):
    def test_tools_are_from_assist_and_not_administrative_api(self):
        self.assertTrue(bridge.URL.endswith('/api/mcp/assist'))
        definitions = bridge.schemas()
        self.assertEqual(len(definitions), 19)
        self.assertIn('ha_homeassistant__GetLiveContext', bridge.NAMES)
        self.assertIn('ha_intent__HassTurnOn', bridge.NAMES)
        self.assertTrue(all(item['name'].startswith('ha_') and len(item['name']) <= 64 for item in definitions))
        self.assertTrue(all(item['parameters']['type'] == 'object' for item in definitions))
        self.assertFalse(any('config' in name.lower() or 'call_service' in name.lower() for name in bridge.NAMES))

    async def test_unknown_tool_is_rejected_before_network_access(self):
        with patch.object(bridge, 'Client') as client:
            self.assertIn('error', await bridge.call_home_assistant('ha_delete_config', {}))
            client.assert_not_called()

    async def test_read_call_preserves_native_name_and_never_returns_token(self):
        remote = AsyncMock()
        remote.call_tool.return_value = Mock(is_error=False, structured_content={'light': 'on'}, content=[])
        mcp_context = AsyncMock(); mcp_context.__aenter__.return_value = remote
        http_context = AsyncMock()
        with patch.dict('os.environ', {'HOME_ASSISTANT_TOKEN': 'synthetic-credential'}), patch.object(bridge.httpx2, 'AsyncClient', return_value=http_context), patch.object(bridge, 'streamable_http_client'), patch.object(bridge, 'Client', return_value=mcp_context):
            result = await bridge.call_home_assistant('ha_homeassistant__GetLiveContext', {'domain': 'light'})
        remote.call_tool.assert_awaited_once_with('homeassistant__GetLiveContext', {'domain': 'light'})
        self.assertEqual(result['result']['light'], 'on')
        self.assertNotIn('synthetic-credential', json.dumps(result))
