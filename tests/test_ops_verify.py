"""Verify operational decisions and fail-closed collection without cluster writes."""

import importlib.util
import io
import json
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "ops_verify", Path(__file__).resolve().parents[1] / "tools/ops/verify.py")
OPS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPS)
NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


def healthy_app():
    """A controller-confirmed application, with no functional probe evidence."""
    return {"metadata": {"name": "example", "namespace": "argocd"},
            "spec": {"syncPolicy": {"automated": {"selfHeal": True}}},
            "status": {"health": {"status": "Healthy"},
                       "sync": {"status": "Synced", "revision": "abc"}}}


def reader(resources):
    """Return isolated fixtures by API resource name."""
    return lambda resource, namespace=None: deepcopy(resources.get((resource, namespace), resources.get(resource, [])))


def backup_resources():
    """Scheduled backups and trim with recent completed backup evidence."""
    def cron(name, owner=None):
        item = {"metadata": {"name": name}, "spec": {},
                "status": {"lastSuccessfulTime": (NOW - timedelta(minutes=30)).isoformat()}}
        if owner:
            item["metadata"]["ownerReferences"] = [{"kind": "RecurringJob", "apiVersion": "longhorn.io/v1beta2", "name": owner}]
        return item
    return {
        "volumes.longhorn.io": [{"metadata": {"name": "volume", "labels": {"recurring-job.longhorn.io/backup-daily": "enabled"}}}],
        "recurringjobs.longhorn.io": [{"metadata": {"name": "backup-daily"}, "spec": {"task": "backup"}},
                                     {"metadata": {"name": "trim-daily"}, "spec": {"task": "filesystem-trim"}}],
        "backups.longhorn.io": [{"status": {"volumeName": "volume", "backupTargetName": "default", "state": "Completed",
                                              "backupCreatedAt": (NOW - timedelta(hours=1)).isoformat()}}],
        ("cronjobs.batch", "longhorn-system"): [cron("backup", "backup-daily"), cron("trim", "trim-daily")],
        ("cronjobs.batch", "talos-backup"): [cron("talos-backup")],
    }


