"""Verify isolated FRR API discovery and resource scope without opening sockets."""

import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "frr_fixture_api", Path(__file__).resolve().parents[1] / "tools/security/frr_fixture_api.py"
)
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)


class FrrFixtureApiTests(unittest.TestCase):
    """Keep synthetic discovery accurate and unsupported resources absent."""

    def request(self, path):
        """Run the real handler against an in-memory response stream."""
        handler = api.Handler.__new__(api.Handler)
        handler.path = path
        handler.wfile = io.BytesIO()
        with (
            patch.object(handler, "send_response") as status,
            patch.object(handler, "send_header"),
            patch.object(handler, "end_headers"),
        ):
            handler.do_get()
        return status.call_args.args[0], json.loads(handler.wfile.getvalue())

    def test_discovery_preserves_resource_scope_and_status_verbs(self):
        """Node state stays cluster scoped while other resource kinds remain namespaced."""
        status, document = self.request("/apis/" + api.VERSION)
        self.assertEqual(status, 200)
        resources = {item["name"]: item for item in document["resources"]}
        self.assertEqual(len(resources), 2 * len(api.KINDS))
        for name in api.KINDS:
            with self.subTest(resource=name):
                self.assertEqual(resources[name]["namespaced"], name != "frrnodestates")
                self.assertEqual(resources[name + "/status"]["verbs"], ["get", "update", "patch"])

    def test_unknown_discovery_and_absent_resources_remain_not_found(self):
        """Discovery dispatch cannot turn unknown APIs or missing objects into successes."""
        for path in ("/apis/unknown/v1", "/apis/" + api.VERSION + "/bgpsessionstates/absent"):
            with self.subTest(path=path), patch.object(api, "STATE", {}), patch("builtins.print"):
                status, document = self.request(path)
            self.assertEqual(status, 404)
            self.assertEqual(document["reason"], "NotFound")
