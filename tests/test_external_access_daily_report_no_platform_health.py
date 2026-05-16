from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_MANIFEST = ROOT / "metrics" / "config-map-external-access-daily-report-scripts.yaml"
PLATFORM_APP = ROOT / "argocd" / "application-platform-health.yaml"


class ExternalAccessDailyReportNoPlatformHealthTest(unittest.TestCase):
    def test_external_access_report_does_not_embed_platform_health(self):
        source = SCRIPT_MANIFEST.read_text(encoding="utf-8")

        forbidden_fragments = [
            "collect_platform_health_report",
            "render_platform_html_section",
            "platform_health",
            "Platform health",
            "platform-health-report-scripts",
            "platform_health_",
        ]
        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, source)

    def test_platform_health_app_does_not_grant_external_access_report_rbac(self):
        source = PLATFORM_APP.read_text(encoding="utf-8")

        self.assertNotIn("cluster-role-binding-external-access-daily-report-platform-health.yaml", source)


if __name__ == "__main__":
    unittest.main()
