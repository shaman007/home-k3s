#!/usr/bin/env python3
"""Canonical local mail startup/readiness sources; never call the cluster."""

import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class SourceDumper(yaml.SafeDumper):
    """Keep multiline scripts literal and sequences consistent with source style."""

    def increase_indent(self, flow=False, indentless=False):
        """Keep list indentation consistent with the existing manifests."""
        return super().increase_indent(flow, False)

    def represent_string(self, value):
        """Keep copied scripts and configuration reviewable as literal blocks."""
        return self.represent_scalar(
            "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None
        )


SourceDumper.add_representer(str, SourceDumper.represent_string)


def read(path):
    """Read only non-secret Git sources."""
    return yaml.safe_load((ROOT / path).read_text())


def attach(pod, container, name):
    """Only replace our code mount, preserving every existing data/secret mount."""
    mounts = container.setdefault("volumeMounts", [])
    mounts[:] = [m for m in mounts if m["name"] != "mail-startup"]
    mounts.append(
        {"name": "mail-startup", "mountPath": "/mail-startup", "readOnly": True}
    )
    volumes = pod.setdefault("volumes", [])
    volumes[:] = [v for v in volumes if v["name"] != "mail-startup"]
    volumes.append({"name": "mail-startup", "configMap": {"name": name}})


def init_container(image, profile):
    """Use the existing application image, no API token and no shared data mounts."""
    return {
        "name": "wait-for-mail-dependencies",
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "command": [
            "timeout",
            "-s",
            "TERM",
            "-k",
            "1",
            "305",
            "perl",
            "/mail-startup/mail_dependency_gate.pl",
            "--wait",
            profile,
        ],
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 11333,
            "runAsGroup": 11333,
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "resources": {
            "requests": {"cpu": "10m", "memory": "64Mi"},
            "limits": {"memory": "128Mi"},
        },
    }


def build_deployment(app, cm):
    """Gate application startup and readiness without modifying local liveness."""
    path = f"mail/deployment-{app}.yaml"
    deployment = read(path)
    if app == "postfix":
        deployment["metadata"].setdefault("annotations", {})[
            "argocd.argoproj.io/sync-wave"
        ] = "1"
    pod = deployment["spec"]["template"]["spec"]
    work = next(
        c
        for c in pod["containers"]
        if c["name"] == ("rspamd" if app == "rspamd" else "postfix-mail")
    )
    profile = app + "-dependencies"
    init = init_container(work["image"], profile)
    attach(pod, init, cm["metadata"]["name"])
    containers = pod.setdefault("initContainers", [])
    containers[:] = [c for c in containers if c["name"] != init["name"]]
    containers.append(init)
    attach(pod, work, cm["metadata"]["name"])
    if app == "rspamd":
        command = [
            "timeout",
            "-s",
            "TERM",
            "-k",
            "1",
            "8",
            "perl",
            "/mail-startup/mail_dependency_gate.pl",
            "--check",
            "rspamd-ready",
        ]
    else:
        command = [
            "/usr/bin/sh",
            "-ec",
            (
                "postfix status >/dev/null 2>&1; "
                "exec timeout -s TERM -k 1 8 perl /mail-startup/mail_dependency_gate.pl "
                "--check postfix-dependencies"
            ),
        ]
    work["readinessProbe"] = {
        "exec": {"command": command},
        "periodSeconds": 10,
        "timeoutSeconds": 10,
        "failureThreshold": 1,
    }
    # Liveness stays strictly daemon-local: dependent outages must not restart Pods.
    return path, deployment


def documents():
    """Prepare an acyclic mail graph while preserving spool, mailboxes and TLS."""
    data = {
        "mail_dependency_gate.pl": (
            ROOT / "tools/bootstrap/mail_dependency_gate.pl"
        ).read_text()
    }
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]
    cm = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "immutable": True,
        "metadata": {"name": "mail-startup-" + digest, "namespace": "mail"},
        "data": data,
    }
    result = {"mail/config-map-" + cm["metadata"]["name"] + ".yaml": cm}
    for app in ("rspamd", "postfix"):
        path, deployment = build_deployment(app, cm)
        result[path] = deployment
    path = "mail/stateful-set-valkey.yaml"
    valkey = list(yaml.safe_load_all((ROOT / path).read_text()))
    provider = next(d for d in valkey if d["kind"] == "StatefulSet")
    pod = provider["spec"]["template"]["spec"]
    work = next(c for c in pod["containers"] if c["name"] == "valkey")
    if work.get("args") != ["--appendonly", "yes", "--save", "60", "1"] or work.get(
        "envFrom"
    ):
        raise ValueError("Review changed Valkey authentication/startup contract")
    old = pod.get("initContainers", [])
    pod["initContainers"] = [c for c in old if c["name"] != "wait-for-redis-shutdown"]
    if not pod["initContainers"]:
        del pod["initContainers"]
    result[path] = valkey
    postfix_config = read("mail/config-map-main-cf.yaml")
    config = postfix_config["data"]["config"]
    if "milter_default_action = accept" in config:
        config = config.replace(
            "milter_default_action = accept", "milter_default_action = tempfail"
        )
    if "milter_default_action = tempfail" not in config:
        raise ValueError("Review changed Postfix milter policy")
    postfix_config["data"]["config"] = config
    result["mail/config-map-main-cf.yaml"] = postfix_config
    rspamd = read("mail/config-map-rspamd-cf.yaml")
    rspamd["data"]["force_actions"] = """rules {
  CLAMAV_UNAVAILABLE {
    action = "soft reject";
    expression = "CLAM_VIRUS_FAIL";
    message = "Antivirus temporarily unavailable; please retry later";
    honor_action = ["reject", "soft reject"];
  }
}
"""
    result["mail/config-map-rspamd-cf.yaml"] = rspamd
    deployment = result["mail/deployment-rspamd.yaml"]
    pod = deployment["spec"]["template"]["spec"]
    work = next(c for c in pod["containers"] if c["name"] == "rspamd")
    pod["volumes"] = [v for v in pod["volumes"] if v["name"] != "force-actions-cf"]
    pod["volumes"].append(
        {
            "name": "force-actions-cf",
            "configMap": {
                "name": "rspamd-cf",
                "items": [{"key": "force_actions", "path": "force_actions.conf"}],
            },
        }
    )
    work["volumeMounts"] = [
        m for m in work["volumeMounts"] if m["name"] != "force-actions-cf"
    ]
    work["volumeMounts"].append(
        {
            "name": "force-actions-cf",
            "mountPath": "/etc/rspamd/local.d/force_actions.conf",
            "subPath": "force_actions.conf",
            "readOnly": True,
        }
    )
    return result


def main():
    """Write only with an explicit local flag; default verifies canonical sources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-source", action="store_true")
    args = parser.parse_args()
    for relative, document in documents().items():
        path = ROOT / relative
        docs = document if isinstance(document, list) else [document]
        if args.write_source:
            path.write_text(
                yaml.dump_all(docs, Dumper=SourceDumper, sort_keys=False, width=110)
            )
        elif not path.exists() or list(yaml.safe_load_all(path.read_text())) != docs:
            raise ValueError("Mail gate source differs: " + relative)
    print(
        "Mail gate sources updated"
        if args.write_source
        else "Mail gate sources checked"
    )


if __name__ == "__main__":
    main()
