"""Read benchmark API keys through validated, bounded Kubernetes secret lookup."""

import base64
import json
import os
import re
import subprocess

DNS_LABEL = r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
DNS_SUBDOMAIN = DNS_LABEL + r"(?:\." + DNS_LABEL + r")*"


def secret_reference(reference):
    """Validate namespace DNS labels and Secret DNS subdomains before command construction."""
    parts = reference.split("/")
    if len(parts) != 2:
        raise ValueError("Kubernetes secret must use namespace/name")
    namespace, name = parts
    if (
        len(namespace) > 63
        or not re.fullmatch(DNS_LABEL, namespace)
        or len(name) > 253
        or not re.fullmatch(DNS_SUBDOMAIN, name)
    ):
        raise ValueError("Kubernetes secret must use valid namespace/name identifiers")
    return namespace, name


def load_api_key(kubernetes_secret):
    """Use the environment key or an explicitly selected secret without printing credentials."""
    if not kubernetes_secret:
        return os.environ.get("LLM_API_KEY", "")
    namespace, name = secret_reference(kubernetes_secret)
    secret = json.loads(
        subprocess.check_output(
            [
                "kubectl",
                "get",
                "secret",
                "-n",
                namespace,
                name,
                "-o",
                "json",
                "--request-timeout=15s",
            ],
            shell=False,
            timeout=30,
        )
    )
    return base64.b64decode(secret["data"]["key"]).decode().strip()
