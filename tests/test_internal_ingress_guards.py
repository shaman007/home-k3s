from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
INTERNAL_SUFFIX = ".k8s.my.lan"
MIDDLEWARE_ANNOTATION = "traefik.ingress.kubernetes.io/router.middlewares"
ALLOWED_GUARDS = {
    "traefik-internal-clients-only@kubernetescrd",
    "headlamp-local-network-only@kubernetescrd",
}


class InternalIngressGuardTest(unittest.TestCase):
    def test_every_internal_ingress_has_a_client_guard(self):
        missing = []
        for path in ROOT.rglob("ingress*.yaml"):
            if "DEPRECATED" in path.parts:
                continue
            for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
                if not document or document.get("kind") != "Ingress":
                    continue
                hosts = {
                    rule.get("host", "")
                    for rule in document.get("spec", {}).get("rules", [])
                }
                internal_hosts = sorted(host for host in hosts if host.endswith(INTERNAL_SUFFIX))
                if not internal_hosts:
                    continue
                middleware_refs = {
                    ref.strip()
                    for ref in document.get("metadata", {})
                    .get("annotations", {})
                    .get(MIDDLEWARE_ANNOTATION, "")
                    .split(",")
                    if ref.strip()
                }
                if middleware_refs.isdisjoint(ALLOWED_GUARDS):
                    missing.append(f"{path.relative_to(ROOT)}: {', '.join(internal_hosts)}")

        self.assertEqual([], missing)

    def test_shared_guard_allows_lan_and_cluster_pods(self):
        application = yaml.safe_load(
            (ROOT / "argocd/application-traefik.yaml").read_text(encoding="utf-8")
        )
        values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])
        middleware = next(
            item
            for item in values["extraObjects"]
            if item.get("kind") == "Middleware"
            and item.get("metadata", {}).get("name") == "internal-clients-only"
        )

        self.assertEqual(
            ["192.168.1.0/24", "10.42.0.0/16"],
            middleware["spec"]["ipAllowList"]["sourceRange"],
        )


if __name__ == "__main__":
    unittest.main()
