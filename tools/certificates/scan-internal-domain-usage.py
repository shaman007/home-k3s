#!/usr/bin/env python3
"""Inventory internal hostnames without copying source lines or secret values."""

import argparse
import collections
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PATTERN = (
    r"(?i)(?<![a-z0-9_-])(?:[a-z0-9_-]+\.)+(?:lan|local|svc)(?:\.cluster\.local)?\.?(?![a-z0-9_.-])"
)
EXCLUSIONS = [
    ".git",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "target",
    "dist",
    "build",
    "__pycache__",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / "git")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(
        (ROOT / "docs/migrations/letsencrypt-internal/inventory.json").read_text()
    )
    replacements = {
        old: new
        for c in inventory["certificates"]
        if not c["canary"]
        for old, new in zip(c["old_names"], c["new_names"])
    }
    command = [
        "rg",
        "--pcre2",
        "--hidden",
        "--no-heading",
        "--color",
        "never",
        "--only-matching",
        "--line-number",
    ]
    for name in EXCLUSIONS:
        command.extend(["--glob", "!**/" + name + "/**"])
    try:
        relative_output = args.output.resolve().relative_to(args.root.resolve())
        command.extend(["--glob", "!" + str(relative_output)])
    except ValueError:
        pass
    command.extend(["--glob", "!**/bench/results/**", PATTERN, str(args.root.resolve())])
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise SystemExit(
            "Hostname inventory requires ripgrep (rg); install it before scanning"
        ) from None
    if result.returncode not in (0, 1):
        raise SystemExit("Scan failed; source/error bodies suppressed")
    entries = []
    annotation_lines = {}
    for line in result.stdout.splitlines():
        filename, number, host = line.rsplit(":", 2)
        path = Path(filename)
        relative = path.relative_to(args.root.resolve())
        host = host.lower().rstrip(".")
        if filename not in annotation_lines:
            annotation_lines[filename] = {
                n
                for n, text in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                )
                if "/token-policies" in text
            }
        if int(number) in annotation_lines[filename]:
            category = "metadata_annotation"
        elif host in replacements:
            category = "ingress_hostname"
        elif host == "api.k8s.my.lan":
            category = "kubernetes_api"
        elif host.endswith((".svc", ".svc.cluster.local")):
            category = "cluster_service"
        elif host == "vault.w386.k8s.my.lan":
            category = "retired_vault_alias_or_annotation"
        elif host.endswith(".local") and not host.endswith(".cluster.local"):
            category = "dot_local_candidate_requires_review"
        else:
            category = "other_internal_name"
        parts = relative.parts
        if (
            "tests" in parts
            or path.name.startswith(("test_", "test-"))
            or path.name.endswith("_test.go")
        ):
            usage = "tests"
        elif path.suffix.lower() in {".md", ".rst"}:
            usage = "documentation"
        elif "docs" in parts:
            usage = "staged_or_historical_artifact"
        else:
            usage = "configuration_or_code"
        entries.append(
            {
                "repository": parts[0],
                "path": str(relative),
                "line": int(number),
                "hostname": host,
                "category": category,
                "usage": usage,
                **({"replacement": replacements[host]} if host in replacements else {}),
            }
        )
    # Source lines and secret contents are deliberately never written to the report.
    report = {
        "scan_root": str(args.root.resolve()),
        "excluded_directories": EXCLUSIONS + ["bench/results"],
        "scope": (
            "candidate hostname inventory, not "
            "automatic replacement instructions; "
            ".local can also match code identifiers; "
            "ignored files and generated directories "
            "are excluded; no source lines or "
            "credentials copied"
        ),
        "counts": {
            "occurrences": len(entries),
            "files": len({e["path"] for e in entries}),
            "repositories": dict(
                sorted(collections.Counter(e["repository"] for e in entries).items())
            ),
            "categories": dict(sorted(collections.Counter(e["category"] for e in entries).items())),
            "usage": dict(sorted(collections.Counter(e["usage"] for e in entries).items())),
        },
        "occurrences": sorted(entries, key=lambda e: (e["path"], e["line"], e["hostname"])),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["counts"], indent=2))


if __name__ == "__main__":
    main()
