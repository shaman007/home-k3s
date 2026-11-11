#!/usr/bin/env python3
"""Preflight native mutations, then roll reviewed workloads one at a time."""

import copy
import json
import os
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request

NAMESPACE = "longhorn-system"
MARKER = "hardening.home-k3s/component-security"


def security(entry):
    """Build the reviewed user, group, capability, and seccomp security context."""
    return {
        "runAsNonRoot": entry["uid"] != 0,
        "runAsUser": entry["uid"],
        "runAsGroup": entry["gid"],
        "allowPrivilegeEscalation": False,
        "privileged": False,
        "capabilities": {"drop": ["ALL"]},
        "seccompProfile": {"type": "RuntimeDefault"},
    }


def reviewed(doc, entry):
    """Reject workloads that differ from the explicitly reviewed deployment contract."""
    meta, pod = doc["metadata"], doc["spec"]["template"]["spec"]
    if not (
        doc["kind"] == entry["kind"]
        and meta["namespace"] == NAMESPACE
        and (meta["name"] == entry["name"])
    ):
        raise AssertionError
    if not doc["spec"]["template"]["metadata"]["labels"]["app"] == entry["name"]:
        raise AssertionError
    if not pod["serviceAccountName"] == entry["serviceAccount"]:
        raise AssertionError
    if not (len(pod["containers"]) == entry["count"] and (not pod.get("initContainers"))):
        raise AssertionError
    c = pod["containers"][entry["index"]]
    if not (c["name"] == entry["container"] and c["image"] == entry["image"]):
        raise AssertionError
    if not (c.get("command", []) == entry["command"] and c.get("args", []) == entry["args"]):
        raise AssertionError
    if entry["kind"] == "DaemonSet":
        for index in range(entry["count"]):
            if index == entry["index"]:
                continue
            actual = pod["containers"][index]
            expected = entry["fixture"]["spec"]["template"]["spec"]["containers"][index]
            if not (actual["name"] == expected["name"] and actual["image"] == expected["image"]):
                raise AssertionError
            if actual["securityContext"]["privileged"] is not True:
                raise AssertionError
        if not doc["spec"]["updateStrategy"] == entry["fixture"]["spec"]["updateStrategy"]:
            raise AssertionError


def expected_spec(doc, entry):
    """Copy the workload specification and apply only its reviewed security context."""
    spec = copy.deepcopy(doc["spec"])
    c = spec["template"]["spec"]["containers"][entry["index"]]
    c["securityContext"] = {**(c.get("securityContext") or {}), **security(entry)}
    return spec


def ready(doc):
    """Require the current generation and every desired replica to be updated and ready."""
    status = doc.get("status", {})
    if status.get("observedGeneration", 0) < doc["metadata"].get("generation", 1):
        return False
    if doc["kind"] == "Deployment":
        count = doc["spec"].get("replicas", 1)
        return (
            count > 0
            and status.get("updatedReplicas", 0) == count
            and status.get("replicas", 0) == count
            and status.get("readyReplicas", 0) == count
            and status.get("availableReplicas", 0) == count
        )
    count = status.get("desiredNumberScheduled", 0)
    return (
        count > 0
        and status.get("updatedNumberScheduled", 0) == count
        and status.get("numberReady", 0) == count
        and status.get("numberAvailable", 0) == count
    )


def annotation_patch(doc):
    """Build a resource-version-guarded annotation patch to trigger reviewed admission."""
    patch = [
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": doc["metadata"]["resourceVersion"],
        }
    ]
    if doc["metadata"].get("annotations") is None:
        patch.append({"op": "add", "path": "/metadata/annotations", "value": {}})
    patch.append(
        {"op": "add", "path": "/metadata/annotations/" + MARKER.replace("/", "~1"), "value": "v1"}
    )
    return patch


