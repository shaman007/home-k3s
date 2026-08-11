from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CONFIGMAP = ROOT / "metrics" / "config-map-platform-health-report-scripts.yaml"


def load_report_functions():
    configmap = yaml.safe_load(SCRIPT_CONFIGMAP.read_text(encoding="utf-8"))
    namespace = {"__name__": "platform_health_report_test"}
    exec(compile(configmap["data"]["platform-health-report.py"], str(SCRIPT_CONFIGMAP), "exec"), namespace)
    return namespace


class PlatformHealthReportLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_report_functions()

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

        self.assertFalse(self.report["cronjob_recently_succeeded"](stale, now - timedelta(hours=24))[0])
        self.assertFalse(self.report["cronjob_recently_succeeded"](suspended, now - timedelta(hours=24))[0])

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

    def test_active_job_pod_is_excluded_from_readiness_failures(self):
        pod = {
            "metadata": {"ownerReferences": [{"kind": "Job"}]},
            "status": {"phase": "Running"},
        }

        self.assertTrue(self.report["active_job_pod"](pod))

    def test_pending_or_failed_job_pod_remains_reportable(self):
        for phase in ("Pending", "Failed"):
            with self.subTest(phase=phase):
                pod = {
                    "metadata": {"ownerReferences": [{"kind": "Job"}]},
                    "status": {"phase": phase},
                }
                self.assertFalse(self.report["active_job_pod"](pod))


if __name__ == "__main__":
    unittest.main()
