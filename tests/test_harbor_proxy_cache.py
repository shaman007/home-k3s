"""Verify Harbor proxy-cache routing and approved direct-upstream image exceptions."""

import re
import unittest
from pathlib import Path

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
    Path("talos/w386-install.yaml"),
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

EXPECTED_DIRECT_UPSTREAM_IMAGES = {
    Path("image-builder/cron-job-podman-builder.yaml"): {
        "quay.io/podman/stable",
        "registry.k8s.io/git-sync/git-sync",
    },
    Path("karakeep/deployment-chrome.yaml"): {
        "ghcr.io/karakeep-app/karakeep-chrome",
    },
}

# SeaweedFS serves Longhorn backups needed to recover Harbor itself.
EXPECTED_PINNED_UPSTREAM_IMAGES = {
    Path("seaweedfs/deployment-seaweedfs-s3.yaml"): {
        "docker.io/library/busybox",
        "docker.io/chrislusf/seaweedfs",
    },
}


def is_expected_direct_upstream(relative: Path, image: str) -> bool:
    """Scope upstream exceptions by file/repository and require pins for DR images."""
    pinned = any(
        re.fullmatch(re.escape(repository) + r":[^@\s]+@sha256:[0-9a-f]{64}", image)
        for repository in EXPECTED_PINNED_UPSTREAM_IMAGES.get(relative, set())
    )
    return pinned or (
        "@sha256:" not in image and any(
            image.startswith(f"{repository}:")
            for repository in EXPECTED_DIRECT_UPSTREAM_IMAGES.get(relative, set())
        )
    )


def nested_value(values: dict, path: tuple[str, ...]):
    """Resolve a nested Helm value through the supplied sequence of keys."""
    current = values
    for key in path:
        current = current[key]
    return current


def helm_values(application_name: str) -> dict:
    """Parse inline Helm values from the named Argo CD application."""
    application = yaml.safe_load((ROOT / "argocd" / application_name).read_text(encoding="utf-8"))
    return yaml.safe_load(application["spec"]["source"]["helm"]["values"])


class HarborProxyCacheTest(unittest.TestCase):
    """Check approved image origins, proxy-cache coverage, and relevant resource contracts."""
    def test_seaweedfs_upstream_exception_is_scoped_and_pinned(self):
        """Do not permit other files, repositories or mutable recovery images."""
        path = Path("seaweedfs/deployment-seaweedfs-s3.yaml")
        image = "docker.io/chrislusf/seaweedfs:4.53@sha256:" + "a" * 64
        self.assertTrue(is_expected_direct_upstream(path, image))
        for candidate_path, candidate_image in (
            (Path("seaweedfs/media-cache.yaml"), image),
            (path, image.replace("chrislusf/seaweedfs", "other/seaweedfs")),
            (path, "docker.io/chrislusf/seaweedfs:4.53"),
            (path, image[:-1]),
        ):
            with self.subTest(path=candidate_path, image=candidate_image):
                self.assertFalse(is_expected_direct_upstream(candidate_path, candidate_image))

    def test_direct_image_declarations_use_harbor_or_are_approved_exceptions(self):
        """Verify direct image declarations use Harbor or are approved exceptions."""
        image_pattern = re.compile(r"^\s*(?:-\s*)?image:\s*['\"]?([^'\"#\s]+)")
        violations = []

        for manifest in ROOT.rglob("*.yaml"):
            relative = manifest.relative_to(ROOT)
            if relative.parts[0] == "DEPRECATED" or str(relative).startswith(
                "tools/godaddy-webhook/chart/templates/"
            ):
                continue
            for line_number, line in enumerate(
                manifest.read_text(encoding="utf-8").splitlines(), start=1
            ):
                match = image_pattern.match(line)
                if not match or match.group(1).startswith(f"{HARBOR}/"):
                    continue
                if relative not in BOOTSTRAP_IMAGE_FILES and not is_expected_direct_upstream(
                    relative, match.group(1)
                ):
                    violations.append(f"{relative}:{line_number}: {match.group(1)}")

        self.assertEqual(violations, [])

    def test_harbor_trivy_has_no_cpu_limit(self):
        """Verify Harbor Trivy has no CPU limit."""
        application = yaml.safe_load(
            (ROOT / "argocd/application-harbor.yaml").read_text(encoding="utf-8")
        )
        values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])

        self.assertIsNone(values["trivy"]["resources"]["limits"]["cpu"])

    def test_acme_solver_has_no_cpu_limit(self):
        """Verify ACME solver has no CPU limit."""
        application = yaml.safe_load(
            (ROOT / "argocd/application-cert-manager.yaml").read_text(encoding="utf-8")
        )
        values = yaml.safe_load(application["spec"]["sources"][0]["helm"]["values"])

        self.assertNotIn(
            "--acme-http01-solver-resource-limits-cpu=0",
            values.get("extraArgs", []),
        )

    def test_platform_helm_workloads_use_upstream_images(self):
        """Verify platform Helm workloads use upstream images."""
        for application, expected in EXPECTED_HELM_IMAGES.items():
            values = helm_values(application)
            for path, image in expected.items():
                self.assertEqual(nested_value(values, path), image)

    def test_proxy_reconciler_covers_all_declared_upstreams(self):
        """Verify proxy reconciler covers all declared upstreams."""
        reconciler = (ROOT / "harbor" / "reconcile-proxy-caches.sh").read_text(encoding="utf-8")
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
