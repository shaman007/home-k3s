"""Enforce separate browser isolation and the canonical worker startup contract."""

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    """Load a non-secret Karakeep manifest."""
    return yaml.safe_load((ROOT / "karakeep" / name).read_text())


class KarakeepStartupTests(unittest.TestCase):
    """Prevent same-Pod init deadlocks, accidental routing and stale gate copies."""

    def test_browser_is_independent_and_not_selected_by_web_service(self):
        """The browser can start while the workers wait; HTTP never routes to CDP."""
        web = read("deployment-karakeep.yaml")["spec"]["template"]["spec"]
        browser = read("deployment-chrome.yaml")["spec"]["template"]
        self.assertEqual([c["name"] for c in web["containers"]], ["web"])
        volumes = {v["name"] for v in web["volumes"]}
        for container in web["containers"] + web["initContainers"]:
            self.assertTrue(
                {m["name"] for m in container["volumeMounts"]}.issubset(volumes)
            )
            self.assertTrue(all(m.get("mountPath") for m in container["volumeMounts"]))
        self.assertEqual(
            [c["name"] for c in web["initContainers"]], ["init-writable-paths"]
        )
        self.assertFalse(browser["spec"]["automountServiceAccountToken"])
        self.assertNotIn("initContainers", browser["spec"])
        self.assertFalse(
            all(
                browser["metadata"]["labels"].get(k) == v
                for k, v in read("service-karakeep.yaml")["spec"]["selector"].items()
            )
        )
        self.assertTrue(
            all(
                browser["metadata"]["labels"].get(k) == v
                for k, v in read("service-chrome.yaml")["spec"]["selector"].items()
            )
        )
        self.assertEqual(read("service-chrome.yaml")["spec"]["type"], "ClusterIP")
        chrome = browser["spec"]["containers"][0]
        self.assertEqual(chrome["securityContext"]["runAsUser"], 65534)
        self.assertNotIn("command", chrome)
        self.assertNotIn("envFrom", chrome)
        self.assertEqual(chrome["readinessProbe"]["httpGet"]["path"], "/json/version")
        self.assertEqual(
            {v["name"] for v in browser["spec"]["volumes"]}, {"dshm", "chrome-tmp"}
        )

    def test_cdp_policy_pairs_only_same_namespace_web_and_browser(self):
        """No Ingress, public VIP or broad CDP allowance is introduced."""
        for direction, source, destination in (
            ("ingress", "karakeep-chrome", "karakeep"),
            ("egress", "karakeep", "karakeep-chrome"),
        ):
            spec = read("network-policy-chrome-allow-" + direction + "-karakeep.yaml")[
                "spec"
            ]
            self.assertEqual(spec["podSelector"], {"matchLabels": {"app": source}})
            rule = spec[direction][0]
            self.assertEqual(
                rule["from" if direction == "ingress" else "to"],
                [{"podSelector": {"matchLabels": {"app": destination}}}],
            )
            self.assertEqual(rule["ports"], [{"protocol": "TCP", "port": 9222}])

    def test_worker_only_mount_has_exact_canonical_script(self):
        """Immutable gate projection never replaces web or migration entrypoints."""
        cm = read("config-map-worker-startup.yaml")
        self.assertTrue(cm["immutable"])
        self.assertEqual(
            cm["data"]["karakeep_worker_gate.cjs"],
            (ROOT / "tools/bootstrap/karakeep_worker_gate.cjs").read_text(),
        )
        web = read("deployment-karakeep.yaml")["spec"]["template"]["spec"]
        volume = next(v for v in web["volumes"] if v["name"] == "worker-startup")
        self.assertEqual(volume["configMap"]["name"], cm["metadata"]["name"])
        self.assertEqual(volume["configMap"]["defaultMode"], 0o555)
        env = read("config-map-karakeep-env.yaml")["data"]
        self.assertEqual(
            env["BROWSER_WEB_URL"], "http://chrome.karakeep.svc.cluster.local:9222"
        )
