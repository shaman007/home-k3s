#!/usr/bin/env python3
"""List tracked YAML files that look like Kubernetes manifests."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


EXCLUDED_PREFIXES = (
    "DEPRECATED/",
    "mastodon/chart/",
)


def tracked_yaml_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--",
            "*.yaml",
            "*.yml",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    files = []
    for entry in result.stdout.decode("utf-8").split("\0"):
        if not entry:
            continue
        if entry.startswith(EXCLUDED_PREFIXES):
            continue
        files.append(repo_root / entry)
    return files


def looks_like_k8s_manifest(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False

    has_api_version = any(
        line.lstrip().startswith("apiVersion:") for line in content.splitlines()
    )
    has_kind = any(line.lstrip().startswith("kind:") for line in content.splitlines())
    return has_api_version and has_kind


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--print0",
        action="store_true",
        help="Terminate file paths with NUL instead of newlines.",
    )
    args = parser.parse_args()

    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )

    separator = "\0" if args.print0 else "\n"
    for manifest in tracked_yaml_files(repo_root):
        if looks_like_k8s_manifest(manifest):
            sys.stdout.write(str(manifest.relative_to(repo_root)))
            sys.stdout.write(separator)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
