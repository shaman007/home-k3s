"""Protect offline image identity checks and narrow Harbor challenge delegation."""

import copy
import graphlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_images", ROOT / "tools/bootstrap/bootstrap_images.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ImageRecoveryTests(unittest.TestCase):
    """A warm node with a different digest must never pass or be overwritten."""

    def setUp(self):
        self.lock = {
            "format_version": 1,
            "nodes": ["192.168.30.100"],
            "images": [
                {
                    "namespace": "cri",
                    "reference": "busybox:1.38",
                    "digest": "sha256:" + "a" * 64,
                }
            ],
        }

    def test_lock_contains_dns_solver_and_system_dependencies(self):
        """Verify lock contains dns solver and system dependencies."""
        lock = MOD.validate(
            json.loads((ROOT / "docs/bootstrap-images/images.lock.json").read_text())
        )
        refs = [i["reference"] for i in lock["images"]]
        for required in [
            "godaddy-webhook",
            "kubelet",
            "etcd",
            "pause",
            "seaweedfs",
            "cert-manager",
            "harbor-core",
        ]:
            self.assertTrue(any(required in r for r in refs), required)
        self.assertEqual(len(lock["nodes"]), 3)

    def test_active_core_images_have_recovery_entries(self):
        """A source change must not silently leave the pinned recovery inventory stale."""
        lock = json.loads((ROOT / "docs/bootstrap-images/images.lock.json").read_text())
        refs = {i["reference"] for i in lock["images"]}
        pod = yaml.safe_load(
            (ROOT / "seaweedfs/deployment-seaweedfs-s3.yaml").read_text()
        )["spec"]["template"]["spec"]
        for container in pod["containers"] + pod["initContainers"]:
            self.assertIn(container["image"], refs)
        app = yaml.safe_load((ROOT / "argocd/application-harbor.yaml").read_text())
        values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        self.assertIn(values["jobservice"]["initContainers"][0]["image"], refs)

    def test_argocd_bootstrap_patches_keep_local_image_policy(self):
        """No image/entrypoint override is hidden in the offline scheduling changes."""
        config = yaml.safe_load(
            (ROOT / "argocd-install/kustomization.yaml").read_text()
        )
        targets = set()
        for entry in config["patches"]:
            data = yaml.safe_load(entry["patch"])
            spec = data.get("spec", {}).get("template", {}).get("spec", {})
            if any(c.get("imagePullPolicy") for c in spec.get("containers", [])):
                targets.add(entry["target"]["name"])
                for c in spec.get("containers", []) + spec.get("initContainers", []):
                    self.assertEqual(set(c), {"name", "imagePullPolicy"})
                    self.assertEqual(c["imagePullPolicy"], "IfNotPresent")
        self.assertEqual(len(targets), 7)

    def test_normalized_cri_aliases(self):
        """Verify normalized cri aliases."""
        self.assertEqual(
            MOD.canonical("busybox:1.38"), "docker.io/library/busybox:1.38"
        )
        self.assertEqual(
            MOD.canonical("quay.io/a/b:v1@sha256:abc"), "quay.io/a/b@sha256:abc"
        )

    @patch.object(MOD, "user_executable", return_value="/usr/bin/talosctl")
    def test_check_never_pulls(self, _cli):
        """Verify check never pulls."""
        with patch.object(MOD, "execute", return_value="") as run:
            issues = MOD.check_node(self.lock, self.lock["nodes"][0])
        self.assertEqual(len(issues), 1)
        self.assertTrue(all("pull" not in c.args[0] for c in run.call_args_list))

    @patch.object(MOD, "user_executable", return_value="/usr/bin/talosctl")
    def test_wrong_digest_is_not_overwritten(self, _cli):
        """Verify wrong digest is not overwritten."""
        with patch.object(
            MOD,
            "execute",
            return_value="node docker.io/library/busybox:1.38 sha256:" + "b" * 64,
        ) as run:
            issues = MOD.check_node(self.lock, self.lock["nodes"][0], True)
        self.assertEqual(issues[0]["result"], "digest-drift")
        self.assertTrue(all("pull" not in c.args[0] for c in run.call_args_list))

    @patch.object(MOD, "user_executable", return_value="/usr/bin/talosctl")
    def test_preload_rechecks_actual_content(self, _cli):
        """Verify preload rechecks actual content."""
        with patch.object(
            MOD,
            "execute",
            side_effect=[
                "",
                "",
                "node docker.io/library/busybox:1.38 sha256:" + "a" * 64,
                "",
            ],
        ) as run:
            self.assertEqual(MOD.check_node(self.lock, self.lock["nodes"][0], True), [])
        self.assertEqual(run.call_args_list[1].args[0][1:3], ["image", "pull"])

    def test_reject_duplicate_or_unsafe_lock(self):
        """Verify reject duplicate or unsafe lock."""
        x = copy.deepcopy(self.lock)
        x["images"] *= 2
        with self.assertRaises(ValueError):
            MOD.validate(x)
        x = copy.deepcopy(self.lock)
        x["images"][0]["reference"] = "--insecure"
        with self.assertRaises(ValueError):
            MOD.validate(x)

    def test_bundle_checksum_detects_corruption_and_missing_files(self):
        """Verify bundle acceptance depends on contents, not successful CLI exit."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "layer").write_bytes(b"fixture")
            MOD.seal_bundle(root)
            self.assertEqual(MOD.verify_bundle(root), 1)
            (root / "layer").write_bytes(b"corrupted")
            with self.assertRaises(ValueError):
                MOD.verify_bundle(root)
            (root / "layer").unlink()
            with self.assertRaises(ValueError):
                MOD.verify_bundle(root)

    def test_bundle_never_overwrites_existing_destination(self):
        """Verify bundle never overwrites existing destination."""
        with self.assertRaises(ValueError):
            MOD.bundle(self.lock, ROOT)


class HarborDNS01Tests(unittest.TestCase):
    """Keep issuance off public ingress without widening solver permissions."""

    def test_only_harbor_selected_and_cname_followed(self):
        """Verify only harbor selected and cname followed."""
        issuer = yaml.safe_load(
            (
                ROOT / "cert-manager/cluster-issuer-letsencrypt-harbor-dns01.yaml"
            ).read_text()
        )
        self.assertEqual(
            issuer["spec"]["acme"]["server"],
            "https://acme-v02.api.letsencrypt.org/directory",
        )
        (solver,) = issuer["spec"]["acme"]["solvers"]
        self.assertEqual(
            solver["selector"], {"dnsNames": ["harbor.andreybondarenko.com"]}
        )
        self.assertEqual(solver["dns01"]["cnameStrategy"], "Follow")
        self.assertEqual(solver["dns01"]["webhook"]["solverName"], "godaddy-v3")
        self.assertNotIn("http01", solver)
        cert = yaml.safe_load((ROOT / "harbor/certificate-harbor-tls.yaml").read_text())
        self.assertEqual(cert["spec"]["issuerRef"]["name"], issuer["metadata"]["name"])
        self.assertEqual(cert["spec"]["secretName"], "harbor-tls")

    def test_missing_independent_solver_image_exposes_conditional_cycle(self):
        """Do not hide the Harbor-backed solver in an otherwise acyclic graph."""
        graph = yaml.safe_load((ROOT / "docs/startup/dependencies.yaml").read_text())
        dependencies = {n: set() for n in graph["nodes"]}
        for edge in graph["edges"]:
            dependencies[edge["to"]].add(edge["from"])
        self.assertEqual(
            len(list(graphlib.TopologicalSorter(dependencies).static_order())),
            len(dependencies),
        )
        for edge in graph["recovery_scenarios"][
            "harbor_dns01_without_independent_images"
        ]["extra_edges"]:
            dependencies[edge["to"]].add(edge["from"])
        with self.assertRaises(graphlib.CycleError):
            list(graphlib.TopologicalSorter(dependencies).static_order())

    def test_delegation_changes_only_challenge_record(self):
        """Verify delegation changes only challenge record."""
        r = json.loads(
            (ROOT / "docs/migrations/harbor-dns01/dns-record.json").read_text()
        )
        self.assertEqual(r["name"], "_acme-challenge.harbor")
        self.assertEqual(r["type"], "CNAME")
        self.assertEqual(r["data"], "_acme-challenge.harbor.int.andreybondarenko.com")
        canary = list(
            yaml.safe_load_all(
                (ROOT / "docs/migrations/harbor-dns01/staging-canary.yaml").read_text()
            )
        )
        self.assertNotEqual(canary[1]["spec"]["secretName"], "harbor-tls")


if __name__ == "__main__":
    unittest.main()
