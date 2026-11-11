"""Plex probes must reject XML declarations before expanding entities or reading files."""

import importlib.util
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/security"))
SPEC = importlib.util.spec_from_file_location(
    "plex_probe", ROOT / "tools/security/test_plex_capability_guards.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class PlexXmlTests(unittest.TestCase):
    """Preserve normal identity/preferences parsing while refusing hostile XML."""

    def test_expected_plex_documents_keep_attributes(self):
        """Read identity and escaped preference values without changing their meaning."""
        for xml in [
            '<MediaContainer machineIdentifier="synthetic"/>',
            '<Preferences customConnections="https://fixture.invalid/?a=1&amp;b=2"/>',
        ]:
            result = probe.parse_xml(xml)
            self.assertIn(result.tag, {"MediaContainer", "Preferences"})
            self.assertTrue(result.attrib)

    def test_dtds_entities_and_malformed_xml_are_sanitized(self):
        """Reject internal/external entities without opening resources or echoing payloads."""
        marker = secrets.token_urlsafe(18)
        documents = [
            "<!DOCTYPE MediaContainer><MediaContainer/>",
            f'<!DOCTYPE x [<!ENTITY private "{marker}">]><x>&private;</x>',
            '<!DOCTYPE x [<!ENTITY private SYSTEM "file:///etc/passwd">]><x>&private;</x>',
            "<MediaContainer>",
        ]
        for document in documents:
            with self.subTest(document=document), patch("builtins.open") as opened:
                with self.assertRaises(RuntimeError) as caught:
                    probe.parse_xml(document)
                self.assertNotIn(marker, str(caught.exception))
                self.assertNotIn("/etc/passwd", str(caught.exception))
                opened.assert_not_called()

    def test_oversized_documents_are_rejected_before_parsing(self):
        """Bound parser input even when the document contains no entity declarations."""
        with patch.object(probe.ElementTree, "fromstring") as parse:
            with self.assertRaisesRegex(RuntimeError, "response limit"):
                probe.parse_xml("x" * (1024 * 1024 + 1))
            parse.assert_not_called()
