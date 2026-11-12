#!/usr/bin/env python3
"""Verify BOTH live TLS listeners of every OpenBao Pod through loopback forwards."""

import argparse
import hashlib
import http.client
import json
import socket
import ssl
import subprocess  # nosec B404: allowlisted kubectl, shell-free execution.
import time
from pathlib import Path

# Trusted directories for kubectl executable resolution
TRUSTED_DIRS = [
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/bin"),
    Path.home() / "bin",
]

# Constants
KUBECTL = "kubectl"
NAMESPACE = "openbao"
LABEL_SELECTOR = "app.kubernetes.io/name=openbao,component=server"
CONTEXT = "admin@home-k8s"
REQUEST_TIMEOUT = "15s"
EXPECTED_POD_COUNT = 3
FORWARD_PORTS = ("18200:8200", "18202:8202")
LOCAL_PORTS = (18200, 18202)
READY_RETRIES = 50
READY_DELAY = 0.1
CONNECT_TIMEOUT = 5
HTTP_READ_LIMIT = 65536
SUBPROCESS_TIMEOUT = 15
SHUTDOWN_TIMEOUT = 5


def resolve_kubectl():
    """Resolve kubectl executable from trusted directories only."""
    for directory in TRUSTED_DIRS:
        candidate = directory / KUBECTL
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return str(candidate)
    raise RuntimeError("kubectl not found in trusted directories")


def create_ssl_context(ca_file):
    """Create SSL context with minimum TLS 1.2 and certificate verification."""
    context = ssl.create_default_context(cafile=str(ca_file))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def get_pods(kubectl_path):
    """Fetch OpenBao pods from Kubernetes API."""
    cmd = [
        kubectl_path,
        "get",
        "pods",
        "-n",
        NAMESPACE,
        "-l",
        LABEL_SELECTOR,
        "-o",
        "json",
        "--context",
        CONTEXT,
        "--request-timeout",
        REQUEST_TIMEOUT,
    ]
    result = subprocess.run(  # nosec B404 B603 - kubectl path validated from trusted dirs, no shell
        cmd,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"kubectl get pods failed with exit {result.returncode}")
    data = json.loads(result.stdout)
    pods = data.get("items", [])
    if len(pods) != EXPECTED_POD_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_POD_COUNT} OpenBao Pods, got {len(pods)}")
    return pods


def wait_for_port_forward(process, port):
    """Wait for port-forward to become ready on specified local port."""
    for _ in range(READY_RETRIES):
        if process.poll() is not None:
            raise RuntimeError("Port forward exited")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=READY_DELAY):
                return
        except OSError:
            time.sleep(READY_DELAY)
    raise RuntimeError("Port forward did not become ready")


def shutdown_process(process):
    """Gracefully terminate subprocess with bounded shutdown."""
    process.terminate()
    try:
        process.wait(timeout=SHUTDOWN_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=SHUTDOWN_TIMEOUT)


def probe_listener(context, hostname, port, expected_fingerprint, pod_name):
    """Probe a single TLS listener and return observation dict."""
    with socket.create_connection(("127.0.0.1", port), timeout=CONNECT_TIMEOUT) as plain:
        with context.wrap_socket(plain, server_hostname=hostname) as tls:
            cert_der = tls.getpeercert(binary_form=True)
            fingerprint = hashlib.sha256(cert_der).hexdigest()
            if expected_fingerprint and fingerprint != expected_fingerprint:
                raise RuntimeError(f"Listener has not loaded expected certificate: {pod_name}")
            request = (
                f"GET /v1/sys/health?standbyok=true HTTP/1.1\r\n"
                f"Host: {hostname}\r\n"
                f"Connection: close\r\n\r\n"
            )
            tls.sendall(request.encode())
            response = http.client.HTTPResponse(tls)
            response.begin()
            body = response.read(HTTP_READ_LIMIT + 1)
            if len(body) > HTTP_READ_LIMIT:
                raise RuntimeError("OpenBao health response exceeded the limit")
            health = json.loads(body)
            if response.status != 200 or health.get("sealed") or not health.get("initialized"):
                raise RuntimeError("OpenBao health is not ready")
            return {
                "pod": pod_name,
                "listener": port - 10000,
                "sha256": fingerprint,
                "sealed": health["sealed"],
                "standby": health["standby"],
                "raft_applied_index": health.get("raft_applied_index"),
            }


def probe_pod(context, hostname, expected_fingerprint, pod, kubectl_path):
    """Probe both listeners of a single pod via port-forward."""
    pod_name = pod["metadata"]["name"]
    pod_uid = pod["metadata"]["uid"]
    cmd = [
        kubectl_path,
        "port-forward",
        "-n",
        NAMESPACE,
        f"pod/{pod_name}",
        *FORWARD_PORTS,
        "--address=127.0.0.1",
        "--context",
        CONTEXT,
    ]
    with subprocess.Popen(  # nosec B404 B603 - kubectl path validated from trusted dirs, no shell
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as process:
        try:
            wait_for_port_forward(process, LOCAL_PORTS[0])
            observations = []
            for port in LOCAL_PORTS:
                obs = probe_listener(context, hostname, port, expected_fingerprint, pod_name)
                obs["uid"] = pod_uid
                observations.append(obs)
            return observations
        finally:
            shutdown_process(process)


def probe(ca_file, hostname, expected_fingerprint=None):
    """Verify both TLS listeners of every OpenBao Pod through loopback forwards."""
    kubectl_path = resolve_kubectl()
    context = create_ssl_context(ca_file)
    pods = get_pods(kubectl_path)
    observations = []
    for pod in pods:
        pod_obs = probe_pod(context, hostname, expected_fingerprint, pod, kubectl_path)
        observations.extend(pod_obs)
    return observations


def main():
    """CLI entry point for OpenBao TLS verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-file", required=True, type=Path)
    parser.add_argument("--hostname", default="openbao-api.int.andreybondarenko.com")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    result = probe(args.ca_file, args.hostname, args.expected_sha256)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
