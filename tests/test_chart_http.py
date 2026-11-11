"""Pinned chart downloads must stay on authenticated TLS transport."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.request

from http_fixture import fixture_opener

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("chart_http", ROOT / "tools/ci/http_download.py")
http = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(http)


class ChartHttpTests(unittest.TestCase):
    """Exercise HTTPS redirects and reject downgrade or non-network targets."""

    def test_invalid_initial_targets_never_create_transport(self):
        """Refuse HTTP, file URLs, credentials, nonstandard ports and fragments."""
        for url in [
            "http://fixture.invalid",
            "file:///etc/passwd",
            "https://user:private@fixture.invalid",
            "https://fixture.invalid:8443",
            "https://fixture.invalid:bad",
            "https://fixture.invalid#private",
        ]:
            with self.subTest(url=url), patch.object(urllib.request, "build_opener") as build:
                with self.assertRaises(ValueError):
                    http.fetch(url)
                build.assert_not_called()

    def test_safe_signed_https_redirects_still_download(self):
        """Keep cross-host signed GitHub release downloads usable over HTTPS."""
        url = "https://api.github.com/fixture"
        for status in (301, 302, 303, 307, 308):
            target = "https://release-assets.githubusercontent.com/fixture?signature=synthetic"
            visits, buffers = [], []
            with (
                self.subTest(status=status),
                patch.object(
                    urllib.request,
                    "build_opener",
                    side_effect=fixture_opener(url, status, visits, buffers, target),
                ),
            ):
                self.assertEqual(http.fetch(url, "application/octet-stream"), b"{}")
            self.assertEqual(visits, [url, target])
            self.assertTrue(all(body.closed for body in buffers))

    def test_redirect_downgrades_close_before_second_request(self):
        """Reject HTTP, file and credential-bearing destinations through real dispatch."""
        url = "https://api.github.com/fixture"
        for target in [
            "http://elsewhere.invalid/fixture",
            "file:///etc/passwd",
            "https://user:private@fixture.invalid/fixture",
        ]:
            for status in (301, 302, 303, 307, 308):
                visits, buffers = [], []
                with (
                    self.subTest(target=target, status=status),
                    patch.object(
                        urllib.request,
                        "build_opener",
                        side_effect=fixture_opener(url, status, visits, buffers, target),
                    ),
                ):
                    with self.assertRaises(ValueError):
                        http.fetch(url)
                self.assertEqual(visits, [url])
                self.assertTrue(all(body.closed for body in buffers))
