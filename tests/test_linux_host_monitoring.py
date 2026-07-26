import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS = ROOT / "metrics" / "kubernetes-prometheus" / "config-map-prometheus-server-conf.yaml"
DASHBOARD = ROOT / "metrics" / "grafana" / "config-map-grafana-dashboard-linux-host.yaml"
GRAFANA = ROOT / "metrics" / "grafana" / "deployment-grafana.yaml"
EXTERNAL_EGRESS = ROOT / "metrics" / "network-policy-monitoring-allow-egress-prometheus-external.yaml"


class LinuxHostMonitoringTest(unittest.TestCase):
    def setUp(self):
        prometheus_config_map = yaml.safe_load(PROMETHEUS.read_text(encoding="utf-8"))
        self.prometheus = yaml.safe_load(prometheus_config_map["data"]["prometheus.yaml"])
        self.rules = yaml.safe_load(prometheus_config_map["data"]["prometheus.rules"])

    def test_linux_host_scrape_is_opted_out_of_down_alerts(self):
        job = next(
            job
            for job in self.prometheus["scrape_configs"]
            if job["job_name"] == "linux-host-node-exporter"
        )
        static_config = job["static_configs"][0]

        self.assertEqual(
            static_config["targets"], ["backup.andreybondarenko.com:9100"]
        )
        self.assertEqual(static_config["labels"]["host"], "backup")
        self.assertEqual(static_config["labels"]["alert_on_down"], "false")

        target_down = next(
            rule
            for group in self.rules["groups"]
            for rule in group["rules"]
            if rule["alert"] == "TargetDown"
        )
        self.assertIn('up{alert_on_down!="false"}', target_down["expr"])

    def test_linux_host_dashboard_is_valid_and_provisioned(self):
        config_map = yaml.safe_load(DASHBOARD.read_text(encoding="utf-8"))
        dashboard = json.loads(config_map["data"]["linux-host.json"])

        self.assertEqual(dashboard["uid"], "linux-host-overview")
        self.assertEqual(len(dashboard["panels"]), 10)
        for panel in dashboard["panels"]:
            self.assertNotIn("alert", panel)
        self.assertIn(
            "grafana-dashboard-linux-host", GRAFANA.read_text(encoding="utf-8")
        )

    def test_prometheus_can_reach_node_exporter_port(self):
        policy = yaml.safe_load(EXTERNAL_EGRESS.read_text(encoding="utf-8"))
        ports = {
            port["port"]
            for egress in policy["spec"]["egress"]
            for port in egress.get("ports", [])
        }

        self.assertIn(9100, ports)


if __name__ == "__main__":
    unittest.main()
