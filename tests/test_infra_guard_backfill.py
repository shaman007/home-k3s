"""Verify infrastructure guard identity checks, preflight rejection, and guarded backfill."""

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location(
    "infra_backfill", ROOT / "tools/security/infra_guard_backfill.py"
)
b = importlib.util.module_from_spec(s)
s.loader.exec_module(b)
s = importlib.util.spec_from_file_location(
    "infra_generate", ROOT / "tools/security/generate-infra-guards.py"
)
g = importlib.util.module_from_spec(s)
s.loader.exec_module(g)


class InfrastructureGuardTests(unittest.TestCase):
    """Exercise exact workload scope, preflight failures, and guarded infrastructure backfill."""
    def setUp(self):
        self.catalog = json.loads((ROOT / "infra-guards/catalog.json").read_text())
        self.entries = self.catalog["entries"]

    def healthy(self, e):
        """Build healthy workload state for the backfill preflight."""
        doc = copy.deepcopy(e["fixture"])
        doc["metadata"].update(generation=1, resourceVersion="fixture")
        if e["kind"] == "Deployment":
            n = doc["spec"].get("replicas", 1)
            doc["status"] = {
                "observedGeneration": 1,
                **{
                    k: n
                    for k in ["replicas", "updatedReplicas", "readyReplicas", "availableReplicas"]
                },
            }
        else:
            doc["status"] = {
                "observedGeneration": 1,
                **{
                    k: 3
                    for k in [
                        "desiredNumberScheduled",
                        "updatedNumberScheduled",
                        "numberReady",
                        "numberAvailable",
                    ]
                },
            }
        return doc

    def test_exact_reviewed_scope(self):
        """Verify exact reviewed scope."""
        self.assertEqual(
            {(e["namespace"], e["name"]) for e in self.entries},
            {
                ("gpu-operator", "gpu-operator"),
                ("longhorn-system", "longhorn-driver-deployer"),
                ("gpu-operator", "gpu-feature-discovery"),
                ("gpu-operator", "nvidia-device-plugin-daemonset"),
            },
        )
        self.assertEqual(
            {t["name"] for e in self.entries for t in e["targets"]},
            {
                "gpu-operator",
                "longhorn-driver-deployer",
                "wait-longhorn-manager",
                "config-manager-init",
            },
        )
        self.assertEqual(sum(len(e["targets"]) for e in self.entries), 5)
        docs = g.generate(self.catalog)
        for role in [d for d in docs if d["kind"] == "Role"]:
            for rule in role["rules"]:
                if rule["apiGroups"] == ["longhorn.io"]:
                    self.assertEqual(role["metadata"]["namespace"], "longhorn-system")
                    self.assertEqual(rule["verbs"], ["list"])
                    self.assertEqual(rule["resources"], ["volumes", "nodes"])
                else:
                    self.assertEqual(rule["verbs"], ["get", "patch"])
                    self.assertEqual(rule["apiGroups"], ["apps"])
                    self.assertTrue(rule["resourceNames"])
                    self.assertNotIn("*", rule["resourceNames"])
        self.assertEqual(
            next(d for d in docs if d["kind"] == "MutatingAdmissionPolicy")["spec"][
                "failurePolicy"
            ],
            "Ignore",
        )

    def test_only_selected_contexts_change(self):
        """Verify only selected contexts change."""
        for e in self.entries:
            doc = self.healthy(e)
            b.reviewed(doc, e)
            after = b.expected_spec(doc, e)
            for section in ["containers", "initContainers"]:
                selected = {t["index"] for t in e["targets"] if t["section"] == section}
                for i, c in enumerate(after["template"]["spec"][section]):
                    if i not in selected:
                        self.assertEqual(c, doc["spec"]["template"]["spec"][section][i])
                    else:
                        target = next(
                            t for t in e["targets"] if t["section"] == section and t["index"] == i
                        )
                        for key, value in target["guards"].items():
                            self.assertEqual(c["securityContext"][key], value)
            # Native patch is idempotent even when unrelated context fields exist.
            doc["spec"] = after
            self.assertEqual(b.expected_spec(doc, e), after)

    def test_deployer_identity_has_no_persistent_volume_ownership_change(self):
        """Verify deployer identity has no persistent volume ownership change."""
        e = next(e for e in self.entries if e["name"] == "longhorn-driver-deployer")
        self.assertEqual(e["podGuards"]["fsGroup"], 1000)
        self.assertEqual(e["fixture"]["spec"]["template"]["spec"]["volumes"], [])
        self.assertTrue(
            all(
                not c["volumeMounts"]
                for section in ["containers", "initContainers"]
                for c in e["fixture"]["spec"]["template"]["spec"][section]
            )
        )
        self.assertTrue(all(t["guards"]["runAsUser"] == 1000 for t in e["targets"]))

    def test_incomplete_rollout_not_ready(self):
        """Verify incomplete rollout not ready."""
        for e in self.entries:
            doc = self.healthy(e)
            self.assertTrue(b.ready(doc))
            doc["status"]["observedGeneration"] = 0
            self.assertFalse(b.ready(doc))
            doc = self.healthy(e)
            doc["status"][
                "availableReplicas" if e["kind"] == "Deployment" else "numberAvailable"
            ] = 0
            self.assertFalse(b.ready(doc))

    def test_failed_admission_preview_never_writes(self):
        """Verify failed admission preview never writes."""
        e = self.entries[0]
        calls = []
        outer = self

        class Response:
            """Provide a context-managed synthetic response for isolated API-client tests."""
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                """Encode the simulated API response as JSON bytes."""
                return json.dumps(outer.healthy(e)).encode()

        class Opener:
            """Supply mocked HTTP responses for guarded backfill safety tests."""
            def open(self, req, **kwargs):
                """Record the request and return the simulated API response."""
                calls.append((req.get_method(), req.full_url))
                return Response()

        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / "catalog.json").write_text(json.dumps({"entries": [e]}))
            (p / "token").write_text("synthetic-test-only")
            with (
                patch.object(b.ssl, "create_default_context"),
                patch.object(b.urllib.request, "build_opener", return_value=Opener()),
                patch.dict(
                    b.os.environ,
                    {"KUBERNETES_SERVICE_HOST": "mock.invalid", "KUBERNETES_SERVICE_PORT": "443"},
                ),
                patch.object(b.time, "sleep"),
            ):
                with self.assertRaises(AssertionError):
                    b.main(p, p)
        self.assertTrue(all("dryRun=All" in url for method, url in calls if method == "PATCH"))

    def test_rollout_failure_stops_later_targets(self):
        """Verify rollout failure stops later targets."""
        entries = [e for e in self.entries if e["namespace"] != "longhorn-system"][:2]
        written = []
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

        class Opener:
            """Supply mocked HTTP responses for guarded backfill safety tests."""
            def open(self, req, **kwargs):
                """Record the request and return the simulated API response."""
                e = next(e for e in entries if req.full_url.split("?")[0].endswith("/" + e["name"]))
                doc = outer.healthy(e)
                if req.get_method() == "PATCH":
                    doc["spec"] = b.expected_spec(doc, e)
                    if "dryRun=All" not in req.full_url:
                        written.append(e["name"])
                if e["name"] in written:
                    doc["spec"] = b.expected_spec(doc, e)
                    doc["metadata"]["generation"] = 2
                return Response(doc)

        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / "catalog.json").write_text(json.dumps({"entries": entries}))
            (p / "token").write_text("synthetic-test-only")
            with (
                patch.object(b.ssl, "create_default_context"),
                patch.object(b.urllib.request, "build_opener", return_value=Opener()),
                patch.dict(
                    b.os.environ,
                    {"KUBERNETES_SERVICE_HOST": "mock.invalid", "KUBERNETES_SERVICE_PORT": "443"},
                ),
                patch.object(b.time, "sleep"),
                patch.object(b.time, "monotonic", side_effect=[0, 301]),
            ):
                with self.assertRaises(RuntimeError):
                    b.main(p, p)
        self.assertEqual(written, [entries[0]["name"]])

    def test_unhealthy_storage_prevents_any_rollout_write(self):
        """Verify unhealthy storage prevents any rollout write."""
        e = next(e for e in self.entries if e["namespace"] == "longhorn-system")
        calls = []
        spec = importlib.util.spec_from_file_location(
            "storage_guard", ROOT / "tools/longhorn/backfill-component-security.py"
        )
        storage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(storage)

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

        class Opener:
            """Supply mocked HTTP responses for guarded backfill safety tests."""
            def open(self, req, **kwargs):
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
                return Response({"items": [{"status": {}}]})

        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / "catalog.json").write_text(json.dumps({"entries": [e]}))
            (p / "token").write_text("synthetic-test-only")
            with (
                patch.object(b.ssl, "create_default_context"),
                patch.object(b.urllib.request, "build_opener", return_value=Opener()),
                patch.dict(
                    b.os.environ,
                    {"KUBERNETES_SERVICE_HOST": "mock.invalid", "KUBERNETES_SERVICE_PORT": "443"},
                ),
                patch.object(b.time, "sleep"),
                patch.dict("sys.modules", {"storage_guard": storage}),
            ):
                with self.assertRaisesRegex(AssertionError, "not stable and healthy"):
                    b.main(p, p)
        self.assertTrue(calls)
        self.assertEqual(set(calls), {"GET"})

    def test_new_helpers_preserve_required_privilege_boundaries(self):
        """Verify new helpers preserve required privilege boundaries."""
        self.assertFalse(any(e["namespace"] == "metallb-system" for e in self.entries))
        self.assertFalse(
            any(
                d.get("metadata", {}).get("namespace") == "metallb-system"
                for d in g.generate(self.catalog)
            )
        )
        gpu = [
            e
            for e in self.entries
            if e["name"] in ["gpu-feature-discovery", "nvidia-device-plugin-daemonset"]
        ]
        self.assertEqual(len(gpu), 2)
        for e in gpu:
            self.assertEqual(len(e["targets"]), 1)
            t = e["targets"][0]
            self.assertEqual(t["name"], "config-manager-init")
            self.assertEqual(t["section"], "initContainers")
            self.assertEqual(t["guards"]["runAsUser"], 1000)
            self.assertTrue(t["guards"]["runAsNonRoot"])
            self.assertEqual(t["guards"]["capabilities"], {"drop": ["ALL"]})
            self.assertEqual(t["requiredEnv"]["ONESHOT"], "true")
            self.assertEqual(t["requiredEnv"]["SEND_SIGNAL"], "false")

    def test_gpu_health_permission_and_capacity_gate(self):
        """Verify gpu health permission and capacity gate."""
        docs = g.generate(self.catalog)
        role = next(d for d in docs if d["kind"] == "ClusterRole")
        self.assertEqual(
            role["rules"],
            [
                {
                    "apiGroups": [""],
                    "resources": ["nodes"],
                    "resourceNames": ["talos-d4h-k5m"],
                    "verbs": ["get"],
                }
            ],
        )
        review = self.catalog["gpuResourceReview"]
        good = {
            "metadata": {"name": review["node"]},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "capacity": {"nvidia.com/gpu": "8"},
                "allocatable": {"nvidia.com/gpu": "8"},
            },
        }
        b.gpu_healthy(good, review)
        for field in ["capacity", "allocatable", "conditions"]:
            bad = copy.deepcopy(good)
            bad["status"][field] = [] if field == "conditions" else {"nvidia.com/gpu": "0"}
            with self.subTest(field=field), self.assertRaises(AssertionError):
                b.gpu_healthy(bad, review)

    def test_lost_gpu_resources_prevent_rollout_writes(self):
        """Verify lost gpu resources prevent rollout writes."""
        e = next(e for e in self.entries if e["name"] == "gpu-operator")
        review = self.catalog["gpuResourceReview"]
        calls = []

        class Response:
            """Provide a context-managed synthetic response for isolated API-client tests."""
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                """Encode the simulated API response as JSON bytes."""
                return json.dumps(
                    {
                        "metadata": {"name": review["node"]},
                        "status": {
                            "conditions": [{"type": "Ready", "status": "True"}],
                            "capacity": {"nvidia.com/gpu": "0"},
                            "allocatable": {"nvidia.com/gpu": "0"},
                        },
                    }
                ).encode()

        class Opener:
            """Supply mocked HTTP responses for guarded backfill safety tests."""
            def open(self, req, **kwargs):
                """Record the request and return the simulated API response."""
                calls.append(req.get_method())
                return Response()

        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / "catalog.json").write_text(
                json.dumps({"entries": [e], "gpuResourceReview": review})
            )
            (p / "token").write_text("synthetic-test-only")
            with (
                patch.object(b.ssl, "create_default_context"),
                patch.object(b.urllib.request, "build_opener", return_value=Opener()),
                patch.dict(
                    b.os.environ,
                    {"KUBERNETES_SERVICE_HOST": "mock.invalid", "KUBERNETES_SERVICE_PORT": "443"},
                ),
                patch.object(b.time, "sleep"),
            ):
                with self.assertRaisesRegex(AssertionError, "GPU resource count changed"):
                    b.main(p, p)
        self.assertTrue(calls)
        self.assertEqual(set(calls), {"GET"})


if __name__ == "__main__":
    unittest.main()
