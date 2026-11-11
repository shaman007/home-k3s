"""Administrative HTTP clients must keep credentials on their reviewed services."""

import base64
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import secrets
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.parse
import urllib.request

from http_fixture import fixture_opener


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "admin_client", ROOT / "tools/provision-traefik-security.py"
)
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)


class AdministrativeHttpTests(unittest.TestCase):
    """Exercise origin checks and urllib's actual redirect dispatch without sockets."""

    def setUp(self):
        self.marker = secrets.token_urlsafe(18)

    def test_unreviewed_targets_fail_before_transport(self):
        """Reject alternate schemes, lookalike hosts, credentials, ports and fragments."""
        urls = [
            "file:///etc/passwd",
            "http://sso.andreybondarenko.com/admin/realms",
            "https://elsewhere.invalid/admin/realms",
            "https://sso.andreybondarenko.com.elsewhere.invalid/admin/realms",
            "https://sso.andreybondarenko.com:8443/admin/realms",
            "https://sso.andreybondarenko.com:invalid/admin/realms",
            "https://operator:fixture@sso.andreybondarenko.com/admin/realms",
            "https://sso.andreybondarenko.com/admin/realms#fragment",
        ]
        for url in urls:
            with (
                self.subTest(url=url),
                patch.object(client.urllib.request, "build_opener") as build,
            ):
                with self.assertRaises(RuntimeError):
                    client.request(
                        url, headers={"Authorization": "Bearer " + self.marker}
                    )
                build.assert_not_called()

    def test_credential_headers_cannot_cross_services(self):
        """Reject Keycloak headers on OpenBao and OpenBao headers on Keycloak."""
        cases = [
            (client.BAO + "/v1/sys/health", {"Authorization": "Bearer " + self.marker}),
            (client.SSO + "/admin/realms", {"X-Vault-Token": self.marker}),
        ]
        for url, headers in cases:
            with (
                self.subTest(url=url),
                patch.object(client.urllib.request, "build_opener") as build,
            ):
                with self.assertRaisesRegex(RuntimeError, "does not match its service"):
                    client.request(url, headers=headers)
                build.assert_not_called()

    def test_redirects_never_forward_credentials_or_replay_writes(self):
        """Use real redirect processing with an in-memory HTTPS handler to detect forwarding."""
        cases = [
            (client.SSO + "/admin/realms", {"Authorization": "Bearer " + self.marker}),
            (client.BAO + "/v1/kv/data/fixture", {"X-Vault-Token": self.marker}),
        ]
        for base, headers in cases:
            for status in (301, 302, 303, 307, 308):
                for method in ("GET", "POST"):
                    url = base + "?private=" + self.marker
                    visits, buffers = [], []

                    with (
                        self.subTest(base=base, status=status, method=method),
                        patch.object(
                            client.urllib.request,
                            "build_opener",
                            side_effect=fixture_opener(url, status, visits, buffers),
                        ),
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, f"HTTP {status}"
                        ) as caught:
                            client.request(
                                url,
                                method=method,
                                data={"fixture": True} if method == "POST" else None,
                                headers=headers,
                            )
                        self.assertNotIn(self.marker, str(caught.exception))
                        self.assertEqual(visits, [url])
                        self.assertTrue(all(body.closed for body in buffers))

    def test_valid_request_preserves_method_body_headers_and_timeout(self):
        """Keep normal JSON requests usable on the explicit default HTTPS port."""
        opener = MagicMock()
        response = io.BytesIO(b'{"ok":true}')
        opener.open.return_value = response
        url = client.BAO + ":443/v1/kv/data/fixture"
        with patch.object(client.urllib.request, "build_opener", return_value=opener):
            result = client.request(
                url,
                method="POST",
                data={"data": {"fixture": True}},
                headers={"X-Vault-Token": self.marker},
            )
        self.assertEqual(result, {"ok": True})
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, url)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(json.loads(req.data), {"data": {"fixture": True}})
        self.assertEqual(req.get_header("X-vault-token"), self.marker)
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 20})
        self.assertTrue(response.closed)

    def test_missing_and_failed_responses_close_without_echoing_private_details(self):
        """Preserve optional 404 handling and sanitize errors without retaining bodies."""
        for status, missing in ((404, True), (404, False), (500, True)):
            url = client.BAO + "/v1/kv/data/fixture?private=" + self.marker
            body = io.BytesIO(self.marker.encode())
            error = urllib.error.HTTPError(url, status, self.marker, Message(), body)
            opener = MagicMock()
            opener.open.side_effect = error
            with (
                self.subTest(status=status, missing=missing),
                patch.object(
                    client.urllib.request, "build_opener", return_value=opener
                ),
            ):
                if status == 404 and missing:
                    self.assertIsNone(client.request(url, missing=missing))
                else:
                    with self.assertRaises(RuntimeError) as caught:
                        client.request(url, missing=missing)
                    self.assertNotIn(self.marker, str(caught.exception))
                self.assertTrue(body.closed)

    def test_keycloak_login_uses_the_guarded_transport(self):
        """Route the password grant through the same origin and redirect controls."""
        credentials = {
            "data": {
                "username": base64.b64encode(b"fixture-user").decode(),
                "password": base64.b64encode(self.marker.encode()).decode(),
            }
        }
        response = io.BytesIO(json.dumps({"access_token": self.marker}).encode())
        with (
            patch.object(
                client.subprocess,
                "run",
                return_value=SimpleNamespace(stdout=json.dumps(credentials).encode()),
            ),
            patch.object(client, "open_request", return_value=response) as transport,
        ):
            self.assertEqual(client.keycloak_token(), self.marker)
        req = transport.call_args.args[0]
        self.assertEqual(
            req.full_url, client.SSO + "/realms/master/protocol/openid-connect/token"
        )
        self.assertEqual(req.get_method(), "POST")
        form = urllib.parse.parse_qs(req.data.decode())
        self.assertEqual(form["password"], [self.marker])
        self.assertEqual(form["username"], ["fixture-user"])
