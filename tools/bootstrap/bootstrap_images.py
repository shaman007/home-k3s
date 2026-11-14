#!/usr/bin/env python3
"""Check/preload exact bootstrap references; export an independent recovery bundle."""

import argparse
import hashlib
import ipaddress
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.security.probe_commands import run_command, user_executable  # pylint: disable=wrong-import-position

LOCK = Path(__file__).resolve().parents[2] / "docs/bootstrap-images/images.lock.json"
DIGEST = re.compile(r"sha256:[a-f0-9]{64}")


def validate(lock):
    """Reject malformed/duplicate rows before invoking a CLI."""
    if (
        lock.get("format_version") != 1
        or not lock.get("nodes")
        or not lock.get("images")
    ):
        raise ValueError("Invalid image lock")
    for node in lock["nodes"]:
        ipaddress.IPv4Address(node)
    seen = set()
    for image in lock["images"]:
        ref = image["reference"]
        if (
            not re.fullmatch(r"[a-zA-Z0-9./_:@-]+", ref)
            or ref.startswith("-")
            or not DIGEST.fullmatch(image["digest"])
            or image["namespace"] not in ("cri", "system")
        ):
            raise ValueError("Invalid image row")
        key = (image["namespace"], ref)
        if key in seen:
            raise ValueError("Duplicate image row")
        seen.add(key)
    return lock


def canonical(ref):
    """Match CRI-normalized names, including tag@digest becoming digest-only."""
    if "@" in ref:
        name, digest = ref.rsplit("@", 1)
        if ":" in name.rsplit("/", 1)[-1]:
            name = name.rsplit(":", 1)[0]
        ref = name + "@" + digest
    first = ref.split("/", 1)[0]
    if "/" not in ref or (
        "." not in first and ":" not in first and first != "localhost"
    ):
        ref = "docker.io/" + ref
    if ref.startswith("docker.io/") and "/" not in ref[len("docker.io/") :]:
        ref = "docker.io/library/" + ref[len("docker.io/") :]
    return ref


def inventory(text):
    """Parse native Talos tabular image references and manifest digests."""
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 3 and DIGEST.fullmatch(fields[2]):
            result[canonical(fields[1])] = fields[2]
    return result


