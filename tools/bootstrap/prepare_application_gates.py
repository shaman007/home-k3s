"""Generate native-client startup gates for five stacks; never contact Kubernetes."""

import argparse
import copy
import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class SourceDumper(yaml.SafeDumper):
    """Use readable script blocks and the repository's indented sequence style."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def represent_string(dumper, value):
    """Keep generated script copies reviewable."""
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None
    )


SourceDumper.add_representer(str, represent_string)
SCRIPTS = ("wait_service.sh", "probe_data.php", "probe_http.cjs")
MOUNT = {"name": "startup-gate", "mountPath": "/startup-gate", "readOnly": True}
SECURITY = {
    "allowPrivilegeEscalation": False,
    "readOnlyRootFilesystem": True,
    "runAsNonRoot": True,
    "runAsUser": 65534,
    "runAsGroup": 65534,
    "capabilities": {"drop": ["ALL"]},
    "seccompProfile": {"type": "RuntimeDefault"},
}


def load(path):
    """Read one tracked manifest, without resolving Secret values."""
    return yaml.safe_load((ROOT / path).read_text())


def container(path, name):
    """Use the stack's existing pinned image, including Renovate updates."""
    return next(
        c
        for c in load(path)["spec"]["template"]["spec"]["containers"]
        if c["name"] == name
    )


def renamed(environment, mapping):
    """Copy existing literals/Secret refs under a native client's environment names."""
    result = []
    # Mapping values are environment variable names; no password values are embedded.
    for source, target in mapping.items():
        entry = copy.deepcopy(next(e for e in environment if e["name"] == source))
        entry["name"] = target
        if target == "PGPASSWORD" and "secretKeyRef" not in entry.get("valueFrom", {}):
            raise ValueError("Password must remain a Secret reference")
        result.append(entry)
    return result


def gate(name, image, mode, env=None, mounts=None):
    """Harden a sequential init container and suppress raw client diagnostics."""
    uid = 33 if mode.startswith(("nextcloud-", "wordpress-")) else 65534
    if mode in {"ferretdb", "spotify"}:
        uid = 1000
    security = copy.deepcopy(SECURITY)
    security.update(runAsUser=uid, runAsGroup=uid)
    return {
        "name": name,
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "command": ["/bin/sh", "/startup-gate/wait_service.sh", mode],
        "securityContext": security,
        "resources": {
            "requests": {"cpu": "10m", "memory": "32Mi"},
            "limits": {"memory": "128Mi"},
        },
        "env": env or [],
        "volumeMounts": [copy.deepcopy(MOUNT)] + (mounts or []),
    }


def attach_php_stacks(attach):
    """Mount application configs read-only and avoid PHP bootstrap side effects."""
    for folder, path, name, volume, mount in [
        (
            "nextcloud",
            "nextcloud/stateful-set-nextcloud-web.yaml",
            "php-nextcloud",
            "nextcloud-lh",
            "/nextcloud",
        ),
        ("wordpress", "wordpress/deployment-php.yaml", "php", "wordpress-lh", "/code"),
    ]:
        app = container(path, name)
        mounts = [{"name": volume, "mountPath": mount, "readOnly": True}]
        attach(
            path,
            [
                gate("wait-for-sql", app["image"], folder + "-sql", mounts=mounts),
                gate(
                    "wait-for-valkey",
                    app["image"],
                    folder + "-valkey",
                    mounts=mounts,
                ),
            ],
        )


