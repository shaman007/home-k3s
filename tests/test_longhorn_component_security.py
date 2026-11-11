"""Verify Longhorn component mutation scope, storage health gates, and rollout safety."""

import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location(
    "backfill", ROOT / "tools/longhorn/backfill_component_security.py"
)
b = importlib.util.module_from_spec(s)
s.loader.exec_module(b)


class ComponentSecurityTests(unittest.TestCase):
    """Verify component mutation identity, healthy storage gates, and guarded rollout."""

    def setUp(self):
        self.catalog = json.loads((ROOT / "longhorn/component-security-catalog.json").read_text())
        self.entries = self.catalog["entries"]
        self.policy, self.binding = yaml.safe_load_all(
            (ROOT / "longhorn/policy-component-security.yaml").read_text()
        )
        self.bundle = list(
            yaml.safe_load_all((ROOT / "longhorn/component-security-backfill.yaml").read_text())
        )

    def healthy(self, entry):
        """Build healthy workload state for the backfill preflight."""
        doc = copy.deepcopy(entry["fixture"])
        doc["metadata"].update(generation=1, resourceVersion="123")
        if doc["kind"] == "Deployment":
            n = doc["spec"].get("replicas", 1)
            doc["status"] = {
                "observedGeneration": 1,
                "updatedReplicas": n,
                "replicas": n,
                "readyReplicas": n,
                "availableReplicas": n,
            }
        else:
            doc["status"] = {
                "observedGeneration": 1,
                "desiredNumberScheduled": 3,
                "updatedNumberScheduled": 3,
                "numberReady": 3,
                "numberAvailable": 3,
            }
        return doc

    def test_exact_scope_and_namespace_rbac(self):
        """Verify exact scope and namespace RBAC."""
        self.assertEqual(
            {e["name"] for e in self.entries},
            {
                "csi-attacher",
                "csi-provisioner",
                "csi-resizer",
                "csi-snapshotter",
                "longhorn-ui",
                "longhorn-csi-plugin",
                "longhorn-global-manager",
                "longhorn-manager",
            },
        )
        rules = next(d for d in self.bundle if d["kind"] == "Role")["rules"]
        self.assertEqual(
            rules[-1],
            {"apiGroups": ["longhorn.io"], "resources": ["volumes", "nodes"], "verbs": ["list"]},
        )
        for rule in rules[:-1]:
            self.assertEqual(rule["verbs"], ["get", "patch"])
            self.assertEqual(rule["apiGroups"], ["apps"])
            expected = [
                e["name"]
                for e in self.entries
                if ("deployments" if e["kind"] == "Deployment" else "daemonsets")
                in rule["resources"]
            ]
            self.assertEqual(rule["resourceNames"], expected)
        self.assertEqual(self.policy["spec"]["failurePolicy"], "Ignore")
        self.assertEqual(
            self.binding["spec"]["matchResources"]["namespaceSelector"]["matchLabels"],
            {"kubernetes.io/metadata.name": "longhorn-system"},
        )
        annotation = yaml.safe_load((ROOT / "argocd/application-longhorn.yaml").read_text())[
            "metadata"
        ]["annotations"]["argocd.argoproj.io/compare-options"]
        self.assertEqual(annotation, "ServerSideDiff=true,IncludeMutationWebhook=true")

    def test_only_selected_container_changes(self):
        """Verify only selected container changes."""
        for entry in self.entries:
            doc = copy.deepcopy(entry["fixture"])
            b.reviewed(doc, entry)
            spec = b.expected_spec(doc, entry)
            old = doc["spec"]["template"]["spec"]["containers"]
            for i, c in enumerate(spec["template"]["spec"]["containers"]):
                if i != entry["index"]:
                    self.assertEqual(c, old[i])
            restored = copy.deepcopy(spec)
            if "securityContext" in old[entry["index"]]:
                restored["template"]["spec"]["containers"][entry["index"]]["securityContext"] = old[
                    entry["index"]
                ]["securityContext"]
            else:
                restored["template"]["spec"]["containers"][entry["index"]].pop("securityContext")
            self.assertEqual(restored, doc["spec"])
            sc = spec["template"]["spec"]["containers"][entry["index"]]["securityContext"]
            self.assertEqual(
                sc["runAsUser"],
                {
                    "longhorn-ui": 499,
                    "longhorn-global-manager": 1000,
                    "longhorn-manager": 65534,
                }.get(entry["name"], 0),
            )
            self.assertEqual(
                sc["runAsNonRoot"],
                entry["name"] in ["longhorn-ui", "longhorn-global-manager", "longhorn-manager"],
            )

    def test_rollout_readiness_requires_updated_generation_and_all_replicas(self):
        """Verify rollout readiness requires updated generation and all replicas."""
        for entry in self.entries:
            doc = self.healthy(entry)
            self.assertTrue(b.ready(doc))
            doc["metadata"]["generation"] = 2
            self.assertFalse(b.ready(doc))
            fields = (
                ["updatedReplicas", "replicas", "readyReplicas", "availableReplicas"]
                if entry["kind"] == "Deployment"
                else ["updatedNumberScheduled", "numberReady", "numberAvailable"]
            )
            for field in fields:
                with self.subTest(workload=entry["name"], field=field):
                    doc = self.healthy(entry)
                    doc["status"].pop(field)
                    self.assertFalse(b.ready(doc))
                    doc["status"][field] = 0
                    self.assertFalse(b.ready(doc))
            doc = self.healthy(entry)
            if entry["kind"] == "Deployment":
                doc["spec"]["replicas"] = 0
            else:
                doc["status"]["desiredNumberScheduled"] = 0
            for field in fields:
                doc["status"][field] = 0
            self.assertFalse(b.ready(doc))

    def test_failed_preflight_writes_nothing(self):
        """Verify failed preflight writes nothing."""
        entries = self.entries[:2]
        calls = []
        outer = self

        class Response:
            """Provide a context-managed synthetic response for isolated API-client tests."""

            def __init__(self, doc):
                self.doc = doc

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                """Encode the simulated API response as JSON bytes."""
                return json.dumps(self.doc).encode()

        def open_request(req, **_kwargs):
            """Record the request and return the simulated API response."""
            calls.append((req.method, req.full_url))
            entry = next((e for e in entries if "/" + e["name"] in req.full_url))
            doc = outer.healthy(entry)
            if req.method == "PATCH" and entry == entries[0]:
                doc["spec"] = b.expected_spec(doc, entry)
            return Response(doc)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "catalog.json").write_text(json.dumps({"entries": entries}))
            (root / "token").write_text("synthetic-test-only")
            with (
                patch.object(b.ssl, "create_default_context"),
                patch.object(
                    b.urllib.request,
                    "build_opener",
                    return_value=SimpleNamespace(open=open_request),
                ),
                patch.dict(
                    b.os.environ,
                    {"KUBERNETES_SERVICE_HOST": "mock.invalid", "KUBERNETES_SERVICE_PORT": "443"},
                ),
                patch.object(b.time, "sleep"),
            ):
                with self.assertRaisesRegex(AssertionError, "absent admission mutation"):
                    b.main(root, root)
        self.assertTrue(all("dryRun=All" in url for method, url in calls if method == "PATCH"))

    def test_failed_rollout_does_not_patch_later_targets(self):
        """Verify failed rollout does not patch later targets."""
        entries = self.entries[:2]
        live = []
        outer = self

        class Response:
            """Provide a context-managed synthetic response for isolated API-client tests."""

            def __init__(self, doc):
                self.doc = doc

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                """Encode the simulated API response as JSON bytes."""
                return json.dumps(self.doc).encode()

        def open_request(req, **_kwargs):
            """Record the request and return the simulated API response."""
            entry = next((e for e in entries if "/" + e["name"] in req.full_url))
            doc = outer.healthy(entry)
            if req.method == "PATCH":
                doc["spec"] = b.expected_spec(doc, entry)
                if "dryRun=All" not in req.full_url:
                    live.append(entry["name"])
            if entry["name"] in live:
                doc["spec"] = b.expected_spec(doc, entry)
                doc["metadata"]["generation"] = 2
            return Response(doc)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "catalog.json").write_text(json.dumps({"entries": entries}))
            (root / "token").write_text("synthetic-test-only")
            with (
                patch.object(b.ssl, "create_default_context"),
                patch.object(
                    b.urllib.request,
                    "build_opener",
                    return_value=SimpleNamespace(open=open_request),
                ),
                patch.dict(
                    b.os.environ,
                    {"KUBERNETES_SERVICE_HOST": "mock.invalid", "KUBERNETES_SERVICE_PORT": "443"},
                ),
                patch.object(b.time, "sleep"),
                patch.object(b.time, "monotonic", side_effect=[0, 301]),
            ):
                with self.assertRaisesRegex(RuntimeError, "later targets were not changed"):
                    b.main(root, root)
        self.assertEqual(live, [entries[0]["name"]])

    def test_backfill_only_patches_metadata_with_concurrency_guard(self):
        """Verify backfill only patches metadata with concurrency guard."""
        changes = b.annotation_patch(self.healthy(self.entries[0]))
        self.assertEqual(
            changes[0], {"op": "test", "path": "/metadata/resourceVersion", "value": "123"}
        )
        self.assertTrue(all(p["path"].startswith("/metadata/") for p in changes))
        data = next(d["data"] for d in self.bundle if d["kind"] == "ConfigMap")
        self.assertEqual(
            data["backfill.py"],
            (ROOT / "tools/longhorn/backfill_component_security.py").read_text(),
        )
        self.assertEqual(json.loads(data["catalog.json"]), self.catalog)

    def test_storage_gate_accepts_idle_detached_but_rejects_degradation(self):
        """Verify storage gate accepts idle detached but rejects degradation."""
        volumes = {
            "items": [
                {
                    "status": {
                        "state": "attached",
                        "robustness": "healthy",
                        "restoreRequired": False,
                    }
                },
                {
                    "status": {
                        "state": "detached",
                        "robustness": "unknown",
                        "restoreRequired": False,
                    }
                },
            ]
        }
        good = [{"type": "Ready", "status": "True"}, {"type": "Schedulable", "status": "True"}]
        nodes = {
            "items": [
                {"status": {"conditions": good, "diskStatus": {"disk": {"conditions": good}}}}
            ]
        }
        b.storage_healthy(volumes, nodes)
        for mutation in [
            "degraded",
            "faulted",
            "restoring",
            "transitioning",
            "node",
            "disk",
            "no-status",
        ]:
            v, n = copy.deepcopy(volumes), copy.deepcopy(nodes)
            if mutation in ["degraded", "faulted"]:
                v["items"][0]["status"]["robustness"] = mutation
            if mutation == "restoring":
                v["items"][0]["status"]["restoreRequired"] = True
            if mutation == "transitioning":
                v["items"][0]["status"]["state"] = "attaching"
            if mutation == "node":
                n["items"][0]["status"]["conditions"] = []
            if mutation == "disk":
                n["items"][0]["status"]["diskStatus"]["disk"]["conditions"] = []
            if mutation == "no-status":
                v["items"][0]["status"] = {}
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                b.storage_healthy(v, n)

    def test_manager_rollout_strategy_requires_chart_review(self):
        """Verify manager rollout strategy requires chart review."""
        app = yaml.safe_load((ROOT / "argocd/application-longhorn.yaml").read_text())
        chart = app["spec"]["sources"][0]
        values = yaml.safe_load(chart["helm"]["values"])
        review = self.catalog["managerRolloutReview"]
        self.assertEqual(
            chart["targetRevision"],
            review["chartVersion"],
            "Review rolling manager compatibility before a Longhorn chart upgrade",
        )
        self.assertEqual(
            values["longhornManager"]["updateStrategy"]["rollingUpdate"]["maxUnavailable"],
            review["maxUnavailable"],
        )
        entry = next(e for e in self.entries if e["name"] == "longhorn-manager")
        self.assertEqual(
            entry["fixture"]["spec"]["updateStrategy"]["rollingUpdate"]["maxUnavailable"],
            review["maxUnavailable"],
        )

    def test_unhealthy_storage_preflight_never_patches(self):
        """Verify unhealthy storage preflight never patches."""
        entry = next(e for e in self.entries if e["name"] == "longhorn-manager")
        calls = []

        class Response:
            """Provide a context-managed synthetic response for isolated API-client tests."""

            def __init__(self, doc):
                self.doc = doc

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                """Encode the simulated API response as JSON bytes."""
                return json.dumps(self.doc).encode()

        def open_request(req, **_kwargs):
            """Record the request and return the simulated API response."""
            calls.append(req.get_method())
            if req.full_url.endswith("/volumes"):
                return Response(
                    {
                        "items": [
                            {
                                "status": {
                                    "state": "attached",
                                    "robustness": "degraded",
                                    "restoreRequired": False,
                                }
                            }
                        ]
                    }
                )
            return Response({"items": []})

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "catalog.json").write_text(json.dumps({"entries": [entry]}))
            (root / "token").write_text("synthetic-test-only")
            with (
                patch.object(b.ssl, "create_default_context"),
                patch.object(
                    b.urllib.request,
                    "build_opener",
                    return_value=SimpleNamespace(open=open_request),
                ),
                patch.dict(
                    b.os.environ,
                    {"KUBERNETES_SERVICE_HOST": "mock.invalid", "KUBERNETES_SERVICE_PORT": "443"},
                ),
                patch.object(b.time, "sleep"),
            ):
                with self.assertRaises(AssertionError):
                    b.main(root, root)
        self.assertTrue(calls)
        self.assertEqual(set(calls), {"GET"})

    def test_http_failure_is_sanitized_and_response_closed(self):
        """A failed workload read closes its body without exposing private diagnostics."""
        entry = next(e for e in self.entries if e["name"] != "longhorn-manager")
        body = io.BytesIO(b"private-fixture-response")
        error = b.urllib.error.HTTPError("https://mock.invalid/private", 503, "private", {}, body)
        opener = MagicMock()
        opener.open.side_effect = error
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "catalog.json").write_text(json.dumps({"entries": [entry]}))
            (root / "token").write_text("synthetic-test-only")
            with (
                patch.object(b.ssl, "create_default_context"),
                patch.object(b.urllib.request, "build_opener", return_value=opener),
                patch.dict(
                    b.os.environ,
                    {"KUBERNETES_SERVICE_HOST": "mock.invalid", "KUBERNETES_SERVICE_PORT": "443"},
                ),
            ):
                with self.assertRaises(RuntimeError) as caught:
                    b.main(root, root)
        self.assertEqual(str(caught.exception), entry["name"] + ": Kubernetes HTTP 503")
        self.assertTrue(body.closed)
        opener.open.assert_called_once()
        self.assertEqual(opener.open.call_args.args[0].get_method(), "GET")


if __name__ == "__main__":
    unittest.main()
