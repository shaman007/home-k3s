"""Keep Receive migration inactive, independently stored and data-safe by stage."""

import copy
import fnmatch
import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "receive_plan", ROOT / "tools/bootstrap/prepare_prometheus_receive.py"
)
PLAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLAN)


class ReceivePreparationTests(unittest.TestCase):
    """Preparation cannot silently activate, rewrite identities or share live RWO data."""

    def test_active_prometheus_has_only_local_startup_requirements(self):
        """The published workload must not regain a sidecar or mandatory scrape tokens."""
        pod = PLAN.read(PLAN.PROM)["spec"]["template"]["spec"]
        self.assertEqual([c["name"] for c in pod["containers"]], ["prometheus"])
        volumes = {v["name"]: v for v in pod["volumes"]}
        self.assertNotIn("objstoreyml", volumes)
        self.assertNotIn("prometheus-config-shared", volumes)
        self.assertEqual({n for n, v in volumes.items() if "secret" in v}, PLAN.OPTIONAL)
        for name in PLAN.OPTIONAL:
            self.assertIs(volumes[name]["secret"].get("optional"), True)

    def test_active_query_and_scrapes_retire_only_the_old_sidecar(self):
        """The independently stored receive path replaces the retired scrape expectation."""
        cm = PLAN.read(PLAN.CONFIG)
        config = yaml.safe_load(cm["data"]["prometheus.yaml"])
        self.assertEqual(config["remote_write"], [PLAN.remote_write()])
        jobs = {job["job_name"] for job in config["scrape_configs"]}
        self.assertIn("thanos-receive", jobs)
        self.assertNotIn("thanos-sidecar", jobs)
        args = PLAN.read(PLAN.QUERIER)["spec"]["template"]["spec"]["containers"][0]["args"]
        self.assertNotIn("--endpoint=thanos-sidecar.monitoring.svc.cluster.local:10901", args)
        self.assertIn("--endpoint=thanos-receive.monitoring.svc.cluster.local:10901", args)
        self.assertIn("--endpoint=thanos-store-gateway.monitoring.svc.cluster.local:10901", args)

    def test_namespace_quota_reserves_receive_storage(self):
        """Free Longhorn space alone does not permit PVC admission under a quota."""
        quota = next(
            obj for obj in yaml.safe_load_all(
                (ROOT / "namespaces/resource-quotas.yaml").read_text()
            )
            if obj and obj["metadata"].get("namespace") == "monitoring"
        )
        claim = PLAN.receive_statefulset()["spec"]["volumeClaimTemplates"][0]
        storage = claim["spec"]["resources"]["requests"]["storage"]
        budget = quota["spec"]["hard"]["requests.storage"]
        self.assertTrue(storage.endswith("Gi") and budget.endswith("Gi"))
        self.assertGreaterEqual(int(budget[:-2]), 260 + int(storage[:-2]))

    def test_stage_one_sources_match_reviewed_generator(self):
        """Publication deploys only the reviewed receiver/policy phase, not dual write."""
        for path, objects in PLAN.infrastructure().items():
            self.assertEqual(
                list(yaml.safe_load_all((ROOT / path).read_text())), objects, path
            )

    def test_infrastructure_does_not_touch_prometheus(self):
        """Create receiver first, preserving the old ingestion/query path."""
        stage = PLAN.candidate("infrastructure")
        self.assertNotIn(PLAN.PROM, stage)
        self.assertNotIn(PLAN.CONFIG, stage)
        self.assertNotIn(PLAN.QUERIER, stage)
        receiver = stage["thanos/stateful-set-thanos-receive.yaml"][0]
        self.assertEqual(receiver["spec"]["replicas"], 1)
        (claim,) = receiver["spec"]["volumeClaimTemplates"]
        self.assertEqual(claim["spec"]["accessModes"], ["ReadWriteOnce"])
        self.assertEqual(claim["spec"]["resources"]["requests"]["storage"], "64Gi")
        self.assertEqual(
            receiver["spec"]["persistentVolumeClaimRetentionPolicy"],
            {"whenDeleted": "Retain", "whenScaled": "Retain"},
        )
        self.assertNotIn("prometheus-lh", str(receiver))
        self.assertNotIn("affinity", receiver["spec"]["template"]["spec"])

    def test_receive_keeps_existing_tenant_and_replica_semantics(self):
        """Default tenant must not add tenant_id to every new time series."""
        container = PLAN.receive_statefulset()["spec"]["template"]["spec"][
            "containers"
        ][0]
        self.assertIn("--receive.tenant-label-name=cluster", container["args"])
        self.assertIn("--receive.default-tenant-id=prometheus", container["args"])
        self.assertIn('--label=replica="$(POD_NAME)"', container["args"])
        self.assertNotIn("prometheus-lh", str(container))
        self.assertFalse(
            PLAN.receive_statefulset()["spec"]["template"]["spec"][
                "automountServiceAccountToken"
            ]
        )
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])

    def test_receive_reserves_memory_for_compaction_outside_go_heap(self):
        """The observed head fits, with GC and room for mmap/compaction peaks."""
        container = PLAN.receive_statefulset()["spec"]["template"]["spec"]["containers"][0]
        self.assertIn("--enable-auto-gomemlimit", container["args"])
        self.assertIn("--auto-gomemlimit.ratio=0.7", container["args"])
        self.assertEqual(container["resources"]["requests"]["memory"], "6Gi")
        self.assertEqual(container["resources"]["limits"]["memory"], "8Gi")

    def test_dual_write_preserves_sidecar_and_all_old_rules(self):
        """A published first config change must not retire the historical data source."""
        stage = PLAN.candidate("dual-write")
        self.assertNotIn(PLAN.PROM, stage)
        args = stage[PLAN.QUERIER][0]["spec"]["template"]["spec"]["containers"][0][
            "args"
        ]
        current_args = PLAN.read(PLAN.QUERIER)["spec"]["template"]["spec"][
            "containers"
        ][0]["args"]
        old_endpoint = "--endpoint=thanos-sidecar.monitoring.svc.cluster.local:10901"
        if old_endpoint in current_args:
            self.assertIn(old_endpoint, args)
        old = PLAN.read(PLAN.CONFIG)
        new = stage[PLAN.CONFIG][0]
        self.assertTrue(
            new["data"]["prometheus.rules"].startswith(old["data"]["prometheus.rules"])
        )
        original = yaml.safe_load(old["data"]["prometheus.yaml"])
        changed = yaml.safe_load(new["data"]["prometheus.yaml"])
        original.pop("remote_write", None)
        original["scrape_configs"] = [
            j for j in original["scrape_configs"] if j["job_name"] != "thanos-receive"
        ]
        self.assertEqual(changed.pop("remote_write"), [PLAN.remote_write()])
        changed["scrape_configs"] = [
            j for j in changed["scrape_configs"] if j["job_name"] != "thanos-receive"
        ]
        self.assertEqual(changed, original)
        yaml.safe_load(new["data"]["prometheus.rules"])

    def test_cutover_prometheus_has_no_thanos_and_only_optional_app_secrets(self):
        """Preserve readiness, storage and API auth instead of publishing unready endpoints."""
        before = PLAN.read(PLAN.PROM)["spec"]["template"]["spec"]
        pod = PLAN.candidate("cutover")[PLAN.PROM][0]["spec"]["template"]["spec"]
        self.assertEqual([c["name"] for c in pod["containers"]], ["prometheus"])
        old = next(c for c in before["containers"] if c["name"] == "prometheus")
        new = pod["containers"][0]
        for key in [
            "args",
            "readinessProbe",
            "livenessProbe",
            "startupProbe",
            "resources",
            "securityContext",
        ]:
            self.assertEqual(new[key], old[key])
        self.assertTrue(pod["automountServiceAccountToken"])
        self.assertEqual(pod["initContainers"], before["initContainers"])
        for volume in pod["volumes"]:
            if "secret" in volume:
                self.assertTrue(volume["secret"]["optional"])
        self.assertNotIn("objstore", str(pod))
        self.assertEqual(
            next(v for v in pod["volumes"] if v["name"] == "prometheus-storage-volume"),
            next(
                v for v in before["volumes"] if v["name"] == "prometheus-storage-volume"
            ),
        )
        service = PLAN.read(
            "metrics/kubernetes-prometheus/service-prometheus-service.yaml"
        )
        self.assertFalse(service["spec"].get("publishNotReadyAddresses", False))

    def test_eso_preserves_source_and_internal_endpoint_template(self):
        """No credential value or new OpenBao policy is needed for Receive."""
        stage = PLAN.candidate("infrastructure")
        secret = stage["thanos/external-secret-thanos-receive-objstore-internal.yaml"][
            0
        ]
        old = PLAN.read(
            "thanos/external-secret-thanos-compactor-objstore-internal.yaml"
        )
        self.assertEqual(secret["spec"]["data"], old["spec"]["data"])
        self.assertEqual(
            secret["spec"]["target"]["template"], old["spec"]["target"]["template"]
        )

    def test_policy_and_argocd_filename_adoption(self):
        """Receive is not given broad namespace egress or arbitrary remote-write clients."""
        stage = PLAN.candidate("infrastructure")
        app = stage["argocd/application-monitoring-network-policy.yaml"][0]
        include = app["spec"]["source"]["directory"]["include"].strip("{}").split(",")
        self.assertTrue(
            any(fnmatch.fnmatch(Path(PLAN.POLICY).name, p) for p in include)
        )
        ingress = stage[PLAN.POLICY][0]["spec"]["ingress"]
        self.assertEqual(
            ingress[0]["from"],
            [{"podSelector": {"matchLabels": {"app": "prometheus-server"}}}],
        )
        self.assertEqual({p["port"] for p in ingress[0]["ports"]}, {19291, 10902})
        s3 = stage[PLAN.POLICY][-1]["spec"]["egress"][0]
        self.assertEqual(s3["ports"], [{"protocol": "TCP", "port": 8333}])

    def test_global_policies_cannot_reopen_receiver(self):
        """NetworkPolicies are additive: both generic namespace rules must exclude Receive."""
        stage = PLAN.candidate("infrastructure")
        for path in [
            "metrics/network-policy-monitoring-allow-egress-intra-namespace.yaml",
            "metrics/network-policy-monitoring-allow-ingress-from-monitoring.yaml",
        ]:
            selector = stage[path][0]["spec"]["podSelector"]["matchExpressions"][0]
            self.assertEqual(selector["operator"], "NotIn")
            self.assertIn("thanos-receive", selector["values"])

    def test_cutover_preserves_every_existing_alert(self):
        """Retiring a scrape expectation must never remove or weaken old alert rules."""

        def alerts(cm):
            groups = yaml.safe_load(cm["data"]["prometheus.rules"])["groups"]
            return Counter(
                json.dumps(rule, sort_keys=True)
                for group in groups
                for rule in group["rules"]
                if "alert" in rule
            )

        old = alerts(PLAN.read(PLAN.CONFIG))
        new = alerts(PLAN.candidate("cutover")[PLAN.CONFIG][0])
        self.assertFalse(old - new)
        expected = {
            "PrometheusRemoteWriteLag", "PrometheusRemoteWriteDroppedSamples"
        }
        existing_names = {json.loads(rule)["alert"] for rule in old}
        added_names = {json.loads(rule)["alert"] for rule in new - old}
        self.assertEqual(added_names, expected - existing_names)

    def test_regeneration_after_infrastructure_and_dual_write_is_safe(self):
        """Each stage can be regenerated from a tree where the prior stage is promoted."""
        original = PLAN.read
        tree = {
            p: objects[0]
            for p, objects in PLAN.candidate("dual-write").items()
            if len(objects) == 1
        }
        with patch.object(
            PLAN,
            "read",
            side_effect=lambda p: copy.deepcopy(tree[p]) if p in tree else original(p),
        ):
            cutover = PLAN.candidate("cutover")
        config = yaml.safe_load(cutover[PLAN.CONFIG][0]["data"]["prometheus.yaml"])
        self.assertEqual(len(config["remote_write"]), 1)
        self.assertEqual(
            len(
                [
                    j
                    for j in config["scrape_configs"]
                    if j["job_name"] == "thanos-receive"
                ]
            ),
            1,
        )

    def test_changed_labels_or_remote_write_refuse_generation(self):
        """Do not overwrite a future owner or silently change series identity."""
        original = PLAN.read
        for field, value in [
            ("external_labels", {"cluster": "different"}),
            ("remote_write", [{"url": "http://different"}]),
        ]:
            cm = original(PLAN.CONFIG)
            config = yaml.safe_load(cm["data"]["prometheus.yaml"])
            if field == "external_labels":
                config["global"][field] = value
            else:
                config[field] = value
            cm["data"]["prometheus.yaml"] = yaml.safe_dump(config)
            with (
                patch.object(
                    PLAN,
                    "read",
                    side_effect=lambda p, c=cm: (
                        copy.deepcopy(c) if p == PLAN.CONFIG else original(p)
                    ),
                ),
                self.assertRaises(ValueError),
            ):
                PLAN.candidate("cutover")

    def test_export_refuses_existing_or_repository_output(self):
        """Generating candidates is never an implicit promotion into active Argo paths."""
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            PLAN.export("cutover", Path(d))
        with self.assertRaises(ValueError):
            PLAN.export("cutover", ROOT / "new-candidate")


if __name__ == "__main__":
    unittest.main()
