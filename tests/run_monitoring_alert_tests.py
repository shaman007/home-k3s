"""Run boundary/join fixtures against rules extracted from the shipped ConfigMap.

Usage: python tests/run_monitoring_alert_tests.py /path/to/promtool
Requires PyYAML; does not access the cluster.
"""

import pathlib
import subprocess
import sys
import tempfile
import yaml

root = pathlib.Path(__file__).resolve().parents[1]
config = yaml.safe_load(
    (root / "metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml").read_text()
)
rules = yaml.safe_load(config["data"]["prometheus.rules"])
fixtures = yaml.safe_load((root / "tests/monitoring-alerts.test.yaml").read_text())
with tempfile.TemporaryDirectory() as directory:
    directory = pathlib.Path(directory)
    full = directory / "all.rules.yaml"
    full.write_text(yaml.safe_dump(rules, sort_keys=False))
    subprocess.run([sys.argv[1], "check", "rules", str(full)], check=True)
    # Inventory recording rules deliberately omitted so fixtures can simulate absence.
    tested = directory / "tested.rules.yaml"
    tested.write_text(
        yaml.safe_dump(
            {
                "groups": [
                    {
                        "name": "tested",
                        "rules": [
                            rule
                            for group in rules["groups"]
                            for rule in group["rules"]
                            if "alert" in rule
                        ],
                    }
                ]
            },
            sort_keys=False,
        )
    )
    fixtures["rule_files"] = [str(tested)]
    test = directory / "test.yaml"
    test.write_text(yaml.safe_dump(fixtures, sort_keys=False))
    subprocess.run([sys.argv[1], "test", "rules", str(test)], check=True)
    # Queue fixtures also exercise the shipped normalization recording rules.
    queues = yaml.safe_load((root / "tests/queue-alerts.test.yaml").read_text())
    queues["rule_files"] = [str(full)]
    test.write_text(yaml.safe_dump(queues, sort_keys=False))
    subprocess.run([sys.argv[1], "test", "rules", str(test)], check=True)
