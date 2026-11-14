"""Generate inactive GHCR cutover candidates; never contact or mutate the cluster."""

import argparse
import copy
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "ghcr.io/shaman007/godaddy-webhook"
IDENTITY = (
    "https://github.com/shaman007/home-k3s/.github/workflows/"
    "publish-godaddy-webhook.yml@refs/heads/main"
)


def candidates(digest):
    """Require a real immutable digest; retain all unrelated chart configuration."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Expected sha256 followed by 64 lowercase hexadecimal digits")
    policies = []
    for filename in ("policy-verify-own-ghcr.yaml", "policy-verify-ephemeral.yaml"):
        source = next(yaml.safe_load_all((ROOT / "kyverno" / filename).read_text()))
        policy = copy.deepcopy(source)
        suffix = "-ephemeral" if "ephemeral" in filename else ""
        policy["metadata"]["name"] = "verify-godaddy-webhook-ghcr" + suffix
        spec = policy["spec"]
        spec["matchImageReferences"] = [{"glob": IMAGE + ":*"}, {"glob": IMAGE + "@*"}]
        # Retain Audit/Ignore, admission/background and controller coverage as-is.
        spec["attestors"][0]["cosign"]["keyless"]["identities"] = [
            {
                "issuer": "https://token.actions.githubusercontent.com",
                "subject": IDENTITY,
            }
        ]
        policies.append(policy)
    return {
        "values-ghcr.yaml": yaml.safe_dump(
            {"image": {"repository": IMAGE, "digest": digest}}, sort_keys=False
        ),
        "policy-verify-godaddy-ghcr.yaml": yaml.safe_dump_all(
            policies, sort_keys=False
        ),
    }


def main():
    """Write only to a new outside-repository directory, refusing stale output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = candidates(args.digest)
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("Output must be outside the repository (candidates are inactive)")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8")
    print("Inactive candidates:", output)
    print(
        "Digest is syntactically valid; registry identity/signature/pull NOT verified"
    )


if __name__ == "__main__":
    main()
