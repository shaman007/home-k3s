import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "backfill", ROOT / "tools/longhorn/backfill-recurring-security.py"
)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
spec = importlib.util.spec_from_file_location(
    "fixtures", ROOT / "tools/longhorn/test-recurring-security-policy.py"
)
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


class RecurringSecurityTests(unittest.TestCase):
    def setUp(self):
        self.policy, self.binding = yaml.safe_load_all(
            (ROOT / "longhorn/policy-recurring-job-security.yaml").read_text()
        )
        self.bundle = list(
            yaml.safe_load_all((ROOT / "longhorn/recurring-job-security-backfill.yaml").read_text())
        )
        self.names = self.policy["spec"]["matchConstraints"]["resourceRules"][0]["resourceNames"]

    def test_scope_and_backfill_permissions_are_exact(self):
        declared = {
            d["metadata"]["name"]
            for d in yaml.safe_load_all(
                (ROOT / "longhorn/recurring-jobs-proposed.yaml").read_text()
            )
            if d and d.get("kind") == "RecurringJob"
        }
        self.assertEqual(set(self.names), declared)
        role = next(d for d in self.bundle if d["kind"] == "Role")
        self.assertEqual(
            role["rules"],
            [
                {
                    "apiGroups": ["batch"],
                    "resources": ["cronjobs"],
                    "resourceNames": self.names,
                    "verbs": ["get", "patch"],
                }
            ],
        )
        self.assertEqual(
            self.binding["spec"]["matchResources"]["namespaceSelector"]["matchLabels"],
            {"kubernetes.io/metadata.name": "longhorn-system"},
        )
        self.assertEqual(self.policy["spec"]["failurePolicy"], "Ignore")
        self.assertEqual(
            self.policy["spec"]["matchConstraints"]["resourceRules"][0]["resources"], ["cronjobs"]
        )

    def test_embedded_program_and_names_match_sources(self):
        data = next(d["data"] for d in self.bundle if d["kind"] == "ConfigMap")
        self.assertEqual(
            data["backfill.py"],
            (ROOT / "tools/longhorn/backfill-recurring-security.py").read_text(),
        )
        self.assertEqual(json.loads(data["names.json"]), self.names)

    def test_backfill_only_sends_guarded_annotation_patch(self):
        doc = f.fixture(self.names[0])
        doc["metadata"]["resourceVersion"] = "123"
        patch = b.annotation_patch(doc)
        self.assertEqual(
            patch[0], {"op": "test", "path": "/metadata/resourceVersion", "value": "123"}
        )
        self.assertTrue(all(p["path"].startswith("/metadata/") for p in patch))
        self.assertEqual(patch[-1]["value"], "v1")

    def test_no_live_write_when_any_preflight_has_no_mutation(self):
        names = self.names[:2]
        calls = []

        class Response:
            def __init__(self, doc):
                self.doc = doc

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return json.dumps(self.doc).encode()

        class Opener:
            def open(self, req, **kwargs):
                calls.append((req.method, req.full_url))
                name = req.full_url.split("/cronjobs/")[1].split("?")[0]
                doc = f.fixture(name)
                doc["metadata"]["resourceVersion"] = "123"
                if req.method == "PATCH" and name == names[0]:
                    doc["spec"] = b.expected_spec(doc)
                return Response(doc)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "names.json").write_text(json.dumps(names))
            (root / "token").write_text("synthetic-test-only")
            with (
                patch.object(b.ssl, "create_default_context"),
                patch.object(b.urllib.request, "build_opener", return_value=Opener()),
                patch.dict(
                    b.os.environ,
                    {"KUBERNETES_SERVICE_HOST": "mock.invalid", "KUBERNETES_SERVICE_PORT": "443"},
                ),
                patch.object(b.time, "sleep"),
            ):
                with self.assertRaisesRegex(AssertionError, "mutation absent"):
                    b.main(config_dir=root, account=root)
        self.assertTrue(any(method == "PATCH" for method, url in calls))
        self.assertTrue(all("dryRun=All" in url for method, url in calls if method == "PATCH"))


if __name__ == "__main__":
    unittest.main()
