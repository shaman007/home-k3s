"""Offline candidate boundaries and preserved live-source integration contracts."""

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "batch", ROOT / "tools/bootstrap/prepare_dependency_batch.py"
)
BATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BATCH)


def document(path):
    """Read the unchanged runtime source for comparison."""
    return yaml.safe_load((ROOT / path).read_text())


class DependencyBatchTests(unittest.TestCase):
    """Inactive proposals preserve state, images, secrets and unrelated components."""

    def test_export_is_exclusive_outside_repository_and_has_source_hashes(self):
        """Never overwrite a prior review or accidentally write into an Argo source."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "proposal"
            active = {
                path: path.read_bytes()
                for folder in (
                    "argocd",
                    "mail",
                    "nextcloud",
                    "karakeep",
                    "loki",
                    "thanos",
                    "seaweedfs",
                    "metrics",
                )
                for path in (ROOT / folder).rglob("*.yaml")
            }
            inventory = BATCH.prepare(output, list(BATCH.PACKAGES))
            self.assertTrue(
                all(path.read_bytes() == contents for path, contents in active.items())
            )
            self.assertEqual(set(inventory), set(BATCH.PACKAGES))
            for package, entries in inventory.items():
                for entry in entries:
                    path = ROOT / entry["path"]
                    if path.is_file():
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            entry["source_sha256"],
                        )
                    self.assertTrue((output / package / entry["path"]).is_file())
            original = (output / "index.json").read_bytes()
            with self.assertRaises(FileExistsError):
                BATCH.prepare(output, ["mail"])
            self.assertEqual((output / "index.json").read_bytes(), original)
        with self.assertRaises(ValueError):
            BATCH.prepare(ROOT / "seaweedfs/NEVER-CREATE", ["mail"])

    def test_preparation_catalogue_covers_all_observed_schedules_without_blanket_skip(
        self,
    ):
        """Critical jobs and measurements must retain failure/report semantics."""
        catalogue = document("docs/startup/cronjobs/catalog.yaml")["jobs"]
        self.assertEqual(len(catalogue), 31)
        identities = {(row["namespace"], row["name"]) for row in catalogue}
        self.assertEqual(len(identities), len(catalogue))
        candidates = {
            row["name"] for row in catalogue if row["preparation"] == "source-ready"
        }
        self.assertEqual(
            candidates,
            {
                "logs-check",
                "external-access-daily-report",
                "wordpress-daily-report",
                "nextcloud",
                "rspamd-spam-trainer",
                "bookmarked-media-sync",
                "mastodon-spam-list-sync",
            },
        )
        for row in catalogue:
            if row["name"].startswith("backup-") or row["name"] in (
                "talos-backup",
                "oidc-token-renewer",
            ):
                self.assertEqual(row["unavailable_policy"], "fail")
            if row["owner"]["kind"] == "RecurringJob":
                self.assertEqual(row["preparation"], "controller-owned-no-wrapper")
            if row["name"] == "platform-health-report":
                self.assertEqual(row["unavailable_policy"], "report")
            if "source" in row:
                self.assertTrue((ROOT / row["source"]).is_file())
        graph = document("docs/startup/dependencies.yaml")
        self.assertEqual(set(graph["prepared_packages"]), set(BATCH.PACKAGES))

    def test_mail_preserves_postfix_policy_and_all_main_containers(self):
        """Only add the protocol gate and remove the obsolete transition init."""
        result = BATCH.mail()
        self.assertEqual(
            set(result),
            {
                "mail/deployment-rspamd.yaml",
                "mail/stateful-set-valkey.yaml",
                "mail/config-map-rspamd-startup.yaml",
            },
        )
        original = document("mail/deployment-rspamd.yaml")
        changed = result["mail/deployment-rspamd.yaml"]
        before = original["spec"]["template"]["spec"]
        after = changed["spec"]["template"]["spec"]
        self.assertEqual(after["containers"], before["containers"])
        self.assertEqual(after["initContainers"][:-1], before["initContainers"])
        self.assertEqual(after["initContainers"][-1]["name"], "wait-for-valkey")
        self.assertIn(
            "milter_default_action = accept",
            (ROOT / "mail/config-map-main-cf.yaml").read_text(),
        )
        statefulset = next(
            doc
            for doc in result["mail/stateful-set-valkey.yaml"]
            if doc["kind"] == "StatefulSet"
        )
        self.assertNotIn("initContainers", statefulset["spec"]["template"]["spec"])
        old = next(
            doc
            for doc in yaml.safe_load_all(
                (ROOT / "mail/stateful-set-valkey.yaml").read_text()
            )
            if doc["kind"] == "StatefulSet"
        )
        old["spec"]["template"]["spec"].pop("initContainers")
        self.assertEqual(old, statefulset)

    def test_nextcloud_cron_preserves_image_pvc_schedule_and_limits(self):
        """Replace blind sleep, retaining the exact original PHP cron work."""
        original = document("nextcloud/cron-job-nextcloud.yaml")
        changed = BATCH.nextcloud_cron()["nextcloud/cron-job-nextcloud.yaml"]
        self.assertEqual(changed["spec"]["schedule"], original["spec"]["schedule"])
        self.assertEqual(
            changed["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"], 1800
        )
        before = original["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        after = changed["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        for key in ("affinity", "hostAliases", "automountServiceAccountToken"):
            self.assertEqual(before[key], after[key])
        old_work, work = before["containers"][0], after["containers"][0]
        for key in ("image", "resources", "securityContext"):
            self.assertEqual(work[key], old_work[key])
        self.assertEqual(
            work["volumeMounts"][:-1],
            [m for m in old_work["volumeMounts"] if m["name"] != "cron-gate"],
        )
        self.assertEqual(
            after["volumes"][:-1],
            [v for v in before["volumes"] if v["name"] != "cron-gate"],
        )
        self.assertNotIn("initContainers", after)
        self.assertIn(
            "exec php /nextcloud/cron.php", BATCH.script("nextcloud_job_gate.sh")
        )

    def test_karakeep_gates_workers_not_the_pod_or_chrome(self):
        """The same-Pod Chrome provider must remain free to start."""
        original = document("karakeep/deployment-karakeep.yaml")
        proposed = BATCH.karakeep()
        changed = proposed["karakeep/deployment-karakeep.yaml"]
        old_pod = original["spec"]["template"]["spec"]
        pod = changed["spec"]["template"]["spec"]
        self.assertEqual(pod["initContainers"], old_pod["initContainers"])
        self.assertEqual(pod["containers"][1:], old_pod["containers"][1:])
        web, old_web = pod["containers"][0], old_pod["containers"][0]
        self.assertNotIn("command", web)
        for key in set(old_web) - {"volumeMounts"}:
            self.assertEqual(web[key], old_web[key])
        mount = web["volumeMounts"][-1]
        self.assertEqual(mount["mountPath"], "/etc/s6-overlay/s6-rc.d/svc-workers/run")
        self.assertEqual(mount["subPath"], "run")
        runner = proposed["karakeep/config-map-worker-startup.yaml"]["data"]["run"]
        self.assertTrue(runner.startswith("#!/command/with-contenv sh\n"))
        self.assertNotIn("svc-web", runner)

    def test_every_script_reference_resolves_to_versioned_candidate_configmap(self):
        """Older running Jobs must not adopt a changed probe script via projection."""
        for package in (
            BATCH.mail(),
            BATCH.mail_training(),
            BATCH.nextcloud_cron(),
            BATCH.karakeep(),
        ):
            configmaps = {
                doc["metadata"]["name"]: doc
                for doc in package.values()
                if isinstance(doc, dict) and doc["kind"] == "ConfigMap"
            }
            for name, cm in configmaps.items():
                digest = hashlib.sha256(
                    json.dumps(cm["data"], sort_keys=True).encode()
                ).hexdigest()[:12]
                self.assertTrue(name.endswith("-" + digest))
                references = []
                for value in package.values():
                    if not isinstance(value, dict):
                        continue
                    if value["kind"] == "Deployment":
                        pod = value["spec"]["template"]["spec"]
                    elif value["kind"] == "CronJob":
                        pod = value["spec"]["jobTemplate"]["spec"]["template"]["spec"]
                    else:
                        continue
                    references.extend(
                        v.get("configMap", {}).get("name") for v in pod["volumes"]
                    )
                self.assertIn(name, references)

    def test_mail_training_preserves_original_mailbox_work_and_mounts(self):
        """Only wrap work; do not change the trainer's learning/deletion implementation."""
        original = document("mail/cron-job-rspamd-spam-trainer.yaml")
        candidate = BATCH.mail_training()["mail/cron-job-rspamd-spam-trainer.yaml"]
        old = original["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        pod = candidate["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        self.assertNotIn("initContainers", pod)
        self.assertEqual(
            pod["containers"][0]["command"][2:], ["/bin/sh", "/config/train-spam.sh"]
        )
        self.assertEqual(
            pod["containers"][0]["volumeMounts"][:-1],
            [
                m
                for m in old["containers"][0]["volumeMounts"]
                if m["name"] != "mail-training"
            ],
        )
        for key in ("image", "securityContext", "resources"):
            self.assertEqual(pod["containers"][0][key], old["containers"][0][key])
        self.assertEqual(candidate["spec"]["schedule"], original["spec"]["schedule"])

    def test_loki_only_changes_storage_transport(self):
        """Keep bucket names, schema, retention, env references and every other value."""
        original = document("argocd/application-loki.yaml")
        changed = BATCH.observability()["argocd/application-loki.yaml"]
        old_source = original["spec"]["source"]
        new_source = changed["spec"]["source"]
        before = yaml.safe_load(old_source["helm"]["values"])
        after = yaml.safe_load(new_source["helm"]["values"])
        self.assertEqual(after["loki"]["storage"]["s3"]["endpoint"], BATCH.INTERNAL_S3)
        self.assertIs(after["loki"]["storage"]["s3"]["insecure"], True)
        for key in ("endpoint", "insecure"):
            after["loki"]["storage"]["s3"][key] = before["loki"]["storage"]["s3"][key]
        self.assertEqual(before, after)
        new_source["helm"]["values"] = old_source["helm"]["values"]
        self.assertEqual(changed, original)

    def test_thanos_preserves_vault_reference_and_no_raw_provider_data_is_merged(self):
        """ESO produces exactly objstore.yml; the intermediate source key is private."""
        original = document("thanos/external-secret-thanos-objstore-secret.yaml")
        changed = BATCH.observability()[
            "thanos/external-secret-thanos-objstore-secret.yaml"
        ]
        self.assertEqual(
            changed["spec"]["data"][0]["remoteRef"],
            original["spec"]["data"][0]["remoteRef"],
        )
        target = changed["spec"]["target"]
        self.assertEqual(target["name"], original["spec"]["target"]["name"])
        self.assertEqual(target["template"]["mergePolicy"], "Replace")
        self.assertEqual(set(target["template"]["data"]), {"objstore.yml"})
        self.assertNotIn("fail ", target["template"]["data"]["objstore.yml"])

    def test_internal_s3_policies_are_bidirectional_and_scoped(self):
        """No allow-all port/range or querier-to-S3 dependency is introduced."""
        policies = [
            doc
            for doc in BATCH.observability().values()
            if doc["kind"] == "NetworkPolicy"
        ]
        self.assertEqual(len(policies), 3)
        for policy in policies:
            spec = policy["spec"]
            self.assertTrue(spec["podSelector"])
            rules = spec.get("egress", spec.get("ingress"))
            self.assertEqual(rules[0]["ports"], [{"protocol": "TCP", "port": 8333}])
            peers = rules[0].get("to", rules[0].get("from"))
            for peer in peers:
                self.assertIn("namespaceSelector", peer)
                self.assertIn("podSelector", peer)
                self.assertNotIn("ipBlock", peer)
            self.assertNotIn("thanos-querier", json.dumps(spec))

    def test_thanos_template_runs_in_real_go_sprig_without_changing_credentials(self):
        """Helm checks shared Go/Sprig behavior; actual ESO reconciliation is pending."""
        helm = shutil.which("helm")
        self.assertIsNotNone(helm, "Install Helm for the existing CI/test runtime")
        fixture_value = "synthetic\nline'quote"
        fixture = {
            "type": "S3",
            "config": {
                "bucket": "fixture-only",
                "endpoint": "old.invalid",
                "insecure": False,
                "access_key": "synthetic:key",
                "secret_key": fixture_value,
                "region": "us-east-1",
                "http_config": {"idle_conn_timeout": "90s"},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            chart = Path(directory)
            (chart / "Chart.yaml").write_text(
                "apiVersion: v2\nname: fixture\nversion: 0.1.0\n"
            )
            (chart / "templates").mkdir()
            template = (
                '{{- define "transform" -}}\n'
                + BATCH.THANOS_TEMPLATE
                + "{{- end -}}\napiVersion: v1\nkind: ConfigMap\n"
                "metadata:\n  name: fixture\ndata:\n  result: |\n"
                + '{{ include "transform" .Values | indent 4 }}\n'
            )
            (chart / "templates/test.yaml").write_text(template)
            values = chart / "values.yaml"
            values.write_text(yaml.safe_dump({"source": yaml.safe_dump(fixture)}))
            # Fixed local Helm fixture; no shell or network.
            rendered = subprocess.run(  # nosec B603
                [helm, "template", "fixture", str(chart)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            result = yaml.safe_load(yaml.safe_load(rendered.stdout)["data"]["result"])
            expected = copy.deepcopy(fixture)
            expected["config"].update(
                endpoint="s3.seaweedfs.svc.cluster.local:8333", insecure=True
            )
            self.assertEqual(result, expected)
            for invalid in (
                {"type": "AZURE", "config": {}},
                {"type": "S3", "config": "invalid"},
                {"config": {}},
            ):
                values.write_text(yaml.safe_dump({"source": yaml.safe_dump(invalid)}))
                failed = subprocess.run(  # nosec B603
                    [helm, "template", "fixture", str(chart)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.assertNotEqual(failed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
