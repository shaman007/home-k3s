"""Verify Kubernetes API egress coverage in managed NetworkPolicies."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVICE_CIDR = "10.43.0.1/32"
CONTROL_PLANE_LAN_CIDR = "192.168.1.0/24"


def active_yaml_files():
    """Yield repository YAML paths outside the deprecated manifest archive."""
    for path in ROOT.rglob("*.yaml"):
        if "DEPRECATED" in path.parts:
            continue
        yield path


def has_port(document: str, port: int) -> bool:
    """Match an exact network-policy port without accepting numeric prefixes."""
    return re.search(rf"port:\s*{port}\b", document) is not None


class KubernetesApiNetworkPolicyTest(unittest.TestCase):
    """Require API egress policies to cover the current control-plane networks."""
    def test_kubernetes_api_policies_include_current_control_plane_endpoint(self):
        """Verify kubernetes API policies include current control plane endpoint."""
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
                if any(
                    cidr not in document for cidr in (CONTROL_PLANE_LAN_CIDR, "192.168.30.0/24")
                ):
                    offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], sorted(set(offenders)))


if __name__ == "__main__":
    unittest.main()
