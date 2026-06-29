from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "argocd" / "application-metrics-server.yaml"
POLICY_APP = ROOT / "argocd" / "application-metrics-server-network-policy.yaml"
KUBELET_POLICY = ROOT / "kube-system" / "cilium-network-policy-metrics-server-allow-egress-kubelets.yaml"


class MetricsServerGitopsTest(unittest.TestCase):
    def test_metrics_server_app_installs_official_chart(self):
        source = APP.read_text(encoding="utf-8")

        self.assertIn("name: metrics-server", source)
        self.assertIn("repoURL: 'https://kubernetes-sigs.github.io/metrics-server/'", source)
        self.assertIn("chart: metrics-server", source)
        self.assertIn("targetRevision: 3.13.1", source)
        self.assertIn("releaseName: metrics-server", source)
        self.assertIn("k8s-app: metrics-server", source)
        self.assertIn("--kubelet-insecure-tls", source)

    def test_metrics_server_network_policy_app_includes_metrics_server_files(self):
        source = POLICY_APP.read_text(encoding="utf-8")

        self.assertIn("path: kube-system", source)
        self.assertIn("cilium-network-policy-metrics-server-allow-egress-kubelets.yaml", source)
        self.assertIn("network-policy-metrics-server-default-deny.yaml", source)
        self.assertIn("network-policy-metrics-server-allow-ingress-https.yaml", source)

    def test_metrics_server_cilium_policy_allows_node_kubelets(self):
        source = KUBELET_POLICY.read_text(encoding="utf-8")

        self.assertIn("kind: CiliumNetworkPolicy", source)
        self.assertIn("k8s-app: metrics-server", source)
        self.assertIn("- host", source)
        self.assertIn("- remote-node", source)
        self.assertIn('port: "10250"', source)


if __name__ == "__main__":
    unittest.main()