def execute(args):
    """Bound native operations and avoid forwarding raw stderr or credentials."""
    r = run_command(args, capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise RuntimeError("CLI operation failed: " + Path(args[0]).name)
    return r.stdout


def check_node(lock, node, preload=False):
    """Pull only missing references; fail rather than replace unexpected digest drift."""
    cli = user_executable("talosctl")
    issues = []
    for ns in ("cri", "system"):
        prefix = [cli, "image"]
        flags = ["--namespace", ns, "--nodes", node]
        available = inventory(execute(prefix + ["list"] + flags))
        for image in (i for i in lock["images"] if i["namespace"] == ns):
            ref = image["reference"]
            actual = available.get(canonical(ref))
            if actual is not None and actual != image["digest"]:
                issues.append(
                    {"node": node, "reference": ref, "result": "digest-drift"}
                )
                continue
            if actual is None and preload:
                execute(prefix + ["pull", ref] + flags)
                available = inventory(execute(prefix + ["list"] + flags))
                actual = available.get(canonical(ref))
            if actual != image["digest"]:
                issues.append(
                    {"node": node, "reference": ref, "result": "missing-or-mismatch"}
                )
    return issues


def bundle(lock, output):
    """Create new flat cache preserving original tags, guarded by manifest digest checks."""
    if output.exists():
        raise ValueError("Bundle destination must be new")
    skopeo = user_executable("skopeo")
    for image in lock["images"]:
        # Runtime imageIDs can refer to a platform manifest inside an index.
        ref = image["reference"]
        serialized = execute([skopeo, "inspect", "--raw", "docker://" + canonical(ref)])
        raw = json.loads(serialized)
        digest = "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()
        candidates = {digest} | {
            m["digest"]
            for m in raw.get("manifests", [])
            if m.get("platform", {}).get("os") == "linux"
            and m.get("platform", {}).get("architecture") == "amd64"
        }
        if image["digest"] not in candidates:
            raise ValueError("Registry digest drift: " + ref)
    refs = sorted({canonical(i["reference"]) for i in lock["images"]})
    output.mkdir(parents=True)
    for number, ref in enumerate(refs, 1):
        print(f"Caching {number}/{len(refs)}: {ref}", file=sys.stderr, flush=True)
        export_image(ref, output)
    (output / "bootstrap-images.lock.json").write_text(
        json.dumps(lock, indent=2) + "\n"
    )
    verify_image_manifests(lock, output)
    seal_bundle(output)


def export_image(ref, output):
    """Export one native flat-cache image and merge only identical shared blobs."""
    with tempfile.TemporaryDirectory(prefix="talos-bootstrap-") as directory:
        single = Path(directory) / "image"
        result = run_command(
            [
                user_executable("talosctl"),
                "image",
                "cache-create",
                "--layout=flat",
                "--platform=linux/amd64",
                "--images=" + ref,
                "--image-layer-cache-path=" + str(output.parent / "layers"),
                "--image-cache-path=" + str(single),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode:
            # Fixed public diagnostic category; no provider bodies/URLs or auth.
            errors = (result.stdout + result.stderr).lower()
            kind = next(
                (
                    k
                    for k in [
                        "too many requests",
                        "unauthorized",
                        "manifest unknown",
                        "timeout",
                        "no space",
                        "not found",
                    ]
                    if k in errors
                ),
                "native-cache-export",
            )
            raise RuntimeError(f"Cache export failed for {ref}: {kind}")
        for source in single.rglob("*"):
            target = output / source.relative_to(single)
            if source.is_symlink():
                raise ValueError("Unexpected cache symlink")
            if source.is_dir():
                target.mkdir(exist_ok=True)
            elif target.exists():
                with source.open("rb") as first, target.open("rb") as second:
                    if (
                        hashlib.file_digest(first, "sha256").digest()
                        != hashlib.file_digest(second, "sha256").digest()
                    ):
                        raise ValueError("Conflicting native cache entries")
            else:
                shutil.copyfile(source, target)


def verify_image_manifests(lock, output):
    """Require the locked manifest and its amd64 layer closure in the flat cache."""
    checked = set()

    def blob(path, digest):
        if path not in checked:
            with path.open("rb") as stream:
                if (
                    hashlib.file_digest(stream, "sha256").hexdigest()
                    != digest.split(":", 1)[1]
                ):
                    raise ValueError("Content-addressed cache digest mismatch")
            checked.add(path)

    def manifest(repo, digest):
        path = output / "manifests" / repo / "digest" / digest.replace(":", "-")
        blob(path, digest)
        data = json.loads(path.read_text())
        if "manifests" in data:
            selected = [
                m
                for m in data["manifests"]
                if m.get("platform", {}).get("os") == "linux"
                and m.get("platform", {}).get("architecture") == "amd64"
            ]
            if not selected:
                raise ValueError("Cache index has no linux/amd64 manifest")
            for child in selected:
                manifest(repo, child["digest"])
        else:
            for descriptor in [data["config"], *data["layers"]]:
                file = output / "blob" / descriptor["digest"].replace(":", "-")
                if file.stat().st_size != descriptor["size"]:
                    raise ValueError("Cache blob size mismatch")
                blob(file, descriptor["digest"])

    for image in lock["images"]:
        ref = canonical(image["reference"])
        repo = ref.split("@")[0]
        if "@" not in ref and ":" in repo.rsplit("/", 1)[-1]:
            repo, tag = repo.rsplit(":", 1)
            alias = output / "manifests" / repo / "reference" / tag
            data = json.loads(alias.read_text())
            candidates = {"sha256:" + hashlib.sha256(alias.read_bytes()).hexdigest()}
            candidates.update(m["digest"] for m in data.get("manifests", []))
            if image["digest"] not in candidates:
                raise ValueError("Cache tag does not resolve to locked digest")
        manifest(repo, image["digest"])
    return len(checked)


def seal_bundle(output):
    """Hash all bundle files after creation, without modifying image contents."""
    checksums = {}
    for file in sorted(output.rglob("*")):
        if file.is_file() and file.name != "SHA256SUMS.json":
            with file.open("rb") as stream:
                checksums[str(file.relative_to(output))] = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
    (output / "SHA256SUMS.json").write_text(json.dumps(checksums, indent=2) + "\n")


def verify_bundle(output):
    """Fail on damaged, missing or unexpected files before recovery use."""
    expected = json.loads((output / "SHA256SUMS.json").read_text())
    actual = {
        str(p.relative_to(output))
        for p in output.rglob("*")
        if p.is_file() and p.name != "SHA256SUMS.json"
    }
    if not expected or set(expected) != actual:
        raise ValueError("Bundle file inventory mismatch")
    for relative, digest in expected.items():
        file = output / relative
        if file.is_symlink() or not file.resolve().is_relative_to(output.resolve()):
            raise ValueError("Unsafe bundle path")
        with file.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise ValueError("Bundle content checksum mismatch")
    return len(expected)


def main():
    """Check is read-only; preload and bundle require explicit mode selection."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["check", "preload", "bundle", "verify-bundle"])
    p.add_argument("--lock", type=Path, default=LOCK)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    lock = validate(json.loads(args.lock.read_text()))
    if args.mode == "verify-bundle":
        if not args.output:
            p.error("verify-bundle requires --output")
        print(
            json.dumps(
                {
                    "verified_files": verify_bundle(args.output),
                    "verified_image_files": verify_image_manifests(lock, args.output),
                }
            )
        )
        return 0
    if args.mode == "bundle":
        if not args.output:
            p.error("bundle requires --output outside the repository")
        out = args.output.resolve()
        if out.is_relative_to(Path(__file__).resolve().parents[2]):
            p.error("bundle must stay outside the repository")
        bundle(lock, out)
        return 0
    issues = [
        i for n in lock["nodes"] for i in check_node(lock, n, args.mode == "preload")
    ]
    print(
        json.dumps(
            {"mode": args.mode, "nodes": lock["nodes"], "issues": issues}, indent=2
        )
    )
    return bool(issues)


if __name__ == "__main__":
    raise SystemExit(main())
