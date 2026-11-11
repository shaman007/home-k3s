"""Exercise Firefox Sync secret bootstrap and scoped authentication prerequisites."""

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch
from contextlib import nullcontext, redirect_stdout

from http_fixture import fixture_opener

sys.path.insert(0, str(Path(__file__).parents[1] / "tools/firefox-sync"))
SPEC = importlib.util.spec_from_file_location(
    "firefox_sync_bootstrap",
    Path(__file__).parents[1] / "tools/firefox-sync/bootstrap-secrets.py",
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class Response:
    """Provide a context-managed synthetic response for isolated API-client tests."""

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        """Encode the simulated API response document as JSON bytes."""
        return json.dumps(self.data).encode()


class BootstrapTests(unittest.TestCase):
    """Preserve existing secrets and scoped auth bindings during Firefox Sync bootstrap."""

    def run_bootstrap(self, handler, token="hvs.fake-test-token\nnot-a-token\n"):
        """Execute bootstrap with a temporary token file and mocked HTTP transport."""
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "token"
            token_path.write_text(token)
            request = (
                patch.object(bootstrap.Transport, "open", side_effect=handler)
                if handler is not None
                else nullcontext()
            )
            with (
                patch.object(bootstrap, "TOKEN_FILE", token_path),
                patch("sys.argv", ["bootstrap", "--execute"]),
                request,
                redirect_stdout(io.StringIO()) as output,
            ):
                bootstrap.main()
                return output.getvalue()

    def test_plan_has_no_network_access(self):
        """Verify plan has no network access."""
        with (
            patch("sys.argv", ["bootstrap"]),
            patch.object(bootstrap, "Transport") as request,
            redirect_stdout(io.StringIO()),
        ):
            bootstrap.main()
            request.assert_not_called()

    def test_preserves_existing_credentials_and_selects_only_token_line(self):
        """Preserve existing credentials and ignore non-token lines in the token file."""
        seen = []
        existing = {key: "preserve-test-secret" for key in bootstrap.KEYS}

        def handler(request, **_kwargs):
            self.assertEqual(request.get_header("X-vault-token"), "hvs.fake-test-token")
            seen.append((request.method, request.full_url))
            return Response(
                {"data": {"data": existing}} if request.method == "GET" else {}
            )

        output = self.run_bootstrap(handler)
        self.assertNotIn("preserve-test-secret", output)
        self.assertNotIn("hvs.fake-test-token", output)
        self.assertEqual(
            [method for method, url in seen if "/kv/data/" in url], ["GET"]
        )
        self.assertEqual(len(seen), 3)

    def test_refuses_partial_existing_secret_without_writing(self):
        """Refuse partially populated existing credentials without writing a replacement."""
        calls = []

        def handler(request, **_kwargs):
            calls.append(request.method)
            return Response({"data": {"data": {"MYSQL_PASSWORD": "existing"}}})

        with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
            self.run_bootstrap(handler)
        self.assertEqual(calls, ["GET"])

    def test_transport_failure_cannot_expose_token_in_exception(self):
        """Verify transport failure cannot expose token in exception."""

        def handler(request, **kwargs):
            raise ValueError("invalid header hvs.fake-test-token")

        with self.assertRaises(RuntimeError) as error:
            self.run_bootstrap(handler)
        self.assertNotIn("hvs.fake-test-token", str(error.exception))
        self.assertIsNone(error.exception.__cause__)
        self.assertTrue(error.exception.__suppress_context__)

    def test_redirects_never_forward_the_bootstrap_token(self):
        """Exercise the real redirect dispatcher and stop before any second request."""
        url = bootstrap.ADDRESS + "/v1/kv/data/firefox-sync"
        for status in (301, 302, 303, 307, 308):
            visits, buffers = [], []
            with (
                self.subTest(status=status),
                patch.object(
                    bootstrap.urllib.request,
                    "build_opener",
                    side_effect=fixture_opener(url, status, visits, buffers),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, f"HTTP {status}") as caught:
                    self.run_bootstrap(None)
                self.assertNotIn("hvs.fake-test-token", str(caught.exception))
                self.assertEqual(visits, [url])
                self.assertTrue(all(body.closed for body in buffers))

    def test_missing_and_failed_http_responses_are_closed(self):
        """Preserve create-if-missing behavior while closing sanitized HTTP failures."""
        for status in (404, 500):
            body = io.BytesIO(b"private fixture response")
            error = bootstrap.urllib.error.HTTPError(
                "https://private.invalid", status, "private fixture response", {}, body
            )
            responses = iter(
                [error, io.BytesIO(b"{}"), io.BytesIO(b"{}"), io.BytesIO(b"{}")]
            )

            def handler(*_args, **_kwargs):
                response = next(responses)
                if isinstance(response, Exception):
                    raise response
                return response

            with self.subTest(status=status):
                if status == 404:
                    self.assertIn(
                        "Created dedicated Sync secrets", self.run_bootstrap(handler)
                    )
                else:
                    with self.assertRaisesRegex(RuntimeError, "HTTP 500") as caught:
                        self.run_bootstrap(handler)
                    self.assertNotIn("private", str(caught.exception))
                self.assertTrue(body.closed)


if __name__ == "__main__":
    unittest.main()
