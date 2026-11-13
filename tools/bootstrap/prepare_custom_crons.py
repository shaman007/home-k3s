#!/usr/bin/env python3
"""Render or verify the seven reviewed custom CronJob dependency gates locally."""

import argparse
import copy
from pathlib import Path

import prepare_cron_gate as reports
import prepare_dependency_batch as batch
import yaml

ROOT = Path(__file__).resolve().parents[2]


def mount(pod, container, cm):
    """Replace only this generator's mount, preserving existing Job integrations."""
    container["volumeMounts"] = [
        m for m in container.get("volumeMounts", []) if m["name"] != "cron-gate"
    ]
    container["volumeMounts"].append(
        {"name": "cron-gate", "mountPath": "/cron-gate", "readOnly": True}
    )
    pod["volumes"] = [v for v in pod.get("volumes", []) if v["name"] != "cron-gate"]
    pod["volumes"].append(
        {"name": "cron-gate", "configMap": {"name": cm["metadata"]["name"]}}
    )


def mastodon(bookmarked=False):
    """Guard both containers of media sync, or read-only Rails prerequisites."""
    name = "bookmarked-media-sync" if bookmarked else "mastodon-spam-list-sync"
    path = (
        "mastodon/cron-job-bookmarked-media-sync.yaml"
        if bookmarked
        else "mastodon/cron-job-spam-list-sync.yaml"
    )
    job = yaml.safe_load((ROOT / path).read_text())
    pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    work = pod["containers"][0]
    if bookmarked:
        files = {
            n: batch.script(n)
            for n in (
                "bookmarked_job_gate.sh",
                "bookmarked_upload_probe.cjs",
                "mastodon_startup.rb",
            )
        }
        service_account = "/var/run/secrets/kubernetes.io/serviceaccount"
        files["kubeconfig"] = yaml.safe_dump(
            {
                "apiVersion": "v1",
                "kind": "Config",
                "clusters": [
                    {
                        "name": "in-cluster",
                        "cluster": {
                            "server": "https://kubernetes.default.svc",
                            "certificate-authority": service_account + "/ca.crt",
                        },
                    }
                ],
                "users": [
                    {
                        "name": "service-account",
                        "user": {"tokenFile": service_account + "/token"},
                    }
                ],
                "contexts": [
                    {
                        "name": "in-cluster",
                        "context": {
                            "cluster": "in-cluster",
                            "user": "service-account",
                            "namespace": "mastodon",
                        },
                    }
                ],
                "current-context": "in-cluster",
            },
            sort_keys=False,
        )
        cm = batch.config_map(name + "-dependencies", "mastodon", files)
        init = pod["initContainers"][0]
        old = "/scripts/fetch-bookmarked-media.sh"
        desired = "/bin/sh /cron-gate/bookmarked_job_gate.sh"
        if old in init["command"][-1]:
            init["command"][-1] = init["command"][-1].replace(old, desired)
        elif desired not in init["command"][-1]:
            raise ValueError("Review changed media fetch command")
        keys = ("IMMICH_INSTANCE_URL", "IMMICH_API_KEY")
        init["env"] = [e for e in init.get("env", []) if e["name"] not in keys]
        init["env"].extend(copy.deepcopy([e for e in work["env"] if e["name"] in keys]))
        prefix = """# BEGIN dependency gate
if [ -f /work/.dependencies-skipped ]; then
  printf '{"event":"cron_dependencies","result":"skipped"}\\n'
  exit 0
fi
status=0
node /cron-gate/bookmarked_upload_probe.cjs || status=$?
case "$status" in 0) ;; 75) exit 0 ;; *) exit "$status" ;; esac
# END dependency gate
"""
        if "# BEGIN dependency gate" not in work["command"][-1]:
            if not work["command"][-1].startswith("set -eu\n"):
                raise ValueError("Review changed uploader command")
            work["command"][-1] = work["command"][-1].replace(
                "set -eu\n", "set -eu\n" + prefix, 1
            )
        mount(pod, init, cm)
    else:
        cm = batch.config_map(
            name + "-dependencies",
            "mastodon",
            {
                n: batch.script(n)
                for n in ("mastodon_spam_job_gate.sh", "mastodon_startup.rb")
            },
        )
        desired = ["/bin/sh", "/cron-gate/mastodon_spam_job_gate.sh"]
        if (
            work["command"] != ["bundle", "exec", "rails", "runner", "/scripts/sync.rb"]
            and work["command"] != desired
        ):
            raise ValueError("Review changed spam sync command")
        work["command"] = desired
    mount(pod, work, cm)
    return {path: job, f"mastodon/config-map-{cm['metadata']['name']}.yaml": cm}


def documents():
    """Only CronJobs and their immutable script ConfigMaps; no Longhorn sources."""
    result = {}
    for name, definition in reports.REPORTS.items():
        cm, job = reports.candidate(name)
        path = Path(definition[0])
        result[str(path)] = job
        result[
            str(path.parent / ("config-map-" + cm["metadata"]["name"] + ".yaml"))
        ] = cm
    for factory in (batch.nextcloud_cron, batch.mail_training):
        for path, doc in factory().items():
            if doc["kind"] == "ConfigMap":
                path = str(
                    Path(path).parent
                    / ("config-map-" + doc["metadata"]["name"] + ".yaml")
                )
            result[path] = doc
    result.update(mastodon())
    result.update(mastodon(True))
    return result


def main():
    """Writing changes Git sources only, never cluster state."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-source", action="store_true")
    args = parser.parse_args()
    for relative, document in documents().items():
        path = ROOT / relative
        if args.write_source:
            path.write_text(yaml.safe_dump(document, sort_keys=False))
        elif not path.exists() or yaml.safe_load(path.read_text()) != document:
            raise ValueError("Custom CronJob source differs: " + relative)
    print(
        "Custom CronJob sources updated"
        if args.write_source
        else "Custom CronJob sources checked"
    )


if __name__ == "__main__":
    main()
