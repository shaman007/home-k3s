from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
HARBOR = "harbor.andreybondarenko.com"

BOOTSTRAP_IMAGE_FILES = {
    Path("argocd/application-external-secrets.yaml"),
    Path("argocd/application-gpu-operator.yaml"),
    Path("argocd/application-harbor.yaml"),
    Path("argocd/application-metrics-server.yaml"),
    Path("argocd/application-reloader.yaml"),
    Path("argocd/application-traefik.yaml"),
    Path("harbor/values.yaml"),
    Path("talos-gpu-worker-patch.yaml"),
    Path("traefik/values.yaml"),
}

EXPECTED_HELM_IMAGES = {
    "application-external-secrets.yaml": {
        ("global", "repository"): "ghcr.io/external-secrets/external-secrets",
    },
    "application-metrics-server.yaml": {
        ("image", "repository"): "registry.k8s.io/metrics-server/metrics-server",
    },
    "application-reloader.yaml": {
        ("image", "repository"): "ghcr.io/stakater/reloader",
    },
}

def nested_value(values: dict, path: tuple[str, ...]):
    current = values
    for key in path:
        current = current[key]
    return current


def helm_values(application_name: str) -> dict:
    application = yaml.safe_load(
        (ROOT / "argocd" / application_name).read_text(encoding="utf-8")
    )
    return yaml.safe_load(application["spec"]["source"]["helm"]["values"])


class HarborProxyCacheTest(unittest.TestCase):
    def test_direct_image_declarations_use_harbor_or_are_bootstrap_exceptions(self):
        image_pattern = re.compile(r"^\s*(?:-\s*)?image:\s*['\"]?([^'\"#\s]+)")
        violations = []

        for manifest in ROOT.rglob("*.yaml"):
            relative = manifest.relative_to(ROOT)
            if relative.parts[0] == "DEPRECATED":
                continue
            for line_number, line in enumerate(
                manifest.read_text(encoding="utf-8").splitlines(), start=1
            ):
                match = image_pattern.match(line)
                if not match or match.group(1).startswith(f"{HARBOR}/"):
                    continue
                if relative not in BOOTSTRAP_IMAGE_FILES:
                    violations.append(f"{relative}:{line_number}: {match.group(1)}")

        self.assertEqual(violations, [])

    def test_harbor_trivy_has_no_cpu_limit(self):
        application = yaml.safe_load(
            (ROOT / "argocd/application-harbor.yaml").read_text(encoding="utf-8")
        )
        values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])

        self.assertIsNone(values["trivy"]["resources"]["limits"]["cpu"])

    def test_acme_solver_has_no_cpu_limit(self):
        application = yaml.safe_load(
            (ROOT / "argocd/application-cert-manager.yaml").read_text(
                encoding="utf-8"
            )
        )
        values = yaml.safe_load(
            application["spec"]["sources"][0]["helm"]["values"]
        )

        self.assertIn(
            "--acme-http01-solver-resource-limits-cpu=0", values["extraArgs"]
        )

    def test_platform_helm_workloads_use_upstream_images(self):
        for application, expected in EXPECTED_HELM_IMAGES.items():
            values = helm_values(application)
            for path, image in expected.items():
                self.assertEqual(nested_value(values, path), image)

    def test_proxy_reconciler_covers_all_declared_upstreams(self):
        reconciler = (ROOT / "harbor" / "reconcile-proxy-caches.sh").read_text(
            encoding="utf-8"
        )
        for definition in (
            "dockerhub dockerhub https://hub.docker.com docker-hub",
            "quay quay https://quay.io quay",
            "github github https://ghcr.io github-ghcr",
            "google google https://gcr.io docker-registry",
            "kubernetes k8s https://registry.k8s.io docker-registry",
            "elastic elastic https://docker.elastic.co docker-registry",
            "nvidia nvidia https://nvcr.io docker-registry",
            "ecr-public ecr https://public.ecr.aws docker-registry",
        ):
            self.assertIn(f"reconcile_proxy {definition}", reconciler)


if __name__ == "__main__":
    unittest.main()
