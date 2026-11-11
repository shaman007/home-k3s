#!/usr/bin/env python3
"""Render the checked-out Argo applications without contacting Kubernetes.

Support the source forms used here; reject unsupported options instead of silently
validating a different deployment. Outputs may contain generated chart Secrets.
"""

import argparse
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.parse

import yaml
from ci_yaml import load, load_all
from http_download import fetch

ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/shaman007/home-k3s.git"


@dataclass(frozen=True)
class RenderContext:
    """Keep each source's repository, private scratch space and Kubernetes version together."""

    root: Path
    scratch: Path
    kubernetes_version: str


class HelmDownloadError(RuntimeError):
    """A transient chart download failure; diagnostics stay private."""


def github_chart_fallback(source, scratch):
    """Fetch the exact indexed chart through GitHub's release-asset API."""

    repo = source["repoURL"]
    if not repo.startswith("https://"):
        raise ValueError("Fallback requires an HTTPS Helm repository")
    index = load(fetch(repo.rstrip("/") + "/index.yaml").decode())
    entries = index["entries"][source["chart"]]
    entry = next(e for e in entries if str(e["version"]) == str(source["targetRevision"]))
    digest = entry.get("digest", "")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Fallback requires a SHA-256 chart digest")
    for url in entry["urls"]:
        parsed = urllib.parse.urlsplit(url)
        match = re.fullmatch(r"/([^/]+)/([^/]+)/releases/download/([^/]+)/([^/]+)", parsed.path)
        if parsed.scheme != "https" or parsed.netloc != "github.com" or not match:
            continue
        return download_github_asset(match, digest, scratch)
    raise ValueError("No GitHub release asset in the pinned chart index entry")


def download_github_asset(match, digest, scratch):
    """Verify the indexed digest before exposing a GitHub chart archive to Helm."""
    owner, repository, tag, filename = match.groups()
    api = f"https://api.github.com/repos/{owner}/{repository}/releases"
    release = json.loads(fetch(f"{api}/tags/{tag}"))
    asset = next(a for a in release["assets"] if a["name"] == urllib.parse.unquote(filename))
    archive = fetch(f"{api}/assets/{int(asset['id'])}", "application/octet-stream")
    if hashlib.sha256(archive).hexdigest() != digest:
        raise ValueError("Fallback chart digest mismatch")
    path = scratch / "verified-chart.tgz"
    path.write_bytes(archive)
    return path


def run(args, cwd=None):
    """Run a renderer with bounded transient-fetch retries and private diagnostics."""
    for attempt in range(3):
        result = subprocess.run(
            args, check=False, cwd=cwd, text=True, capture_output=True, timeout=300
        )
        if not result.returncode:
            return result.stdout
        # Kustomize fetches pinned GitHub bases with git. Retry fetch failures,
        # while keeping all subprocess diagnostics private (they may contain
        # rendered Secrets). Local YAML/patch failures still fail immediately.
        if args[:2] == ["kubectl", "kustomize"] and "git fetch" in result.stderr and attempt < 2:
            print(f"Remote Kustomize fetch failed; retrying ({attempt + 2}/3)", flush=True)
            time.sleep(2 ** (attempt + 1))
            continue
        transient_helm_download = (
            Path(args[0]).name == "helm"
            and args[1] == "template"
            and "failed to fetch https://github.com/" in result.stderr
            and re.search(r"\b(?:429|500|502|503|504)\b", result.stderr)
        )
        error = HelmDownloadError if transient_helm_download else RuntimeError
        raise error(
            (
                f"{args[0]} {args[1]} failed (exit {result.returncode}"
                f"); run this source locally to inspect its diagnostic output"
            )
        )


def local_path(root, value):
    """Resolve an existing path and reject escapes from the application source root."""
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes source root: {value}")
    if not path.exists():
        raise ValueError(f"Missing source path: {value}")
    return path


def matches(name, pattern):
    """Match case-sensitive filename globs, including brace-separated alternatives."""
    if pattern.startswith("{") and pattern.endswith("}"):
        return any(matches(name, p) for p in pattern[1:-1].split(","))
    return fnmatch.fnmatchcase(name, pattern)


def helm_chart_args(source, root):
    """Resolve a reviewed local chart or a version-pinned Helm/OCI chart reference."""
    repo = source["repoURL"]
    if "chart" not in source:
        if repo != REPO:
            raise ValueError("External Git-hosted charts need explicit support")
        args = [str(local_path(root, source["path"]))]
    else:
        chart = source["chart"]
        if repo.startswith(("http://", "https://")):
            args = [chart, "--repo", repo]
        else:
            args = [repo if repo.startswith("oci://") else "oci://" + repo]
            args[0] = args[0].rstrip("/") + "/" + chart
        args.extend(["--version", source["targetRevision"]])
    return args


def helm_values_args(options, sources, root, scratch):
    """Apply Argo values precedence while enforcing local values-reference boundaries."""
    args = []
    refs = {s["ref"]: s for s in sources if "ref" in s}
    for value in options.get("valueFiles", []):
        if not value.startswith("$"):
            raise ValueError("Chart-relative valueFiles need explicit support before use")
        ref, relative = value[1:].split("/", 1)
        if ref not in refs or refs[ref]["repoURL"] != REPO:
            raise ValueError(f"Unsupported values reference: {ref}")
        args.extend(["--values", str(local_path(root, relative))])
    # Argo precedence: parameters > valuesObject > values > valueFiles.
    if "valuesObject" in options or "values" in options:
        values_file = scratch / "values.yaml"
        values_file.write_text(
            yaml.safe_dump(options["valuesObject"])
            if "valuesObject" in options
            else options["values"]
        )
        args.extend(["--values", str(values_file)])
    for parameter in options.get("parameters", []):
        flag = "--set-string" if parameter.get("forceString", False) else "--set"
        args.extend([flag, parameter["name"] + "=" + parameter["value"]])
    return args


