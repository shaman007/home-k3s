"""Keep static CLI assessments aligned with their deployed report source."""

import ast
import hashlib
from pathlib import Path
from unittest.mock import patch

import yaml
import test_platform_health_report_logic as deployed
from tools.ops import platform_checks

NAMES = set(platform_checks.ASSESSMENT_NAMES)

ROOT = Path(__file__).resolve().parents[1]


class StaticAssessmentParityTest(deployed.PlatformHealthReportLogicTest):
    """Run the deployed behavior fixtures against the static CLI implementations."""

    @classmethod
    def setUpClass(cls):
        """Swap pure functions only, retaining the report's mockable clock hooks."""
        super().setUpClass()
        cls.report.update(
            {name: getattr(platform_checks, name) for name in NAMES - {"utc_now"}}
        )
        clock = patch.object(platform_checks, "utc_now", cls.report_clock)
        clock.start()
        cls.addClassCleanup(clock.stop)

    @classmethod
    def report_clock(cls):
        """Resolve the mutable fixture clock at call time, not at patch creation."""
        return cls.report["utc_now"]()

    def test_deployed_assessment_source_has_not_drifted(self):
        """Require an intentional static-port review whenever owning logic changes."""
        config = yaml.safe_load(
            (ROOT / "metrics/config-map-platform-health-report-scripts.yaml").read_text(
                encoding="utf-8"
            )
        )
        nodes = [
            node
            for node in ast.parse(config["data"]["platform-health-report.py"]).body
            if isinstance(node, ast.FunctionDef) and node.name in NAMES
        ]
        self.assertEqual({node.name for node in nodes}, NAMES)
        fingerprint = hashlib.sha256(
            ast.dump(ast.Module(body=nodes, type_ignores=[])).encode()
        ).hexdigest()
        self.assertEqual(
            platform_checks.SOURCE_SHA256,
            fingerprint,
            "Review static platform_checks against the changed deployed report",
        )
