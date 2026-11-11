"""Guarded GitOps backfill: exact contracts, admission previews, sequential rollouts."""

import copy
import json
import os
from pathlib import Path
import ssl
import time
import urllib.request


def review_container_specs(pod, entry):
    """Require the exact reviewed container count, images, commands and mounts."""
    for section in ["containers", "initContainers"]:
        actual, expected = (
            pod.get(section, []),
            entry["fixture"]["spec"]["template"]["spec"].get(section, []),
        )
        if not len(actual) == len(expected):
            raise AssertionError
        for a, e in zip(actual, expected):
            if not all(
                (
                    a.get(k, []) == e.get(k, [])
                    for k in ["name", "image", "command", "args", "volumeMounts"]
                )
            ):
                raise AssertionError


def review_target_environment(pod, targets):
    """Require each reviewed target identity and its literal/field-reference environment."""
    for target in targets:
        actual = pod[target["section"]][target["index"]]
        if not actual["name"] == target["name"]:
            raise AssertionError
        env = {v["name"]: v for v in actual.get("env", [])}
        for name, value in target.get("requiredEnv", {}).items():
            if not env.get(name, {}).get("value") == value:
                raise AssertionError
        for name, path in target.get("requiredFieldRefs", {}).items():
            if (
                not env.get(name, {}).get("valueFrom", {}).get("fieldRef", {}).get("fieldPath")
                == path
            ):
                raise AssertionError


def reviewed(doc, entry):
    """Reject workloads that differ from the explicitly reviewed deployment contract."""
    if not (doc["kind"] == entry["kind"] and doc["metadata"]["name"] == entry["name"]):
        raise AssertionError
    if not doc["metadata"]["namespace"] == entry["namespace"]:
        raise AssertionError
    pod = doc["spec"]["template"]["spec"]
    if not pod.get("serviceAccountName", "default") == entry["serviceAccount"]:
        raise AssertionError
    for key, value in entry["labels"].items():
        if not doc["spec"]["template"]["metadata"]["labels"].get(key) == value:
            raise AssertionError
    review_container_specs(pod, entry)
    if not pod.get("volumes", []) == entry["fixture"]["spec"]["template"]["spec"].get(
        "volumes", []
    ):
        raise AssertionError
    review_target_environment(pod, entry["targets"])
    if entry["kind"] == "DaemonSet":
        if not doc["spec"]["updateStrategy"] == entry["fixture"]["spec"]["updateStrategy"]:
            raise AssertionError
        if not doc["spec"]["updateStrategy"]["rollingUpdate"]["maxUnavailable"] == 1:
            raise AssertionError


def expected_spec(doc, entry):
    """Copy the workload specification and apply only its reviewed security context."""
    spec = copy.deepcopy(doc["spec"])
    if entry.get("podGuards"):
        pod = spec["template"]["spec"]
        pod["securityContext"] = {**(pod.get("securityContext") or {}), **entry["podGuards"]}
    for target in entry["targets"]:
        container = spec["template"]["spec"][target["section"]][target["index"]]
        container["securityContext"] = {
            **(container.get("securityContext") or {}),
            **target["guards"],
        }
    return spec


def ready(doc):
    """Require the current generation and every desired replica to be updated and ready."""
    s = doc.get("status", {})
    if s.get("observedGeneration", 0) < doc["metadata"].get("generation", 1):
        return False
    if doc["kind"] == "Deployment":
        n = doc["spec"].get("replicas", 1)
        return n > 0 and all(
            s.get(k) == n
            for k in ["replicas", "updatedReplicas", "readyReplicas", "availableReplicas"]
        )
    n = s.get("desiredNumberScheduled", 0)
    return n > 0 and all(
        s.get(k) == n for k in ["updatedNumberScheduled", "numberReady", "numberAvailable"]
    )


def patch(doc):
    """Build a resource-version-guarded annotation patch to trigger reviewed admission."""
    result = [
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": doc["metadata"]["resourceVersion"],
        }
    ]
    if doc["metadata"].get("annotations") is None:
        result.append({"op": "add", "path": "/metadata/annotations", "value": {}})
    result.append(
        {
            "op": "add",
            "path": "/metadata/annotations/hardening.home-k3s~1infra-guards",
            "value": "v1",
        }
    )
    return result


