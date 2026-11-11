#!/usr/bin/env python3
"""Validate Kubernetes runtime-contract patterns that schema checks miss."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml


SUSPICIOUS_HTTP_PROBE_PATHS = {
    "/": (
        "root routes are brittle health checks; prefer a dedicated health endpoint or "
        "tcpSocket when you only need to verify the listener is up"
    ),
    "/metrics": (
        "use tcpSocket for metrics-only endpoints unless the application documents "
        "/metrics as a supported health check"
    ),
    "/wp-json/wp-site-health/v1": (
        "prefer a lightweight dedicated health endpoint instead of a heavyweight "
        "application diagnostic route"
    ),
}

DEPRECATED_ARGS = {
    "--collector.filesystem.ignored-mount-points": (
        "use --collector.filesystem.mount-points-exclude with current node-exporter"
    ),
}

WORKLOAD_KINDS = {"Deployment", "DaemonSet", "StatefulSet"}

ALLOWED_HTTP_PROBE_PATHS = {
    ("dawarich/deployment-dawarich.yaml", "dawarich-sidekiq", "readinessProbe", "/"): (
        "temporary exception until the sidekiq container gets a workload-specific readiness signal"
    ),
}

EXPECTED_EXTERNAL_SECRET_REFRESH_INTERVAL = "15m"
EXPECTED_SECRET_STORE_REFRESH_INTERVAL = 900


def repo_root() -> Path:
    """Resolve the checkout root through Git without changing repository state."""
    return Path(
        subprocess.run(
            ["/usr/bin/git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )


def tracked_yaml_files(root: Path) -> list[Path]:
    """List tracked YAML inputs while excluding archives and raw Helm templates."""
    result = subprocess.run(
        ["/usr/bin/git", "ls-files", "-z", "--", "*.yaml", "*.yml"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    files = []
    for entry in result.stdout.decode("utf-8").split("\0"):
        if not entry:
            continue
        if entry.startswith(
            ("DEPRECATED/", "mastodon/chart/", "tools/godaddy-webhook/chart/templates/")
        ):
            continue
        path = root / entry
        if not path.exists():
            continue
        files.append(path)
    return files


def load_documents(path: Path) -> list[tuple[int, dict]]:
    """Read mapping documents and report parse locations without source snippets."""
    try:
        raw_documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        # Parser exceptions can quote Secret values from the source document.
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise RuntimeError(f"{path}: unable to parse YAML{location}") from None

    documents = []
    for index, document in enumerate(raw_documents, start=1):
        if isinstance(document, dict):
            documents.append((index, document))
    return documents


def workload_containers(document: dict) -> list[dict]:
    """Return regular containers from a workload template, or an empty list."""
    try:
        return document["spec"]["template"]["spec"]["containers"]
    except KeyError:
        return []


def check_http_probe_paths(path: Path, document_index: int, document: dict) -> list[str]:
    """Report brittle HTTP probe routes unless an exact exception is reviewed."""
    errors: list[str] = []
    if document.get("kind") not in WORKLOAD_KINDS:
        return errors

    for container in workload_containers(document):
        container_name = container.get("name", "<unnamed>")
        for probe_name in ("livenessProbe", "readinessProbe", "startupProbe"):
            probe = container.get(probe_name)
            if not isinstance(probe, dict):
                continue
            http_get = probe.get("httpGet")
            if not isinstance(http_get, dict):
                continue
            probe_path = http_get.get("path")
            allowed_reason = ALLOWED_HTTP_PROBE_PATHS.get(
                (path.as_posix(), container_name, probe_name, probe_path)
            )
            if allowed_reason:
                continue
            message = SUSPICIOUS_HTTP_PROBE_PATHS.get(probe_path)
            if message:
                errors.append(
                    (
                        f"{path}: document {document_index}, container {container_name}, "
                        f"{probe_name} path {probe_path!r} is suspicious: {message}."
                    )
                )
    return errors


def check_deprecated_args(path: Path, document_index: int, document: dict) -> list[str]:
    """Report retired container flags and their supported replacements."""
    errors: list[str] = []
    if document.get("kind") not in WORKLOAD_KINDS:
        return errors

    for container in workload_containers(document):
        container_name = container.get("name", "<unnamed>")
        for arg in container.get("args", []) or []:
            for deprecated, replacement in DEPRECATED_ARGS.items():
                if isinstance(arg, str) and arg.startswith(deprecated):
                    errors.append(
                        (
                            f"{path}: document {document_index}, container {container_name}"
                            f" uses deprecated arg {deprecated!r}: {replacement}."
                        )
                    )
    return errors


def check_deprecated_service_fields(path: Path, document_index: int, document: dict) -> list[str]:
    """Reject legacy Service address fields with provider-specific alternatives."""
    if document.get("kind") != "Service":
        return []
    replacements = {
        "externalIPs": "use an explicit NodePort or LoadBalancer endpoint",
        "loadBalancerIP": "use the load balancer provider's address annotation",
    }
    return [
        f"{path}: document {document_index}, Service uses deprecated spec.{field}: {replacement}."
        for field, replacement in replacements.items()
        if field in document.get("spec", {})
    ]


def check_external_secret_targets(path: Path, document_index: int, document: dict) -> list[str]:
    """Require explicit ExternalSecret targets without logging their values."""
    errors: list[str] = []
    if document.get("kind") != "ExternalSecret":
        return errors

    spec = document.get("spec", {})
    target = spec.get("target")
    if not isinstance(target, dict):
        errors.append(
            (
                f"{path}: document {document_index}"
                f", ExternalSecret is missing spec.target; declare an explicit target secret."
            )
        )
        return errors

    if not target.get("name"):
        errors.append(
            f"{path}: document {document_index}, ExternalSecret is missing spec.target.name."
        )
    if not target.get("creationPolicy"):
        errors.append(
            (
                f"{path}: document {document_index}"
                f", ExternalSecret is missing spec.target.creationPolicy."
            )
        )
    return errors


def check_secret_refresh_intervals(path: Path, document_index: int, document: dict) -> list[str]:
    """Check the reviewed refresh cadence for External Secrets resources."""
    errors: list[str] = []
    kind = document.get("kind")
    spec = document.get("spec", {})
    refresh_interval = spec.get("refreshInterval")

    if kind == "ExternalSecret":
        if refresh_interval != EXPECTED_EXTERNAL_SECRET_REFRESH_INTERVAL:
            errors.append(
                (
                    f"{path}: document {document_index}"
                    f", ExternalSecret should set spec.refreshInterval to "
                    f"{EXPECTED_EXTERNAL_SECRET_REFRESH_INTERVAL!r} instead of the debug cadence."
                )
            )
        return errors

    if kind in {"SecretStore", "ClusterSecretStore"}:
        if refresh_interval not in {
            EXPECTED_SECRET_STORE_REFRESH_INTERVAL,
            str(EXPECTED_SECRET_STORE_REFRESH_INTERVAL),
        }:
            errors.append(
                (
                    f"{path}: document {document_index}, {kind} should set spec.refreshInterval to "
                    f"{EXPECTED_SECRET_STORE_REFRESH_INTERVAL} seconds (15 minutes)."
                )
            )

    return errors


def main() -> int:
    """Validate tracked manifests and return a nonzero status for contract failures."""
    root = repo_root()
    errors: list[str] = []

    for path in tracked_yaml_files(root):
        for document_index, document in load_documents(path):
            errors.extend(check_http_probe_paths(path.relative_to(root), document_index, document))
            errors.extend(check_deprecated_args(path.relative_to(root), document_index, document))
            errors.extend(
                check_deprecated_service_fields(path.relative_to(root), document_index, document)
            )
            errors.extend(
                check_external_secret_targets(path.relative_to(root), document_index, document)
            )
            errors.extend(
                check_secret_refresh_intervals(path.relative_to(root), document_index, document)
            )

    if errors:
        print("Runtime-contract validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Runtime-contract validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