def candidates():
    """Return exact source candidates; app entrypoints and migrations remain untouched."""
    scripts = {name: (ROOT / "tools/bootstrap" / name).read_text() for name in SCRIPTS}
    result = {}
    configs = {}

    def attach(path, gates):
        document = load(path)
        namespace = document["metadata"]["namespace"]
        pod = document["spec"]["template"]["spec"]
        config_name = namespace + "-startup-gate"
        selected = {"wait_service.sh": scripts["wait_service.sh"]}
        if namespace in {"nextcloud", "wordpress"}:
            selected["probe_data.php"] = scripts["probe_data.php"]
        if namespace == "spotify":
            selected["probe_http.cjs"] = scripts["probe_http.cjs"]
        digest = hashlib.sha256(
            "".join(k + v for k, v in selected.items()).encode()
        ).hexdigest()
        configs[namespace] = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": config_name, "namespace": namespace},
            "data": selected,
        }
        document["spec"]["template"]["metadata"].setdefault("annotations", {})[
            "checksum/application-startup-gate"
        ] = digest
        names = {g["name"] for g in gates}
        pod["initContainers"] = [
            c for c in pod.get("initContainers", []) if c["name"] not in names
        ] + gates
        pod["volumes"] = [
            v for v in pod.get("volumes", []) if v["name"] != "startup-gate"
        ] + [{"name": "startup-gate", "configMap": {"name": config_name}}]
        result[path] = document
        return pod

    path = "immich/deployment-immich-server.yaml"
    app = container(path, "immich-server")
    pg = container("immich/stateful-set-immich-postgres.yaml", "postgres")
    valkey = load("immich/stateful-set-immich-valkey.yaml")["spec"]["template"]["spec"][
        "containers"
    ][0]
    env = renamed(
        app["env"],
        {
            "DB_HOSTNAME": "PGHOST",
            "DB_DATABASE_NAME": "PGDATABASE",
            "DB_USERNAME": "PGUSER",
            "DB_PASSWORD": "PGPASSWORD",  # nosec B105
        },
    )
    redis_env = renamed(app["env"], {"REDIS_HOSTNAME": "VALKEY_HOST"})
    attach(
        path,
        [
            gate("wait-for-postgres", pg["image"], "postgres", env),
            gate("wait-for-valkey", valkey["image"], "valkey", redis_env),
        ],
    )

    path = "keycloak/stateful-set-keycloak.yaml"
    app = container(path, "keycloak")
    pg = load("keycloak/stateful-set-keycloak-postgres.yaml")["spec"]["template"][
        "spec"
    ]["containers"][0]
    env = renamed(
        app["env"],
        {
            "KC_DB_URL_HOST": "PGHOST",
            "KC_DB_URL_DATABASE": "PGDATABASE",
            "KC_DB_USERNAME": "PGUSER",
            "KC_DB_PASSWORD": "PGPASSWORD",  # nosec B105
        },
    )
    attach(path, [gate("wait-for-postgres", pg["image"], "postgres", env)])

    attach_php_stacks(attach)

    pg = container("your-spotify/stateful-set-ferretdb-postgres.yaml", "postgres")
    env = renamed(
        pg["env"],
        {
            "POSTGRES_USER": "PGUSER",
            "POSTGRES_PASSWORD": "PGPASSWORD",  # nosec B105
            "POSTGRES_DB": "PGDATABASE",
        },
    )
    env.append(
        {"name": "PGHOST", "value": "ferretdb-postgres.spotify.svc.cluster.local"}
    )
    pod = attach(
        "your-spotify/deployment-ferretdb.yaml",
        [gate("wait-for-postgres", pg["image"], "postgres", env)],
    )
    pod["containers"][0]["readinessProbe"] = {
        "httpGet": {"path": "/debug/readyz", "port": "debug"},
        "periodSeconds": 10,
        "timeoutSeconds": 5,
        "failureThreshold": 3,
    }
    server = container("your-spotify/deployment-server.yaml", "server")
    attach(
        "your-spotify/deployment-server.yaml",
        [gate("wait-for-ferretdb", server["image"], "ferretdb")],
    )
    attach(
        "your-spotify/deployment-web.yaml",
        [gate("wait-for-server", server["image"], "spotify")],
    )
    for namespace, config in configs.items():
        folder = "your-spotify" if namespace == "spotify" else namespace
        result[folder + "/config-map-startup-gate.yaml"] = config
    return result


def block_edit(node, document, path):
    """Locate one changed mapping entry using YAML source marks."""
    parent = node
    value = document
    for key in path[:-1]:
        parent = (
            parent.value[key]
            if isinstance(key, int)
            else next(v for k, v in parent.value if k.value == key)
        )
        value = value[key]
    key = path[-1]
    pairs = [(k, v) for k, v in parent.value if k.value == key]
    fragment = yaml.dump(
        {key: value[key]}, Dumper=SourceDumper, sort_keys=False, width=110
    )
    if pairs:
        start, end = pairs[0][0].start_mark.line, pairs[0][1].end_mark.line
        indent = pairs[0][0].start_mark.column
    else:
        start = end = parent.start_mark.line
        indent = parent.start_mark.column
    text = "".join(" " * indent + line + "\n" for line in fragment.splitlines())
    return start, end, text


def update_blocks(source, document):
    """Replace only gate-related YAML blocks; retain unrelated comments and formatting."""
    node = yaml.compose(source)
    paths = [
        ("spec", "template", "metadata", "annotations"),
        ("spec", "template", "spec", "initContainers"),
        ("spec", "template", "spec", "volumes"),
    ]
    if document["metadata"]["name"] == "ferretdb":
        paths.append(("spec", "template", "spec", "containers", 0, "readinessProbe"))
    edits = [block_edit(node, document, path) for path in paths]
    lines = source.splitlines(keepends=True)
    for start, end, text in sorted(edits, reverse=True):
        lines[start:end] = [text]
    result = "".join(lines)
    if yaml.safe_load(result) != document:
        raise ValueError("Source-preserving rendering mismatch")
    return result


def main():
    """Check or generate local GitOps files; deployment is a separate action."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-source", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for relative, document in candidates().items():
        path = ROOT / relative
        if args.check:
            if not path.exists() or yaml.safe_load(path.read_text()) != document:
                raise SystemExit("Stale application gate source: " + relative)
        elif document["kind"] == "ConfigMap":
            path.write_text(
                yaml.dump(document, Dumper=SourceDumper, sort_keys=False, width=110)
            )
        else:
            path.write_text(update_blocks(path.read_text(), document))
    print(
        "Application gates checked"
        if args.check
        else "Local source updated; no cluster calls made"
    )


if __name__ == "__main__":
    main()
