from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVICE_CIDR = "10.43.0.1/32"
CONTROL_PLANE_LAN_CIDR = "192.168.1.0/24"
OLD_CONTROL_PLANE_CIDR = "192.168.1.209/32"


def active_yaml_files():
    for path in ROOT.rglob("*.yaml"):
        if "DEPRECATED" in path.parts:
            continue
        yield path


def has_port(document: str, port: int) -> bool:
    return re.search(rf"port:\s*{port}\b", document) is not None


class KubernetesApiNetworkPolicyTest(unittest.TestCase):
    def test_redis_operator_has_cilium_kube_apiserver_policy(self):
        source = (
            ROOT
            / "ot-operators"
            / "cilium-network-policy-redis-operator-allow-kube-apiserver.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn("kind: CiliumNetworkPolicy", source)
        self.assertIn("name: redis-operator", source)
        self.assertIn("toEntities:", source)
        self.assertIn("- kube-apiserver", source)
        self.assertIn("serviceName: kubernetes", source)

    def test_kubernetes_api_policies_include_current_control_plane_endpoint(self):
        offenders = []

        for path in active_yaml_files():
            source = path.read_text(encoding="utf-8")
            for document in source.split("\n---"):
                if SERVICE_CIDR not in document:
                    continue
                if "kind: NetworkPolicy" not in document:
                    continue
                if not has_port(document, 443):
                    continue
                if CONTROL_PLANE_LAN_CIDR not in document:
                    offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], sorted(set(offenders)))

    def test_no_kubernetes_api_policy_uses_old_k3s_endpoint(self):
        offenders = []

        for path in active_yaml_files():
            source = path.read_text(encoding="utf-8")
            for document in source.split("\n---"):
                if OLD_CONTROL_PLANE_CIDR not in document:
                    continue
                if has_port(document, 6443):
                    offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], sorted(set(offenders)))


if __name__ == "__main__":
    unittest.main()
