from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOGS_CHECK_APP = ROOT / "argocd" / "application-logs-check.yaml"
LOGS_CHECK_CRON = ROOT / "metrics" / "cron-job-logs-check.yaml"
LOGS_CHECK_SCRIPT = ROOT / "metrics" / "config-map-logs-check-scripts.yaml"
LOGS_CHECK_SECRET = ROOT / "metrics" / "external-secret-logs-check-grafana-token.yaml"


class LogsCheckGrafanaAccessTest(unittest.TestCase):
    def test_logs_check_app_includes_grafana_token_secret(self):
        source = LOGS_CHECK_APP.read_text(encoding="utf-8")

        self.assertIn("external-secret-logs-check-grafana-token.yaml", source)

    def test_logs_check_cron_reads_grafana_token_from_secret(self):
        source = LOGS_CHECK_CRON.read_text(encoding="utf-8")

        self.assertIn("- name: GRAFANA_TOKEN", source)
        self.assertIn("name: logs-check-grafana-token", source)
        self.assertIn("key: token", source)
        self.assertIn("optional: true", source)

    def test_logs_check_script_uses_authenticated_grafana_api(self):
        source = LOGS_CHECK_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('for path in ("/api/health", "/api/user")', source)
        self.assertIn('f"{base_url.rstrip(\'/\')}/api/datasources"', source)
        self.assertIn('"source": "grafana_api"', source)
        self.assertIn('"source": "kubernetes_configmap"', source)

    def test_logs_check_secret_uses_monitoring_grafana_token(self):
        source = LOGS_CHECK_SECRET.read_text(encoding="utf-8")

        self.assertIn("name: logs-check-grafana-token", source)
        self.assertIn("key: monitoring", source)
        self.assertIn("property: GRAFANA_TOKEN", source)


if __name__ == "__main__":
    unittest.main()
