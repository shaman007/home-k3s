from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from copy import deepcopy
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CONFIGMAP = ROOT / "metrics" / "config-map-platform-health-report-scripts.yaml"


def load_report_functions():
    configmap = yaml.safe_load(SCRIPT_CONFIGMAP.read_text(encoding="utf-8"))
    namespace = {"__name__": "platform_health_report_test"}
    exec(
        compile(configmap["data"]["platform-health-report.py"], str(SCRIPT_CONFIGMAP), "exec"),
        namespace,
    )
    return namespace


class PlatformHealthReportLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_report_functions()

    def test_restart_metrics_coalesce_recreated_pods_without_changing_checks(self):
        checks = [
            {
                "name": "restarts",
                "passed": True,
                "failures": 0,
                "details": [
                    {
                        "namespace": "test",
                        "item": "recreated/worker",
                        "value_name": "restarts_24h",
                        "value": 2,
                    },
                    {
                        "namespace": "test",
                        "item": "recreated/worker",
                        "value_name": "restarts_24h",
                        "value": 3,
                    },
                ],
            }
        ]
        before = deepcopy(checks)
        metrics = self.report["render_metrics"](checks)
        samples = [
            line
            for line in metrics.splitlines()
            if line.startswith("platform_health_detail_value{")
        ]
        self.assertEqual(
            samples,
            [
                'platform_health_detail_value{check="restarts_24h",namespace="test",'
                'item="recreated/worker"} 5.0'
            ],
        )
        self.assertEqual(checks, before)
        self.assertIn('platform_health_check_status{scope="cluster",check="restarts"} 1', metrics)

    def healthy_application(self, name="example"):
        return {
            "metadata": {"namespace": "argocd", "name": name},
            "spec": {"syncPolicy": {"automated": {"selfHeal": True}}},
            "status": {"health": {"status": "Healthy"}, "sync": {"status": "Synced"}},
        }

    def test_argocd_automation_and_lenka_exception(self):
        app = self.healthy_application()
        for enabled in (None, True):
            app["spec"]["syncPolicy"]["automated"]["enabled"] = enabled
            self.assertTrue(self.report["argocd_application_check"]([app])["passed"])
        for policy in (
            {},
            {"automated": None},
            {"automated": {}},
            {"automated": {"enabled": False, "selfHeal": True}},
        ):
            app["spec"]["syncPolicy"] = policy
            self.assertFalse(self.report["argocd_application_check"]([app])["passed"])
        app = self.healthy_application("lenka")
        app["spec"]["syncPolicy"]["automated"] = {"prune": True}
        self.assertTrue(self.report["argocd_application_check"]([app])["passed"])
        app["spec"]["syncPolicy"]["automated"]["enabled"] = False
        self.assertFalse(self.report["argocd_application_check"]([app])["passed"])

    def test_argocd_unhealthy_states_and_empty_inventory(self):
        self.assertFalse(self.report["argocd_application_check"]([])["passed"])
        for state in ("Progressing", "Suspended", "Degraded", "Missing", "Unknown", "Stalled"):
            app = self.healthy_application()
            app["status"]["health"]["status"] = state
            result = self.report["argocd_application_check"]([app])
            self.assertFalse(result["passed"])
            self.assertIn(state, result["details"][0]["message"])
        app = self.healthy_application()
        app["status"] = {}
        self.assertFalse(self.report["argocd_application_check"]([app])["passed"])
        app["status"] = {"health": {"status": "Healthy"}, "sync": {"status": "OutOfSync"}}
        self.assertFalse(self.report["argocd_application_check"]([app])["passed"])

    def test_argocd_pauses_warnings_operations_and_rendering(self):
        base = self.healthy_application()
        variants = []
        for phase in ("Running", "Terminating", "Failed", "Error"):
            app = deepcopy(base)
            app["status"]["operationState"] = {
                "phase": phase,
                "startedAt": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            }
            variants.append(app)
        for metadata in (
            {"annotations": {"argocd.argoproj.io/skip-reconcile": "true"}},
            {"deletionTimestamp": "2026-11-01T00:00:00Z"},
        ):
            app = deepcopy(base)
            app["metadata"].update(metadata)
            variants.append(app)
        app = deepcopy(base)
        app["status"]["conditions"] = [{"type": "SharedResourceWarning", "message": "<warning>"}]
        variants.append(app)
        app = deepcopy(base)
        app["operation"] = {"sync": {}}
        variants.append(app)
        for app in variants:
            result = self.report["argocd_application_check"]([app])
            self.assertFalse(result["passed"])
            self.assertIn(result["details"][0]["message"], self.report["render_report"]([result]))
            rendered = self.report["render_html_report"]([result], "test")
            self.assertIn("example", rendered)
            self.assertNotIn("<warning>", rendered)
        result = self.report["argocd_application_check"]([variants[0]])
        self.assertIn("stalled", result["details"][0]["message"])
        base["status"]["operationState"] = {"phase": "Succeeded"}
        self.assertTrue(self.report["argocd_application_check"]([base])["passed"])

    def test_argocd_collection_failure_is_reported(self):
        def denied(path):
            raise PermissionError("denied")

        self.assertFalse(self.report["collect_argocd_check"](denied)["passed"])
        paths = []

        def kube(path):
            paths.append(path)
            return {"items": [self.healthy_application()]}

        self.assertTrue(self.report["collect_argocd_check"](kube)["passed"])
        self.assertEqual(paths, ["/apis/argoproj.io/v1alpha1/applications"])

    def test_tls_probe_selects_ingress_controller_by_class(self):
        for ingress_class, destination in [
            ("traefik", "traefik.traefik.svc.cluster.local"),
            ("traefik-private", "traefik-private.traefik.svc.cluster.local"),
        ]:
            with self.subTest(ingress_class=ingress_class):
                with (
                    patch.dict("os.environ", {}, clear=True),
                    patch(
                        "socket.create_connection", side_effect=RuntimeError("probe intercepted")
                    ) as connect,
                ):
                    with self.assertRaisesRegex(RuntimeError, "probe intercepted"):
                        self.report["live_tls_cert_days_left"]("test.k8s.my.lan", ingress_class)
                    connect.assert_called_once_with((destination, 443), timeout=10)

    def test_internal_public_domain_uses_public_trust(self):
        for host in (
            "grafana.int.andreybondarenko.com",
            "cloud.andreybondarenko.com",
            "legacy.k8s.my.lan",
        ):
            with (
                self.subTest(host=host),
                patch("ssl.create_default_context") as verified,
                patch("ssl._create_unverified_context") as unverified,
                patch("socket.create_connection", side_effect=RuntimeError("intercepted")),
            ):
                with self.assertRaisesRegex(RuntimeError, "intercepted"):
                    self.report["live_tls_cert_days_left"](host, "traefik-private")
                verified.assert_called_once_with()
                unverified.assert_not_called()

    def test_new_internal_suffix_is_classified_as_internal(self):
        internal = self.report["is_internal_ingress_host"]
        self.assertTrue(internal("grafana.int.andreybondarenko.com"))
        self.assertTrue(internal("grafana.w386.k8s.my.lan"))
        self.assertTrue(internal("other.example.com", "traefik-private"))
        self.assertFalse(internal("grafana.int.andreybondarenko.com.evil"))
        self.assertFalse(internal("cloud.andreybondarenko.com", "traefik"))

    def test_certificate_collection_checks_backend_expiry_and_failed_renewals(self):
        certificate = {
            "metadata": {"namespace": "openbao", "name": "backend-tls"},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "notAfter": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
            },
        }
        issuer = {
            "metadata": {"name": "internal-prod"},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }

        def kube(path):
            return {"items": [certificate] if path.endswith("/certificates") else [issuer]}

        check = self.report["collect_certificate_check"]
        self.assertTrue(check(kube)["passed"])
        certificate["status"]["failedIssuanceAttempts"] = 1
        self.assertFalse(check(kube)["passed"])
        del certificate["status"]["failedIssuanceAttempts"]
        certificate["status"]["notAfter"] = (
            datetime.now(timezone.utc) + timedelta(days=2)
        ).isoformat()
        self.assertFalse(check(kube)["passed"])
        certificate["status"]["notAfter"] = (
            datetime.now(timezone.utc) + timedelta(days=60)
        ).isoformat()
        issuer["status"]["conditions"][0]["status"] = "False"
        self.assertFalse(check(kube)["passed"])

    def test_certificate_collection_failure_keeps_email_report_running(self):
        def denied(path):
            raise PermissionError("denied")

        self.assertFalse(self.report["collect_certificate_check"](denied)["passed"])
        self.assertFalse(
            self.report["collect_certificate_check"](lambda _: {"items": []})["passed"]
        )

    def test_token_renewal_uses_cronjob_last_success(self):
        now = datetime.now(timezone.utc)
        cronjob = {
            "spec": {"suspend": False},
            "status": {"lastSuccessfulTime": (now - timedelta(minutes=30)).isoformat()},
        }

        recent, last_success = self.report["cronjob_recently_succeeded"](
            cronjob, now - timedelta(hours=24)
        )

        self.assertTrue(recent)
        self.assertIsNotNone(last_success)

    def test_suspended_or_stale_token_renewer_fails(self):
        now = datetime.now(timezone.utc)
        stale = {
            "spec": {"suspend": False},
            "status": {"lastSuccessfulTime": (now - timedelta(days=2)).isoformat()},
        }
        suspended = {
            "spec": {"suspend": True},
            "status": {"lastSuccessfulTime": now.isoformat()},
        }

        self.assertFalse(
            self.report["cronjob_recently_succeeded"](stale, now - timedelta(hours=24))[0]
        )
        self.assertFalse(
            self.report["cronjob_recently_succeeded"](suspended, now - timedelta(hours=24))[0]
        )

    def test_certificate_check_only_uses_tls_declared_hosts(self):
        ingress = {
            "spec": {
                "rules": [
                    {"host": "chat.w386.k8s.my.lan"},
                    {"host": "chat.andreybondarenko.com"},
                ],
                "tls": [
                    {
                        "hosts": ["chat.andreybondarenko.com"],
                        "secretName": "open-webui-tls",
                    }
                ],
            }
        }

        self.assertEqual(
            ["chat.andreybondarenko.com"],
            self.report["ingress_tls_hosts"](ingress),
        )

    def test_ingress_without_tls_is_not_certificate_checked(self):
        ingress = {"spec": {"rules": [{"host": "ollama.w386.k8s.my.lan"}]}}

        self.assertEqual([], self.report["ingress_tls_hosts"](ingress))

    def test_http01_solver_is_detected_from_cert_manager_label(self):
        ingress = {
            "metadata": {
                "labels": {"acme.cert-manager.io/http01-solver": "true"},
            }
        }

        self.assertTrue(self.report["is_http01_solver_ingress"](ingress))

    def test_active_job_pod_is_excluded_from_readiness_failures(self):
        for phase in ("Pending", "Running"):
            with self.subTest(phase=phase):
                pod = {
                    "metadata": {"ownerReferences": [{"kind": "Job"}]},
                    "status": {"phase": phase},
                }
                self.assertTrue(self.report["active_job_pod"](pod))

    def test_failed_job_pod_remains_reportable(self):
        pod = {
            "metadata": {"ownerReferences": [{"kind": "Job"}]},
            "status": {"phase": "Failed"},
        }

        self.assertFalse(self.report["active_job_pod"](pod))

    def test_openbao_health_check_uses_openbao_scrape_job(self):
        source = yaml.safe_load(SCRIPT_CONFIGMAP.read_text(encoding="utf-8"))["data"][
            "platform-health-report.py"
        ]

        self.assertIn('vault_core_unsealed{job="openbao"}', source)
        self.assertIn('up{job="openbao"}', source)
        self.assertIn('check("openbao"', source)
        self.assertNotIn('job="vault"', source)
        self.assertNotIn('check("vault"', source)


if __name__ == "__main__":
    unittest.main()