def storage_healthy(volumes, nodes):
    """Reject active degradation; detached idle volumes may have unknown health."""
    if not volumes.get("items"):
        raise AssertionError("No Longhorn volume status available")
    if not nodes.get("items"):
        raise AssertionError("No Longhorn node status available")
    for volume in volumes["items"]:
        status = volume.get("status", {})
        detached = status.get("state") == "detached"
        acceptable = (
            status.get("robustness") in ("healthy", "unknown")
            if detached
            else status.get("state") == "attached" and status.get("robustness") == "healthy"
        )
        if not (acceptable and status.get("restoreRequired") is False):
            raise AssertionError("Longhorn storage is not stable and healthy")
    for node in nodes["items"]:
        status = node.get("status", {})
        conditions = {c["type"]: c["status"] for c in status.get("conditions", [])}
        if not (conditions.get("Ready") == "True" and conditions.get("Schedulable") == "True"):
            raise AssertionError("Longhorn node is not ready/schedulable")
        disks = status.get("diskStatus", {})
        if not disks:
            raise AssertionError("No Longhorn disk status available")
        for disk in disks.values():
            conditions = {c["type"]: c["status"] for c in disk.get("conditions", [])}
            if not (conditions.get("Ready") == "True" and conditions.get("Schedulable") == "True"):
                raise AssertionError("Longhorn disk is not ready/schedulable")


def main(config_dir=Path("/config"), account=Path("/var/run/secrets/kubernetes.io/serviceaccount")):
    """Preflight native mutations, then roll reviewed workloads one at a time."""
    entries = json.loads((config_dir / "catalog.json").read_text())["entries"]
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

    def request(entry, patch=None, dry=False):
        resource = "deployments" if entry["kind"] == "Deployment" else "daemonsets"
        url = base + "/apis/apps/v1/namespaces/" + NAMESPACE + "/" + resource + "/" + entry["name"]
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
            raise RuntimeError(f"{entry['name']}: Kubernetes HTTP {error.code}") from None

    check_storage = any(e["name"] == "longhorn-manager" for e in entries)

    def storage_check():
        if not check_storage:
            return
        documents = {}
        for resource in ["volumes", "nodes"]:
            url = base + "/apis/longhorn.io/v1beta2/namespaces/" + NAMESPACE + "/" + resource
            req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
            with opener.open(req, timeout=15) as response:
                documents[resource] = json.load(response)
        storage_healthy(documents["volumes"], documents["nodes"])

    # Complete all safety checks before the first persistent write.
    for attempt in range(30):
        try:
            storage_check()
            for entry in entries:
                original = request(entry)
                reviewed(original, entry)
                if not ready(original):
                    raise AssertionError(f"{entry['name']}: workload is not fully healthy")
                preview = request(entry, annotation_patch(original), dry=True)
                if not preview["spec"] == expected_spec(original, entry):
                    raise AssertionError(
                        f"{entry['name']}: unexpected or absent admission mutation"
                    )
            break
        except AssertionError:
            if attempt == 29:
                raise
            time.sleep(3)
    for entry in entries:
        storage_check()
        # Refetch to tolerate harmless controller resourceVersion updates during earlier rollouts.
        original = request(entry)
        reviewed(original, entry)
        if not ready(original):
            raise AssertionError(f"{entry['name']}: became unhealthy before mutation")
        expected = expected_spec(original, entry)
        if original["spec"] != expected:
            patch = annotation_patch(original)
            if not request(entry, patch, dry=True)["spec"] == expected:
                raise AssertionError
            if not request(entry, patch)["spec"] == expected:
                raise AssertionError
        deadline = time.monotonic() + 300
        while True:
            current = request(entry)
            if not current["spec"] == expected:
                raise AssertionError(f"{entry['name']}: spec changed during rollout")
            if ready(current):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"{entry['name']}: rollout timed out; later targets were not changed"
                )
            time.sleep(3)
        storage_check()
        print(f"{entry['name']}: security context and completed rollout verified", flush=True)
    for path in ["/", "/v1"]:
        req = urllib.request.Request("http://longhorn-frontend" + path)
        with opener.open(req, timeout=15) as response:
            if not response.status == 200:
                raise AssertionError("UI HTTP check failed")
    print("Component backfill complete; UI static and API proxy HTTP checks passed", flush=True)


if __name__ == "__main__":
    main()
