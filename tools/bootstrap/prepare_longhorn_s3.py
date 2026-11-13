#!/usr/bin/env python3
"""Produce endpoint-only conditional patches; never read credentials or call Kubernetes."""

import argparse
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs/migrations/longhorn-internal-s3/endpoint.json"


def endpoint_patch(resource_version, *, rollback=False):
    """Fail atomically on a changed Secret, then replace only the endpoint."""
    if not resource_version or not resource_version.isdecimal():
        raise ValueError("A numeric Secret resourceVersion is required")
    plan = json.loads(PLAN.read_text())
    old, new = plan["old_endpoint"], plan["new_endpoint"]
    if rollback:
        old, new = new, old

    def encode(value):
        return base64.b64encode(value.encode()).decode()

    return [
        {"op": "test", "path": "/metadata/name", "value": plan["secret"]},
        {"op": "test", "path": "/metadata/namespace", "value": plan["namespace"]},
        {"op": "test", "path": "/metadata/resourceVersion", "value": resource_version},
        {"op": "test", "path": "/data/AWS_ENDPOINTS", "value": encode(old)},
        {"op": "replace", "path": "/data/AWS_ENDPOINTS", "value": encode(new)},
    ]


def main():
    """Print a reviewable patch containing public endpoint metadata only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-version", required=True)
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    try:
        patch = endpoint_patch(args.resource_version, rollback=args.rollback)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(patch, indent=2))


if __name__ == "__main__":
    main()
