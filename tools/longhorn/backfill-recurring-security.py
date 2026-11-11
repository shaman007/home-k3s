#!/usr/bin/env python3
"""PostSync backfill: trigger the reviewed native mutation, then verify its result.

Only metadata is patched by this client. The admission policy supplies the
security fields. Preflight every existing allowlisted CronJob before any write.
"""

import copy
import json
import os
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request

NAMESPACE = "longhorn-system"
IMAGE = "docker.io/longhornio/longhorn-manager:v1.13.0"
MARKER = "hardening.home-k3s/recurring-security"
SECURITY = {
    "runAsNonRoot": True,
    "runAsUser": 1000,
    "runAsGroup": 1000,
    "allowPrivilegeEscalation": False,
    "privileged": False,
    "capabilities": {"drop": ["ALL"]},
    "seccompProfile": {"type": "RuntimeDefault"},
}


def reviewed(document, name):
    """Reject workloads that differ from the explicitly reviewed deployment contract."""
    meta = document["metadata"]
    spec = document["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    if not (meta["namespace"] == NAMESPACE and meta["name"] == name):
        raise AssertionError
    if not meta["labels"]["longhorn.io/managed-by"] == "longhorn-manager":
        raise AssertionError
    if not meta["labels"]["recurring-job.longhorn.io"] == name:
        raise AssertionError
    if not any(
        (
            o["kind"] == "RecurringJob"
            and o["name"] == name
            and (o["apiVersion"] == "longhorn.io/v1beta2")
            for o in meta["ownerReferences"]
        )
    ):
        raise AssertionError
    if not spec["serviceAccountName"] == "longhorn-service-account":
        raise AssertionError
    if not (len(spec["containers"]) == 1 and (not spec.get("initContainers"))):
        raise AssertionError
    container = spec["containers"][0]
    if not (container["name"] == name and container["image"] == IMAGE):
        raise AssertionError
    if not container["command"] == [
        "longhorn-manager",
        "-d",
        "recurring-job",
        name,
        "--manager-url",
        "http://longhorn-backend:9500/v1",
    ]:
        raise AssertionError
    return spec


def expected_spec(document):
    """Copy the workload specification and apply only its reviewed security context."""
    spec = copy.deepcopy(document["spec"])
    container = spec["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    container["securityContext"] = {**(container.get("securityContext") or {}), **SECURITY}
    return spec


def annotation_patch(document):
    """Build a resource-version-guarded annotation patch to trigger reviewed admission."""
    operations = [
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": document["metadata"]["resourceVersion"],
        }
    ]
    if document["metadata"].get("annotations") is None:
        operations.append({"op": "add", "path": "/metadata/annotations", "value": {}})
    operations.append(
        {"op": "add", "path": "/metadata/annotations/" + MARKER.replace("/", "~1"), "value": "v1"}
    )
    return operations


def main(config_dir=Path("/config"), account=Path("/var/run/secrets/kubernetes.io/serviceaccount")):
    """PostSync backfill: trigger the reviewed native mutation, then verify its result."""
    names = json.loads((config_dir / "names.json").read_text())
    context = ssl.create_default_context(cafile=str(account / "ca.crt"))
    token = (account / "token").read_text().strip()
    base = (
        "https://"
        + os.environ["KUBERNETES_SERVICE_HOST"]
        + ":"
        + os.environ["KUBERNETES_SERVICE_PORT"]
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context)
    )

    def request(name, patch=None, dry=False):
        url = base + "/apis/batch/v1/namespaces/" + NAMESPACE + "/cronjobs/" + name
        if dry:
            url += "?dryRun=All"
        headers = {"Authorization": "Bearer " + token}
        if patch is not None:
            headers["Content-Type"] = "application/json-patch+json"
        req = urllib.request.Request(
            url,
            headers=headers,
            method="PATCH" if patch is not None else "GET",
            data=json.dumps(patch).encode() if patch is not None else None,
        )
        try:
            with opener.open(req, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404 and patch is None:
                return None
            raise RuntimeError(f"{name}: Kubernetes HTTP {error.code}") from None

    pending = []
    for attempt in range(30):
        pending = []
        try:
            for name in names:
                original = request(name)
                if original is None:
                    print(f"{name}: absent; future creation is covered by admission", flush=True)
                    continue
                reviewed(original, name)
                expected = expected_spec(original)
                if original["spec"] == expected:
                    print(f"{name}: already hardened", flush=True)
                    continue
                patch = annotation_patch(original)
                preview = request(name, patch, dry=True)
                if not preview["spec"] == expected:
                    raise AssertionError(
                        f"{name}: admission mutation absent or unexpected spec change"
                    )
                pending.append((name, original, patch, expected))
            break
        except AssertionError:
            if attempt == 29:
                raise
            time.sleep(3)  # Allow the API server's admission-policy cache to converge.
    for name, original, patch, expected in pending:
        result = request(name, patch)
        if not result["spec"] == expected:
            raise AssertionError(f"{name}: persisted spec differs from preflight")
        if not request(name)["spec"] == expected:
            raise AssertionError(f"{name}: read-back differs from preflight")
        print(f"{name}: hardened and read-back verified", flush=True)
    print("Recurring-job security backfill complete", flush=True)


if __name__ == "__main__":
    main()
