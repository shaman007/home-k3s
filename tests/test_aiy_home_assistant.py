"""Assist-only MCP bridge contracts; no physical home actions in unit tests."""

import importlib
import json
import secrets
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))
bridge = importlib.import_module("home_assistant")


class HomeAssistantTests(unittest.IsolatedAsyncioTestCase):
    """Keep Assist tools allowlisted and credentials out of model-visible results."""

    def test_tools_are_from_assist_and_not_administrative_api(self):
        """Verify tools are from assist and not administrative api."""
        self.assertTrue(bridge.URL.endswith("/api/mcp/assist"))
        definitions = bridge.schemas()
        self.assertEqual(len(definitions), 19)
        self.assertIn("ha_homeassistant__GetLiveContext", bridge.NAMES)
        self.assertIn("ha_intent__HassTurnOn", bridge.NAMES)
        self.assertTrue(
            all(item["name"].startswith("ha_") and len(item["name"]) <= 64 for item in definitions)
        )
        self.assertTrue(all(item["parameters"]["type"] == "object" for item in definitions))
        self.assertFalse(
            any("config" in name.lower() or "call_service" in name.lower() for name in bridge.NAMES)
        )

    async def test_unknown_tool_is_rejected_before_network_access(self):
        """Verify unknown tool is rejected before network access."""
        with patch.object(bridge, "Client") as client:
            self.assertIn("error", await bridge.call_home_assistant("ha_delete_config", {}))
            client.assert_not_called()

    async def test_read_call_preserves_native_name_and_never_returns_token(self):
        """Verify read call preserves native name and never returns token."""
        credential = secrets.token_urlsafe(32)
        remote = AsyncMock()
        remote.call_tool.return_value = Mock(
            is_error=False, structured_content={"light": "on"}, content=[]
        )
        mcp_context = AsyncMock()
        mcp_context.__aenter__.return_value = remote
        http_context = AsyncMock()
        with patch.dict("os.environ", {"HOME_ASSISTANT_TOKEN": credential}), patch.object(
            httpx2, "AsyncClient", return_value=http_context
        ) as http_factory, patch.object(bridge, "streamable_http_client"), patch.object(
            bridge, "Client", return_value=mcp_context
        ):
            result = await bridge.call_home_assistant(
                "ha_homeassistant__GetLiveContext", {"domain": "light"}
            )
        self.assertFalse(http_factory.call_args.kwargs["follow_redirects"])
        self.assertFalse(http_factory.call_args.kwargs["trust_env"])
        self.assertEqual(http_factory.call_args.kwargs["timeout"], 20)
        remote.call_tool.assert_awaited_once_with(
            "homeassistant__GetLiveContext", {"domain": "light"}
        )
        self.assertEqual(result["result"]["light"], "on")
        self.assertNotIn(credential, json.dumps(result))

    async def test_sdk_errors_do_not_expose_credentials(self):
        """Even unexpected transport exceptions must produce only a sanitized error."""
        credential = secrets.token_urlsafe(32)
        with patch.dict("os.environ", {"HOME_ASSISTANT_TOKEN": credential}), patch.object(
            httpx2, "AsyncClient", side_effect=RuntimeError("Bearer " + credential)
        ):
            result = await bridge.call_home_assistant("ha_homeassistant__GetLiveContext", {})
        self.assertIn("error", result)
        self.assertNotIn(credential, json.dumps(result))