def helm_args(app, source, sources, context):
    """Translate supported Argo Helm options into an explicit render command."""
    options = source.get("helm", {})
    supported = {
        "releaseName",
        "valueFiles",
        "values",
        "valuesObject",
        "parameters",
        "skipCrds",
        "skipTests",
        "kubeVersion",
        "apiVersions",
    }
    if options.keys() - supported:
        raise ValueError(f"Unsupported Helm options: {sorted(options.keys() - supported)}")
    chart_args = helm_chart_args(source, context.root)
    args = [
        os.environ.get("HELM", "helm"),
        "template",
        options.get("releaseName", app["metadata"]["name"]),
        *chart_args,
        "--namespace",
        app["spec"]["destination"]["namespace"],
        "--kube-version",
        options.get("kubeVersion", context.kubernetes_version),
    ]
    if not options.get("skipCrds", False):
        args.append("--include-crds")
    if options.get("skipTests", False):
        args.append("--skip-tests")
    for version in options.get("apiVersions", []):
        args.extend(["--api-versions", version])
    args.extend(helm_values_args(options, sources, context.root, context.scratch))
    return args


def render_chart(args, source, scratch):
    """Render a chart with digest-verified fallback and exact OCI preamble removal."""
    try:
        output = run(args, cwd=scratch)
    except HelmDownloadError:
        print("GitHub chart download unavailable; trying digest-verified release API", flush=True)
        try:
            archive = github_chart_fallback(source, scratch)
        except Exception:
            # Network exceptions can include signed redirect URLs. Keep them private.
            raise RuntimeError("Digest-verified chart download fallback failed") from None
        fallback_args = args.copy()
        fallback_args[3] = str(archive)
        for flag in ("--repo", "--version"):
            if flag in fallback_args:
                position = fallback_args.index(flag)
                del fallback_args[position : position + 2]
        output = run(fallback_args, cwd=scratch)
    if args[3].startswith("oci://"):
        # Helm 4 writes OCI pull metadata to stdout before the YAML stream.
        # Remove only its known preamble, never arbitrary non-manifest YAML.
        output = re.sub(
            r"\APulled: [^\r\n]+\r?\nDigest: sha256:[0-9a-f]{64}\r?\n", "", output, count=1
        )
    return output


def render_directory(path, options, root):
    """Render only selected Kubernetes manifests from an explicit raw directory source."""
    if options.keys() - {"recurse", "include", "exclude"}:
        raise ValueError("Unsupported directory options")
    docs = []
    for file in sorted(path.rglob("*") if options.get("recurse") else path.iterdir()):
        if not file.is_file() or file.suffix not in {".yaml", ".yml", ".json"}:
            continue
        name = file.relative_to(path).as_posix()
        if not matches(name, options.get("include", "*")) or matches(
            name, options.get("exclude", "")
        ):
            continue
        for document in load_all(file.read_text()):
            if document is not None:
                if (
                    not isinstance(document, dict)
                    or not document.get("apiVersion")
                    or not document.get("kind")
                ):
                    raise ValueError(
                        f"Non-manifest in application source: {file.relative_to(root)}"
                    )
                docs.append(document)
    return yaml.safe_dump_all(docs, sort_keys=False)


def render_source(app, source, sources, context):
    """Render one supported Argo source, rejecting options CI cannot reproduce."""
    if source.keys() - {"repoURL", "targetRevision", "chart", "helm", "path", "directory", "ref"}:
        raise ValueError("Unsupported application source options")
    if "chart" in source:
        args = helm_args(app, source, sources, context)
        return render_chart(args, source, context.scratch)
    if source["repoURL"] != REPO:
        raise ValueError("External Git sources need explicit support before use")
    if "path" not in source and "ref" in source:
        return ""
    path = local_path(context.root, source["path"])
    if (path / "kustomization.yaml").exists() and "directory" not in source:
        return run(["kubectl", "kustomize", str(path)])
    if (path / "Chart.yaml").exists():
        if "directory" in source:
            raise ValueError("A Git-hosted chart cannot also be a raw directory source")
        return run(helm_args(app, source, sources, context), cwd=context.scratch)
    return render_directory(path, source.get("directory", {}), context.root)


def main():
    """Render selected applications into private files and write their inventory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--application",
        action="append",
        help="Render only these application names (local diagnosis)",
    )
    args = parser.parse_args()
    config = load((ROOT / "tools/ci/validation-config.yaml").read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("Output directory must be empty to prevent stale validation inputs")
    os.chmod(args.output, 0o700)
    applications = []
    for file in sorted((ROOT / "argocd").glob("*.yaml")):
        app = load(file.read_text())
        if isinstance(app, dict) and app.get("kind") == "Application":
            if not args.application or app["metadata"]["name"] in args.application:
                applications.append(app)
    if not applications:
        raise ValueError("No applications selected")
    inventory = []
    for app in applications:
        name = app["metadata"]["name"]
        print(f"Rendering {name}", flush=True)
        sources = app["spec"].get("sources", [app["spec"].get("source", {})])
        rendered = []
        for source in sources:
            with tempfile.TemporaryDirectory() as tmp:
                rendered.append(
                    render_source(
                        app,
                        source,
                        sources,
                        RenderContext(ROOT, Path(tmp), config["kubernetesVersion"]),
                    )
                )
        output = args.output / (name + ".yaml")
        output.write_text("\n---\n".join(s for s in rendered if s.strip()))
        os.chmod(output, 0o600)
        inventory.append(name)
    (args.output / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    print(f"Rendered {len(inventory)} applications")


if __name__ == "__main__":
    main()
