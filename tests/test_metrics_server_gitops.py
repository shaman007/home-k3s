"""Check metrics-server manifests and their Argo CD integration."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "argocd" / "application-metrics-server.yaml"
POLICY_APP = ROOT / "argocd" / "application-metrics-server-network-policy.yaml"
KUBELET_POLICY = (
    ROOT / "kube-system" / "cilium-network-policy-metrics-server-allow-egress-kubelets.yaml"
)


class MetricsServerGitopsTest(unittest.TestCase):
    """Check the official chart, GitOps wiring, and kubelet network access."""
    def test_metrics_server_app_installs_official_chart(self):
        """Verify metrics server app installs official chart."""
        source = APP.read_text(encoding="utf-8")

        self.assertIn("name: metrics-server", source)
        self.assertIn("repoURL: 'https://kubernetes-sigs.github.io/metrics-server/'", source)
        self.assertIn("chart: metrics-server", source)
        self.assertIn("targetRevision: 3.14.0", source)
        self.assertIn("releaseName: metrics-server", source)
        self.assertIn("k8s-app: metrics-server", source)
        self.assertIn("--kubelet-insecure-tls", source)

    def test_metrics_server_network_policy_app_includes_metrics_server_files(self):
        """Verify metrics server network policy app includes metrics server files."""
        source = POLICY_APP.read_text(encoding="utf-8")

        self.assertIn("path: kube-system", source)
        self.assertIn("cilium-network-policy-metrics-server-allow-egress-kubelets.yaml", source)
        self.assertIn("network-policy-metrics-server-default-deny.yaml", source)
        self.assertIn("network-policy-metrics-server-allow-ingress-https.yaml", source)

    def test_metrics_server_cilium_policy_allows_node_kubelets(self):
        """Verify metrics server cilium policy allows node kubelets."""
        source = KUBELET_POLICY.read_text(encoding="utf-8")

        self.assertIn("kind: CiliumNetworkPolicy", source)
        self.assertIn("k8s-app: metrics-server", source)
        self.assertIn("- host", source)
        self.assertIn("- remote-node", source)
        self.assertIn('port: "10250"', source)


if __name__ == "__main__":
    unittest.main()
