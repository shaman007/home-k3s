#!/usr/bin/env python3
"""Sign and verify uploaded GitHub release files; never execute downloaded files."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    tag = os.environ["RELEASE_TAG"]
    identity = "https://github.com/" + os.environ["GITHUB_WORKFLOW_REF"]
    endpoint = f"repos/{repo}/releases/tags/{quote(tag, safe='')}"
    release = json.loads(run("gh", "api", endpoint, capture_output=True, text=True).stdout)
    if release["draft"]:
        raise SystemExit("Publish the release before signing")
    assets = [a for a in release["assets"] if not a["name"].endswith(".sigstore.json")]
    if not assets:
        raise SystemExit("No uploaded release files; generated source archives are not release assets")
    for asset in assets:
        name = asset["name"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", name):
            raise SystemExit("Unsafe release asset filename")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for asset in assets:
            name = asset["name"]
            # Download by immutable asset ID, rather than interpolating names into a URL or shell.
            path = root / name
            with path.open("wb") as target:
                run("gh", "api", "-H", "Accept: application/octet-stream",
                    f"repos/{repo}/releases/assets/{asset['id']}", stdout=target)
            bundle = root / (name + ".sigstore.json")
            run("cosign", "sign-blob", "--yes", "--bundle", str(bundle), str(path))
            run("cosign", "verify-blob", "--bundle", str(bundle),
                "--certificate-identity", identity,
                "--certificate-oidc-issuer", "https://token.actions.githubusercontent.com", str(path))
        # Do not publish partial results or certify a release changed during signing.
        current = json.loads(run("gh", "api", endpoint, capture_output=True, text=True).stdout)
        fields = lambda items: sorted((a["id"], a["name"], a["updated_at"]) for a in items
                                      if not a["name"].endswith(".sigstore.json"))
        if fields(assets) != fields(current["assets"]):
            raise SystemExit("Release assets changed while signing; retry after uploads finish")
        for asset in assets:
            run("gh", "release", "upload", tag, "--repo", repo, "--clobber",
                str(root / (asset["name"] + ".sigstore.json")))


if __name__ == "__main__":
    main()