class OpsVerifyTest(unittest.TestCase):
    """Test scope, evidence and command boundaries independently of implementation."""

    def test_argocd_healthy_does_not_hide_wrong_revision(self):
        """Healthy/Synced at an old revision must fail a requested revision gate."""
        read = reader({"applications.argoproj.io": [healthy_app()]})
        checks = OPS.run("argocd", read, app="example", revision="different", now=NOW)
        self.assertTrue(checks[0]["passed"])
        self.assertFalse(checks[1]["passed"])

    def test_multi_source_revision_checks_selected_source(self):
        """Do not mistake one updated source for another source reaching its target."""
        app = healthy_app()
        app["spec"]["sources"] = [{}, {}]
        app["status"]["sync"]["revisions"] = ["old", "target"]
        read = reader({"applications.argoproj.io": [app]})
        with self.assertRaises(OPS.CollectionError):
            OPS.run("argocd", read, app="example", revision="target", now=NOW)
        self.assertFalse(OPS.run("argocd", read, "example", "target", 1, NOW)[1]["passed"])
        self.assertTrue(OPS.run("argocd", read, "example", "target", 2, NOW)[1]["passed"])

    def test_empty_and_paused_argocd_fail(self):
        """Missing inventory and paused reconciliation cannot be a successful procedure."""
        self.assertFalse(OPS.run("argocd", reader({}), now=NOW)[0]["passed"])
        app = healthy_app()
        app["metadata"]["annotations"] = {"argocd.argoproj.io/skip-reconcile": "true"}
        self.assertFalse(OPS.run("argocd", reader({"applications.argoproj.io": [app]}), now=NOW)[0]["passed"])

    def test_controller_error_text_is_not_published(self):
        """Arbitrary controller messages are excluded from returned evidence."""
        app = healthy_app()
        app["status"]["conditions"] = [{"type": "ComparisonError", "message": "SECRET-SENTINEL"}]
        result = OPS.run("argocd", reader({"applications.argoproj.io": [app]}), now=NOW)
        self.assertFalse(result[0]["passed"])
        self.assertNotIn("SECRET-SENTINEL", json.dumps(result))
        self.assertIn("ComparisonError", json.dumps(result))

    def test_backup_status_is_not_restore_evidence(self):
        """A recent CronJob success alone must not hide missing backup metadata."""
        resources = backup_resources()
        self.assertTrue(all(check["passed"] for check in OPS.run("backups", reader(resources), now=NOW)))
        resources["backups.longhorn.io"] = []
        checks = OPS.run("backups", reader(resources), now=NOW)
        self.assertFalse(checks[0]["passed"])
        self.assertTrue(checks[-1]["passed"])
        self.assertIn("Does not prove recoverability", OPS.LIMITS["backups"])

    def test_stale_suspended_missing_and_future_talos_success_fail(self):
        """Check the scheduled success timestamp rather than surviving Job history."""
        for mode in ("stale", "suspended", "missing", "future"):
            with self.subTest(mode=mode):
                resources = backup_resources()
                job = resources[("cronjobs.batch", "talos-backup")][0]
                if mode == "stale":
                    job["status"]["lastSuccessfulTime"] = (NOW - timedelta(hours=3)).isoformat()
                elif mode == "suspended":
                    job["spec"]["suspend"] = True
                elif mode == "future":
                    job["status"]["lastSuccessfulTime"] = (NOW + timedelta(hours=1)).isoformat()
                else:
                    resources[("cronjobs.batch", "talos-backup")] = []
                self.assertFalse(OPS.run("backups", reader(resources), now=NOW)[-1]["passed"])

    def test_future_longhorn_timestamps_cannot_pass_freshness_gate(self):
        """Do not accept clock skew as evidence that a backup exists now."""
        resources = backup_resources()
        resources["backups.longhorn.io"][0]["status"]["backupCreatedAt"] = (NOW + timedelta(hours=1)).isoformat()
        checks = OPS.run("backups", reader(resources), now=NOW)
        self.assertFalse(all(check["passed"] for check in checks))
        self.assertFalse(next(check for check in checks if check["name"] == "backup_timestamps")["passed"])

    def test_baseline_preserves_zero_replicas_and_detached_volumes(self):
        """An intentionally stopped workload and detached/unknown volume are valid evidence."""
        workload = {"metadata": {"name": "example", "generation": 2, "uid": "uid-1"},
                    "spec": {"replicas": 0, "persistentVolumeClaimRetentionPolicy": {"whenScaled": "Retain"}},
                    "status": {"observedGeneration": 2}}
        resources = {"statefulsets.apps": [workload],
                     "volumes.longhorn.io": [{"metadata": {"name": "volume"},
                                                "status": {"state": "detached", "robustness": "unknown"}}]}
        checks = OPS.run("baseline", reader(resources), now=NOW)
        states = next(check for check in checks if check["name"] == "statefulsets.apps")
        self.assertTrue(states["passed"])
        self.assertEqual(states["details"][0]["original_replicas"], 0)
        self.assertEqual(states["details"][0]["pvc_retention"], {"whenScaled": "Retain"})
        self.assertTrue(checks[-1]["passed"])
        resources["volumes.longhorn.io"][0]["status"]["robustness"] = "faulted"
        self.assertFalse(OPS.run("baseline", reader(resources), now=NOW)[-1]["passed"])
        workload["status"]["observedGeneration"] = 1
        checks = OPS.run("baseline", reader(resources), now=NOW)
        self.assertFalse(next(check for check in checks if check["name"] == "statefulsets.apps")["passed"])

    def test_node_pressure_fails_baseline(self):
        """Ready alone must not mask active disk pressure."""
        resources = {"nodes": [{"metadata": {"name": "node"}, "status": {"conditions": [
            {"type": "Ready", "status": "True"}, {"type": "DiskPressure", "status": "True"}]}}]}
        self.assertFalse(OPS.run("baseline", reader(resources), now=NOW)[0]["passed"])

    def test_collector_only_issues_bounded_context_pinned_gets(self):
        """No shell or mutating subcommand is permitted in the collector."""
        with patch.object(OPS.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '{"items": []}')) as execute:
            self.assertEqual(OPS.collect("test-context", 8)("nodes"), [])
        args, kwargs = execute.call_args
        command = args[0]
        self.assertEqual(command[:3], ["kubectl", "get", "nodes"])
        self.assertIn("test-context", command)
        self.assertIn("--request-timeout=8s", command)
        self.assertEqual(kwargs["timeout"], 13)
        self.assertNotIn("shell", kwargs)

    def test_collection_errors_are_json_and_do_not_leak_output(self):
        """RBAC failure, malformed JSON and timeouts must not return success or raw errors."""
        outcomes = [subprocess.CompletedProcess([], 1, "SECRET-SENTINEL", "SECRET-SENTINEL"),
                    subprocess.CompletedProcess([], 0, "SECRET-SENTINEL"),
                    subprocess.CompletedProcess([], 0, '{"items": {}}'),
                    subprocess.TimeoutExpired("SECRET-SENTINEL", 20)]
        for outcome in outcomes:
            with self.subTest(outcome=type(outcome).__name__):
                kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                with patch.object(OPS.subprocess, "run", **kwargs), redirect_stdout(io.StringIO()) as output:
                    code = OPS.main(["argocd"])
                result = json.loads(output.getvalue())
                self.assertEqual(code, 2)
                self.assertEqual(result["status"], "error")
                self.assertNotIn("SECRET-SENTINEL", output.getvalue())

    def test_cli_exit_codes_separate_failed_checks_and_success(self):
        """Structured output remains parseable for a real condition failure."""
        for items, expected in [([], 1), ([healthy_app()], 0)]:
            with patch.object(OPS, "collect", return_value=reader({"applications.argoproj.io": items})), redirect_stdout(io.StringIO()) as output:
                code = OPS.main(["argocd"])
            self.assertEqual(code, expected)
            self.assertEqual(json.loads(output.getvalue())["format_version"], 1)


if __name__ == "__main__":
    unittest.main()
