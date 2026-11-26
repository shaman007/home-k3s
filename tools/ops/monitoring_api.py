#!/usr/bin/env python3
"""Read-only monitoring APIs: OpenBao consumer token and Kubernetes API proxy."""
import argparse
import json
import os
import re
import subprocess  # nosec B404 -- installed kubectl, fixed read-only verbs
import urllib.parse
import urllib.request

GRAFANA = "https://grafana.int.andreybondarenko.com"
AM_PATHS = {"/api/v2/alerts", "/api/v2/alerts/groups", "/api/v2/status", "/api/v2/receivers"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward bearer credentials through redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def grafana_get(path):
    """Use only the token passed to this consumer by bao-desktop exec grafana."""
    parsed = urllib.parse.urlsplit(path)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/api/") or ".." in urllib.parse.unquote(parsed.path).split("/"):
        raise ValueError("Expected a Grafana /api/ path")
    token = os.environ.get("GRAFANA_TOKEN")
    if not token:
        raise ValueError("Run with bao-desktop exec grafana -- COMMAND")
    request = urllib.request.Request(GRAFANA + path, headers={"Authorization": "Bearer " + token})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
        return json.load(response)


def kube_get(path):
    """No exec, Secret reads, port-forward or cluster mutations."""
    allowed = path == "/api/v1/namespaces/monitoring/pods?labelSelector=app%3Dalertmanager" or re.fullmatch(
        r"/api/v1/namespaces/monitoring/pods/http:[a-z0-9-]+:9093/proxy/api/v2/(?:alerts(?:/groups)?|status|receivers)(?:\?.*)?", path
    )
    if not allowed:
        raise ValueError("Only Alertmanager discovery and read-only proxy routes are allowed")
    result = subprocess.run(["kubectl", "--request-timeout=10s", "get", "--raw", path], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def alertmanager_get(path="/api/v2/alerts"):
    """Read every replica because direct Sidekick alerts are not replicated."""
    if urllib.parse.urlsplit(path).path not in AM_PATHS:
        raise ValueError("Unsupported read-only Alertmanager API path")
    pods = kube_get("/api/v1/namespaces/monitoring/pods?labelSelector=app%3Dalertmanager")
    results = []
    for pod in pods["items"]:
        name = pod["metadata"]["name"]
        if pod["status"].get("phase") != "Running":
            continue
        data = kube_get(f"/api/v1/namespaces/monitoring/pods/http:{name}:9093/proxy{path}")
        results.append({"replica": name, "data": data})
    if not results:
        raise RuntimeError("No running Alertmanager replicas")
    return results


def alert_summary(results):
    """Avoid command arguments and raw event annotations in routine output."""
    return [{"replica": replica["replica"], "alerts": [{
        "name": alert["labels"].get("alertname"), "job": alert["labels"].get("job"),
        "namespace": alert["labels"].get("k8s_ns_name", alert["labels"].get("namespace")),
        "pod": alert["labels"].get("k8s_pod_name"), "fingerprint": alert["fingerprint"],
        "startsAt": alert["startsAt"], "endsAt": alert["endsAt"], "state": alert["status"]["state"],
    } for alert in replica["data"]]} for replica in results]


def main():
    """Expose GET-only diagnostics; credentials never enter argv or files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=["grafana", "alertmanager"])
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    if args.service == "grafana":
        result = grafana_get(args.path or "/api/health")
    else:
        result = alertmanager_get(args.path or "/api/v2/alerts")
        if not args.path:
            result = alert_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
