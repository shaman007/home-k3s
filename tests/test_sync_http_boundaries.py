"""Keep Firefox Sync bootstrap and storage-probe credentials on reviewed origins."""

import base64
from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import secrets
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

from http_fixture import fixture_opener
from test_firefox_sync_bootstrap import bootstrap

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sync_storage_probe", ROOT / "tools/firefox-sync/verify_storage.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class SyncHttpBoundaryTests(unittest.TestCase):
    """Exercise actual redirect dispatch and reject invalid origins before secret access."""

    def test_invalid_origins_fail_before_opener_creation(self):
        """Reject ambiguous origins, remote HTTP, credentials, ports and URL suffixes."""
        urls = [
            "file:///etc/passwd",
            "http://sync.andreybondarenko.com",
            "https://sync.andreybondarenko.com.attacker.invalid",
            "https://sync.andreybondarenko.com:8443",
            "https://sync.andreybondarenko.com:invalid",
            "https://sync.andreybondarenko.com:0",
            "https://user:fixture@sync.andreybondarenko.com",
            "https://sync.andreybondarenko.com/path",
            "https://sync.andreybondarenko.com?fixture=true",
            "https://sync.andreybondarenko.com#fragment",
            "https://sync.andreybondarenko.com\n",
            "http://192.0.2.1:18000",
            "http://127.0.0.1:0",
        ]
        for url in urls:
            with (
                self.subTest(url=url),
                patch.object(urllib.request, "build_opener") as build,
            ):
                with self.assertRaises(ValueError):
                    bootstrap.Transport(url, {"sync.andreybondarenko.com"}, allow_loopback=True)
                build.assert_not_called()

    def test_requests_cannot_leave_the_configured_origin(self):
        """Reject cross-origin requests even when another HTTPS host is reviewed."""
        opener = MagicMock()
        with patch.object(urllib.request, "build_opener", return_value=opener):
            transport = bootstrap.Transport(
                bootstrap.ADDRESS,
                {"openbao.int.andreybondarenko.com", "sync.andreybondarenko.com"},
            )
        for url in [
            "https://sync.andreybondarenko.com/path",
            "file:///etc/passwd",
            "http://openbao.int.andreybondarenko.com/path",
            bootstrap.ADDRESS + ":8443/path",
            bootstrap.ADDRESS + "/path#fragment",
            "https://user:fixture@openbao.int.andreybondarenko.com/path",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                transport.open(urllib.request.Request(url))
        opener.open.assert_not_called()

    def test_redirect_dispatch_never_forwards_credentials(self):
        """Reject every redirect status for reads and writes on public and tunnel origins."""
        marker = secrets.token_urlsafe(18)
        origins = [
            bootstrap.ADDRESS,
            "https://sync.andreybondarenko.com",
            "http://127.0.0.1:18000",
        ]
        for origin in origins:
            for status in (301, 302, 303, 307, 308):
                for method in ("GET", "POST"):
                    url = origin + "/fixture"
                    for target in [
                        origin + "/elsewhere",
                        "https://elsewhere.invalid/collect",
                        "http://127.0.0.1:19000/collect",
                        "file:///etc/passwd",
                    ]:
                        visits, buffers = [], []
                        with (
                            self.subTest(
                                origin=origin,
                                status=status,
                                method=method,
                                target=target,
                            ),
                            patch.object(
                                urllib.request,
                                "build_opener",
                                side_effect=fixture_opener(url, status, visits, buffers, target),
                            ),
                        ):
                            transport = bootstrap.Transport(
                                origin,
                                {
                                    "openbao.int.andreybondarenko.com",
                                    "sync.andreybondarenko.com",
                                },
                                allow_loopback=True,
                            )
                            request = urllib.request.Request(
                                url,
                                data=b"{}" if method == "POST" else None,
                                method=method,
                                headers={
                                    "Authorization": marker,
                                    "X-Vault-Token": marker,
                                },
                            )
                            with self.assertRaises(urllib.error.HTTPError) as caught:
                                transport.open(request)
                            caught.exception.close()
                            self.assertEqual(visits, [url])
                            self.assertTrue(all(body.closed for body in buffers))

    def test_valid_request_preserves_headers_body_and_timeout(self):
        """Allow explicit default ports and tunnel requests without changing request data."""
        for origin in [bootstrap.ADDRESS + ":443", "http://localhost:18000"]:
            opener = MagicMock()
            response = io.BytesIO(b"{}")
            opener.open.return_value = response
            request = urllib.request.Request(origin + "/fixture?batch=true", data=b"{}")
            with patch.object(urllib.request, "build_opener", return_value=opener):
                transport = bootstrap.Transport(
                    origin, {"openbao.int.andreybondarenko.com"}, allow_loopback=True
                )
                with transport.open(request) as result:
                    self.assertIs(result, response)
            opener.open.assert_called_once_with(request, timeout=15)
            self.assertTrue(response.closed)

    def test_probe_rejects_invalid_origin_before_reading_secret(self):
        """Fail malformed ports and remote HTTP before invoking kubectl or transport."""
        for url in [
            "https://sync.andreybondarenko.com:invalid",
            "http://elsewhere.invalid",
        ]:
            with (
                self.subTest(url=url),
                patch("sys.argv", ["probe", "--url", url]),
                patch.object(probe.subprocess, "check_output") as secret,
                patch.object(urllib.request, "build_opener") as build,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                probe.main()
            secret.assert_not_called()
            build.assert_not_called()

    def test_probe_sanitizes_redirect_errors_and_closes_response(self):
        """Stop a redirected authenticated read before writing or forwarding its Hawk token."""
        body = io.BytesIO(secrets.token_bytes(18))
        error = urllib.error.HTTPError("https://elsewhere.invalid", 302, "private", {}, body)
        data = {"data": {"SYNC_MASTER_SECRET": base64.b64encode(secrets.token_bytes(32)).decode()}}
        with (
            patch("sys.argv", ["probe"]),
            patch.object(probe.subprocess, "check_output", return_value=json.dumps(data).encode()),
            patch.object(probe.Transport, "open", side_effect=error) as request,
            self.assertRaisesRegex(RuntimeError, "HTTP 302") as caught,
        ):
            probe.main()
        request.assert_called_once()
        self.assertNotIn("elsewhere.invalid", str(caught.exception))
        self.assertTrue(body.closed)


class SyncStorageCleanupTests(unittest.TestCase):
    """Keep synthetic storage probes conservative around writes and cleanup."""

    def test_existing_user_data_prevents_writes_and_deletes(self):
        """Never touch a synthetic identity that unexpectedly already has data."""
        with patch.object(probe, "check_batch") as batch:
            request = MagicMock(return_value=(200, b'{"bookmarks":1}'))
            with self.assertRaisesRegex(RuntimeError, "refusing to write or delete"):
                probe.check_storage(request, "/1.5/fixture")
        request.assert_called_once_with("GET", "/1.5/fixture/info/collections")
        batch.assert_not_called()

    def test_ambiguous_write_still_attempts_and_verifies_cleanup(self):
        """A write transport failure cannot skip deletion of potentially stored fixture data."""
        request = MagicMock(
            side_effect=[
                (200, b"{}"),
                RuntimeError("synthetic write failure"),
                (200, b""),
                (200, b"{}"),
            ]
        )
        with patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "synthetic write failure"):
                probe.check_storage(request, "/1.5/fixture")
        methods = [call.args[0] for call in request.call_args_list]
        self.assertEqual(methods, ["GET", "PUT", "DELETE", "GET"])
        self.assertEqual(request.call_args_list[-2].args, ("DELETE", "/1.5/fixture/storage"))
        self.assertEqual(request.call_args_list[-1].args, ("GET", "/1.5/fixture/info/collections"))

    def test_unverified_cleanup_remains_a_failure(self):
        """A failed write followed by remaining data must report cleanup failure."""
        request = MagicMock(
            side_effect=[
                (200, b"{}"),
                RuntimeError("synthetic write failure"),
                (200, b""),
                (200, b'{"bookmarks":1}'),
            ]
        )
        with self.assertRaisesRegex(RuntimeError, "cleanup could not be verified"):
            probe.check_storage(request, "/1.5/fixture")