def gpu_healthy(node, review):
    """Require reviewed node identity, GPU health, permissions, and allocatable capacity."""
    if not node["metadata"]["name"] == review["node"]:
        raise AssertionError
    if not any(
        (
            c["type"] == "Ready" and c["status"] == "True"
            for c in node.get("status", {}).get("conditions", [])
        )
    ):
        raise AssertionError("GPU node is not Ready")
    for field in ["capacity", "allocatable"]:
        if (
            not int(node.get("status", {}).get(field, {}).get(review["resource"], 0))
            == review["capacity"]
        ):
            raise AssertionError("GPU resource count changed")


def preflight(entries, request, environment_check):
    """Require every contract and dry-run mutation to pass before any rollout write."""
    # Every contract and dry-run mutation must pass before the hook writes anything.
    for attempt in range(30):
        try:
            environment_check()
            for e in entries:
                original = request(e)
                reviewed(original, e)
                if not ready(original):
                    raise AssertionError(e["name"] + ": not fully ready")
                if not request(e, patch(original), True)["spec"] == expected_spec(original, e):
                    raise AssertionError(e["name"] + ": unexpected admission result")
            break
        except AssertionError:
            if attempt == 29:
                raise
            time.sleep(3)


def wait_for_rollout(e, request, expected):
    """Require the exact expected spec and fifteen seconds of stable current readiness."""
    deadline = time.monotonic() + 300
    stable_since = None
    while True:
        current = request(e)
        if not current["spec"] == expected:
            raise AssertionError(e["name"] + ": unexpected spec change")
        if ready(current):
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= 15:
                break
        else:
            stable_since = None
        if time.monotonic() >= deadline:
            raise RuntimeError(e["name"] + ": rollout failed; later targets untouched")
        time.sleep(3)


def rollout(entries, request, environment_check):
    """Recheck each target and environment before sequential guarded writes and readback."""
    for e in entries:
        environment_check()
        original = request(e)
        reviewed(original, e)
        if not ready(original):
            raise AssertionError(e["name"] + ": readiness changed")
        expected = expected_spec(original, e)
        if expected != original["spec"]:
            if not request(e, patch(original), True)["spec"] == expected:
                raise AssertionError
            if not request(e, patch(original))["spec"] == expected:
                raise AssertionError
        wait_for_rollout(e, request, expected)
        environment_check()
        print(e["namespace"] + "/" + e["name"] + ": guards and rollout verified", flush=True)


def main(config_dir=Path("/config"), account=Path("/var/run/secrets/kubernetes.io/serviceaccount")):
    """Guarded GitOps backfill: exact contracts, admission previews, sequential rollouts."""
    catalog = json.loads((config_dir / "catalog.json").read_text())
    entries = catalog["entries"]
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

    def request(e, changes=None, dry=False):
        resource = "deployments" if e["kind"] == "Deployment" else "daemonsets"
        url = base + "/apis/apps/v1/namespaces/" + e["namespace"] + "/" + resource + "/" + e["name"]
        if dry:
            url += "?dryRun=All"
        headers = {"Authorization": "Bearer " + token}
        if changes is not None:
            headers["Content-Type"] = "application/json-patch+json"
        req = urllib.request.Request(
            url,
            method="GET" if changes is None else "PATCH",
            headers=headers,
            data=None if changes is None else json.dumps(changes).encode(),
        )
        with opener.open(req, timeout=15) as response:
            return json.load(response)

    def storage_check():
        if not any((e["namespace"] == "longhorn-system" for e in entries)):
            return
        from storage_guard import storage_healthy

        documents = []
        for resource in ["volumes", "nodes"]:
            req = urllib.request.Request(
                base + "/apis/longhorn.io/v1beta2/namespaces/longhorn-system/" + resource,
                headers={"Authorization": "Bearer " + token},
            )
            with opener.open(req, timeout=15) as response:
                documents.append(json.load(response))
        storage_healthy(*documents)

    def gpu_check():
        review = catalog.get("gpuResourceReview")
        if not review:
            return
        req = urllib.request.Request(
            base + "/api/v1/nodes/" + review["node"], headers={"Authorization": "Bearer " + token}
        )
        with opener.open(req, timeout=15) as response:
            gpu_healthy(json.load(response), review)

    def environment_check():
        storage_check()
        gpu_check()

    preflight(entries, request, environment_check)
    rollout(entries, request, environment_check)


if __name__ == "__main__":
    main()
