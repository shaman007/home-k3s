"""Project Kubernetes List input into non-secret startup references; no API calls."""

import ipaddress
import json
import sys
from urllib.parse import urlsplit

WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "CronJob"}


def host_hint(entry):
    """Return only a hostname, never URL credentials, paths, queries or raw values."""
    name = entry["name"]
    sensitive_name = bool(
        set(name.split("_")) & {"PASSWORD", "SECRET", "TOKEN", "KEY", "CREDENTIAL"}
    )
    if sensitive_name or not name.endswith(
        ("HOST", "HOSTNAME", "SERVER", "URL", "ADDR", "ADDRESS", "ENDPOINT")
    ):
        return None
    value = entry.get("value", "")
    if not value or any(character.isspace() for character in value):
        return None
    try:
        host = urlsplit(value if "://" in value else "//" + value).hostname
        if not host or host == "localhost":
            return None
        try:
            address = ipaddress.ip_address(host)
            if address.is_loopback or address.is_unspecified:
                return None
        except ValueError:
            pass
        return host
    except ValueError:
        return None


def volume_references(pod, secrets, configs, pvcs):
    """Collect required mounted-object names without reading object contents."""
    for volume in pod.get("volumes", []):
        if "secret" in volume and not volume["secret"].get("optional", False):
            secrets.add(volume["secret"]["secretName"])
        if "configMap" in volume and not volume["configMap"].get("optional", False):
            configs.add(volume["configMap"]["name"])
        if "persistentVolumeClaim" in volume:
            pvcs.add(volume["persistentVolumeClaim"]["claimName"])
        for source in volume.get("projected", {}).get("sources", []):
            for kind, target in (("secret", secrets), ("configMap", configs)):
                if kind in source and not source[kind].get("optional", False):
                    target.add(source[kind]["name"])


def pod_references(pod):
    """Collect image and required object references plus sanitized literal hosts."""
    secrets, configs, pvcs, hints, images = set(), set(), set(), set(), set()
    volume_references(pod, secrets, configs, pvcs)
    for container in pod.get("initContainers", []) + pod.get("containers", []):
        images.add(container["image"])
        for entry in container.get("env", []):
            hint = host_hint(entry)
            if hint:
                hints.add(hint)
            for kind, target in (
                ("secretKeyRef", secrets),
                ("configMapKeyRef", configs),
            ):
                reference = entry.get("valueFrom", {}).get(kind)
                if reference and not reference.get("optional", False):
                    target.add(reference["name"])
        for entry in container.get("envFrom", []):
            for kind, target in (("secretRef", secrets), ("configMapRef", configs)):
                if kind in entry and not entry[kind].get("optional", False):
                    target.add(entry[kind]["name"])
    for entry in pod.get("imagePullSecrets", []):
        secrets.add(entry["name"])
    return secrets, configs, pvcs, hints, images


def workload_template(workload):
    """Keep scheduled prerequisites visible without treating a CronJob as a Service backend."""
    if workload["kind"] == "CronJob":
        return workload["spec"]["jobTemplate"]["spec"]["template"]
    return workload["spec"]["template"]


def service_hints(hints, namespace, services, workloads):
    """Resolve declared service host hints through namespace-scoped selectors."""
    resolved = []
    for host in sorted(hints):
        parts = host.split(".")
        if len(parts) > 2 and parts[2:] not in (["svc"], ["svc", "cluster", "local"]):
            continue  # External FQDNs must not impersonate a Kubernetes Service.
        service_namespace = parts[1] if len(parts) > 1 else namespace
        service = services.get((service_namespace, parts[0]))
        if service is None or not service["spec"].get("selector"):
            continue
        providers = [
            f"{item['kind']}/{item['metadata']['name']}"
            for item in workloads
            if item["kind"] != "CronJob"
            and item["metadata"]["namespace"] == service_namespace
            and all(
                workload_template(item)["metadata"].get("labels", {}).get(key) == value
                for key, value in service["spec"]["selector"].items()
            )
        ]
        resolved.append(
            {"service": f"{service_namespace}/{parts[0]}", "providers": providers}
        )
    return resolved


def project(document):
    """Inventory all supplied workloads, declared prerequisites and service hints."""
    items = document["items"]
    workloads = [item for item in items if item["kind"] in WORKLOADS]
    services = {
        (item["metadata"]["namespace"], item["metadata"]["name"]): item
        for item in items
        if item["kind"] == "Service"
    }
    report = []
    for workload in workloads:
        namespace = workload["metadata"]["namespace"]
        pod = workload_template(workload)["spec"]
        secrets, configs, pvcs, hints, images = pod_references(pod)
        resolved = service_hints(hints, namespace, services, workloads)
        report.append(
            {
                "namespace": namespace,
                "kind": workload["kind"],
                "name": workload["metadata"]["name"],
                "images": sorted(images),
                "required_secrets": sorted(secrets),
                "required_configmaps": sorted(configs),
                "required_pvcs": sorted(pvcs),
                "volume_claim_templates": [
                    item["metadata"]["name"]
                    for item in workload["spec"].get("volumeClaimTemplates", [])
                ],
                "literal_host_hints": sorted(hints),
                "service_hints": resolved,
            }
        )
    materialization = [
        {
            "namespace": item["metadata"]["namespace"],
            "external_secret": item["metadata"]["name"],
            "target": item["spec"]
            .get("target", {})
            .get("name", item["metadata"]["name"]),
            "store": item["spec"]["secretStoreRef"]["name"],
        }
        for item in items
        if item["kind"] == "ExternalSecret"
    ]
    return {
        "format_version": 1,
        "workload_count": len(report),
        "limitations": [
            "Reference inventory, not dependency readiness proof or an installed gate.",
            "Host hints are not mandatory-startup claims; Secret/ConfigMap contents are opaque.",
            "No raw environment values, Secret contents, URLs, commands or annotations exported.",
        ],
        "workloads": sorted(
            report, key=lambda row: (row["namespace"], row["kind"], row["name"])
        ),
        "secret_materialization": sorted(
            materialization, key=lambda row: (row["namespace"], row["target"])
        ),
    }


if __name__ == "__main__":
    json.dump(project(json.load(sys.stdin)), sys.stdout, indent=2)
    print()
