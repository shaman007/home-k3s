#!/usr/bin/env python3
"""Explicit, secret-safe OpenBao TLS stages. Never uses kubectl apply or Git writes.

Stages write encrypted recovery material and JSON patches into a private state
directory. Each mutation stage must be separately invoked; no implicit rollout.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
# Administrative processes use the executable allowlist and never an implicit shell.
import subprocess  # nosec B404

import yaml

try:
    from tools.bootstrap.probe_openbao_tls import probe
except ModuleNotFoundError:
    from probe_openbao_tls import probe

ROOT = Path(__file__).resolve().parents[2]
OLD_HOST = "openbao-api.int.andreybondarenko.com"
NEW_HOST = "openbao-active.openbao.svc.cluster.local"
OLD_URL = "https://" + OLD_HOST + ":8200"
NEW_URL = "https://" + NEW_HOST + ":8200"
CA_OBJECT_NAME = "openbao-internal-root-ca"
BACKEND_OBJECT_NAME = "openbao-server-letsencrypt-tls"


def executable(program):
    """Resolve an allowlisted executable without consulting the ambient PATH."""
    if program not in ("kubectl", "age", "openssl"):
        raise ValueError("Unsupported administrative executable")
    trusted_path = "/usr/local/bin:/usr/bin:/bin:" + str(Path.home() / "bin")
    resolved = shutil.which(program, path=trusted_path)
    if not resolved or not os.path.isabs(resolved):
        raise FileNotFoundError("Required administrative executable is not installed")
    return resolved


def run(args, payload=None):
    """Run an allowlisted command with bounded execution and secret-safe errors."""
    argv = [executable(args[0]), *args[1:]]
    # Executable is allowlisted and absolute; input is bytes, never shell source.
    result = subprocess.run(  # nosec B603
        argv,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Command failed (details suppressed): " + " ".join(args[:3]))
    return result.stdout


def kube(*args, payload=None):
    """Pin administrative Kubernetes operations to the intended context."""
    return run(
        ["kubectl", *args, "--context=admin@home-k8s", "--request-timeout=20s"], payload
    )


def get(resource, name=None, ns=None):
    """Read Kubernetes objects as JSON without emitting their payloads."""
    args = ["get", resource]
    if name:
        args.append(name)
    args.extend(["-n", ns] if ns else ["-A"])
    return json.loads(kube(*args, "-o", "json"))


def clean(obj):
    """Retain restorable desired fields without status or apply annotations."""
    result = {
        k: obj[k] for k in ("apiVersion", "kind", "spec", "data", "type") if k in obj
    }
    result["metadata"] = {
        k: obj["metadata"][k]
        for k in ("name", "namespace", "labels", "annotations")
        if k in obj["metadata"]
    }
    result["metadata"].get("annotations", {}).pop(
        "kubectl.kubernetes.io/last-applied-configuration", None
    )
    return result


def write(state, name, value):
    """Write non-secret recovery metadata with owner-only permissions."""
    path = state / name
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def encrypted_backup(state, name, objects):
    """Encrypt sensitive objects in memory and verify an exact age round trip."""
    recipient = (
        Path("/home/shaman007/.config/talos-backup/age-recipient.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    identity = "/home/shaman007/.config/talos-backup/age-key.txt"
    plaintext = json.dumps(objects, sort_keys=True).encode()
    output = state / (name + ".json.age")
    if output.exists():
        raise ValueError("Refusing to overwrite encrypted backup")
    ciphertext = run(["age", "-r", recipient], plaintext)
    output.write_bytes(ciphertext)
    output.chmod(0o600)
    restored = run(["age", "-d", "-i", identity, str(output)])
    if restored != plaintext:
        raise RuntimeError("Encrypted backup round trip differs")
    write(
        state,
        name + "-verification.json",
        {
            "sha256": hashlib.sha256(ciphertext).hexdigest(),
            "bytes": len(ciphertext),
            "decryption_verified": True,
            "objects": [o["metadata"]["name"] for o in objects],
        },
    )


def ca_public():
    """Return the public root only after matching its key using OpenSSL stdin."""
    secret = get("secret", CA_OBJECT_NAME, "openbao")
    cert = base64.b64decode(secret["data"]["tls.crt"])
    private_public = run(
        ["openssl", "pkey", "-pubout"], base64.b64decode(secret["data"]["tls.key"])
    )
    certificate_public = run(["openssl", "x509", "-pubkey", "-noout"], cert)
    if private_public != certificate_public:
        raise RuntimeError("CA private key mismatch")
    return cert


def public_roots():
    """Select only existing ISRG public roots for temporary dual trust."""
    roots = []
    context = ssl.create_default_context()
    for parsed, der in zip(
        context.get_ca_certs(), context.get_ca_certs(binary_form=True), strict=True
    ):
        names = [
            value
            for part in parsed["subject"]
            for key, value in part
            if key == "commonName"
        ]
        if any(name in ("ISRG Root X1", "ISRG Root X2") for name in names):
            roots.append(ssl.DER_cert_to_PEM_cert(der).encode())
    if len(roots) != 2:
        raise RuntimeError("Expected both current ISRG trust roots")
    return b"".join(roots)


def patch(resource, name, ns, value):
    """Send an explicit merge patch without displaying the resulting object."""
    args = ["patch", resource, name]
    if ns:
        args.extend(["-n", ns])
    return kube(*args, "--type=merge", "-p", json.dumps(value))


def snapshot(state):
    """Capture original scoped configuration and encrypted backend recovery keys."""
    if state.exists():
        raise ValueError("Snapshot directory must not already exist")
    state.mkdir(parents=True, mode=0o700)
    stores = [
        x
        for x in get("secretstores,clustersecretstores")["items"]
        if x.get("spec", {}).get("provider", {}).get("vault", {}).get("server")
        == OLD_URL
    ]
    apps = sorted(
        {
            x["metadata"]["annotations"]["argocd.argoproj.io/tracking-id"].split(":")[0]
            for x in stores
        }
        | {"argocd-applications", "openbao", "openbao-custom", "kubernetes-prometheus"}
    )
    objects = [clean(x) for x in stores]
    objects += [clean(get("application", name, "argocd")) for name in apps]
    for resource, name, ns in [
        ("statefulset", "openbao", "openbao"),
        ("configmap", "openbao-config", "openbao"),
        ("certificate", BACKEND_OBJECT_NAME, "openbao"),
        ("serverstransport", "openbao-server", "openbao"),
        ("configmap", "vault-ca", "monitoring"),
        ("configmap", "prometheus-server-conf", "monitoring"),
        ("deployment", "prometheus-deployment", "monitoring"),
    ]:
        objects.append(clean(get(resource, name, ns)))
    write(state, "baseline.json", {"objects": objects, "apps": apps})
    encrypted_backup(
        state, "old-backend-tls", [clean(get("secret", BACKEND_OBJECT_NAME, "openbao"))]
    )
    print(
        json.dumps(
            {
                "snapshot": str(state),
                "stores": len(stores),
                "apps": len(apps),
                "old_tls_encrypted_and_verified": True,
            }
        )
    )


def bootstrap(state):
    """Create the reviewed PKI only after an original-state snapshot exists."""
    baseline = json.loads((state / "baseline.json").read_text())
    if not baseline["objects"]:
        raise ValueError("A nonempty rollback baseline is required")
    # An old-DNS SAN permits a rolling, dual-trust change without client name failures.
    documents = list(
        yaml.safe_load_all(
            (ROOT / "docs/migrations/openbao-internal-tls/pki.yaml").read_text()
        )
    )
    for doc in documents:
        if (
            doc["kind"] == "Certificate"
            and doc["metadata"]["name"] == "openbao-internal-tls"
        ):
            if OLD_HOST not in doc["spec"]["dnsNames"]:
                doc["spec"]["dnsNames"].append(OLD_HOST)
    manifest = state / "pki.yaml"
    manifest.write_text(yaml.safe_dump_all(documents, sort_keys=False))
    kube("create", "-f", str(manifest))
    print("PKI resources created; no server/client TLS changed")


def backup_pki(state):
    """Preserve CA/leaf keys independently before allowing any TLS cutover."""
    objects = [
        clean(get("secret", name, "openbao"))
        for name in (CA_OBJECT_NAME, "openbao-internal-tls")
    ]
    encrypted_backup(state, "internal-pki", objects)
    cert = ca_public()
    (state / "root-ca.pem").write_bytes(cert)
    (state / "dual-trust.pem").write_bytes(public_roots() + cert)
    print("CA/leaf encrypted backup decrypted and matched; public trust exported")


def dual_trust(state):
    """Stage client trust without changing the live server certificate."""
    if not json.loads((state / "internal-pki-verification.json").read_text())[
        "decryption_verified"
    ]:
        raise ValueError("Verified off-cluster CA backup is required")
    baseline = json.loads((state / "baseline.json").read_text())
    bundle = (state / "dual-trust.pem").read_bytes()
    for name in ["argocd-applications"] + [
        n for n in baseline["apps"] if n != "argocd-applications"
    ]:
        patch(
            "application",
            name,
            "argocd",
            {
                "metadata": {
                    "annotations": {"argocd.argoproj.io/skip-reconcile": "true"}
                }
            },
        )
    for obj in baseline["objects"]:
        if obj["kind"] not in ("SecretStore", "ClusterSecretStore"):
            continue
        patch(
            obj["kind"],
            obj["metadata"]["name"],
            obj["metadata"].get("namespace"),
            {
                "spec": {
                    "provider": {
                        "vault": {
                            "caBundle": base64.b64encode(bundle).decode(),
                            "caProvider": None,
                        }
                    }
                }
            },
        )
    trust_secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "openbao-backend-trust", "namespace": "openbao"},
        "type": "Opaque",
        "data": {"ca.crt": base64.b64encode(bundle).decode()},
    }
    # Public roots only, no private key in this trust-only Secret.
    kube("create", "-f", "-", payload=json.dumps(trust_secret).encode())
    patch(
        "serverstransport",
        "openbao-server",
        "openbao",
        {"spec": {"rootCAsSecrets": ["openbao-backend-trust"]}},
    )
    patch("configmap", "vault-ca", "monitoring", {"data": {"ca.crt": bundle.decode()}})
    deployment = get("deployment", "prometheus-deployment", "monitoring")
    pod = deployment["spec"]["template"]["spec"]
    pod["volumes"] = [v for v in pod["volumes"] if v["name"] != "openbao-internal-ca"]
    pod["volumes"].append(
        {"name": "openbao-internal-ca", "configMap": {"name": "vault-ca"}}
    )
    found = False
    for container in pod["containers"]:
        if "prometheus" in container["name"]:
            container["volumeMounts"] = [
                m
                for m in container.get("volumeMounts", [])
                if m["name"] != "openbao-internal-ca"
            ]
            container["volumeMounts"].append(
                {
                    "name": "openbao-internal-ca",
                    "mountPath": "/etc/openbao-ca",
                    "readOnly": True,
                }
            )
            found = True
    if not found:
        raise RuntimeError("Prometheus container not identified")
    patch(
        "deployment",
        "prometheus-deployment",
        "monitoring",
        {"spec": {"template": {"spec": pod}}},
    )
    config = get("configmap", "prometheus-server-conf", "monitoring")
    for key, text in config["data"].items():
        if "job_name: openbao" not in text:
            continue
        settings = yaml.safe_load(text)
        job = next(
            x for x in settings["scrape_configs"] if x.get("job_name") == "openbao"
        )
        job.setdefault("tls_config", {})["ca_file"] = "/etc/openbao-ca/ca.crt"
        config["data"][key] = yaml.safe_dump(settings, sort_keys=False)
    patch("configmap", "prometheus-server-conf", "monitoring", {"data": config["data"]})
    print("Dual trust staged; backend certificate unchanged; scoped Argo apps paused")


def switch(state):
    """Reissue the existing mounted certificate using the independent CA."""
    leaf = next(
        x
        for x in yaml.safe_load_all((state / "pki.yaml").read_text())
        if x["kind"] == "Certificate"
        and x["metadata"]["name"] == "openbao-internal-tls"
    )
    spec = leaf["spec"].copy()
    spec["secretName"] = BACKEND_OBJECT_NAME
    # Existing projected Secret paths auto-reload on BOTH listeners; no pod restart.
    patch("certificate", BACKEND_OBJECT_NAME, "openbao", {"spec": spec})
    print(
        "Backend Certificate switched to internal Issuer; wait for issuance and live TLS reload"
    )


def migrate(state):
    """Move stores to internal DNS and configure trust for future server starts."""
    baseline = json.loads((state / "baseline.json").read_text())
    for obj in baseline["objects"]:
        if obj["kind"] in ("SecretStore", "ClusterSecretStore"):
            patch(
                obj["kind"],
                obj["metadata"]["name"],
                obj["metadata"].get("namespace"),
                {"spec": {"provider": {"vault": {"server": NEW_URL}}}},
            )
    # Future restarts must verify retry_join against the internal root too.
    config = get("configmap", "openbao-config", "openbao")
    hcl = config["data"]["extraconfig-from-values.hcl"]
    hcl = hcl.replace(OLD_URL, NEW_URL).replace(
        'leader_tls_servername = "' + OLD_HOST + '"',
        'leader_tls_servername = "' + NEW_HOST + '"\n'
        '    leader_ca_cert_file = "/openbao/userconfig/'
        + BACKEND_OBJECT_NAME
        + '/ca.crt"',
    )
    config["data"]["extraconfig-from-values.hcl"] = hcl
    patch("configmap", "openbao-config", "openbao", {"data": config["data"]})
    sts = get("statefulset", "openbao", "openbao")
    if sts["spec"]["updateStrategy"]["type"] != "OnDelete":
        raise RuntimeError("Refusing template change with automatic rollout strategy")
    env = sts["spec"]["template"]["spec"]["containers"][0]["env"]
    env = [x for x in env if x["name"] != "BAO_CACERT"]
    env.append(
        {
            "name": "BAO_CACERT",
            "value": "/openbao/userconfig/" + BACKEND_OBJECT_NAME + "/ca.crt",
        }
    )
    # Strategic patch touches one container's env only; no Pod is deleted.
    kube(
        "patch",
        "statefulset",
        "openbao",
        "-n",
        "openbao",
        "--type=strategic",
        "-p",
        json.dumps(
            {
                "spec": {
                    "template": {
                        "spec": {"containers": [{"name": "openbao", "env": env}]}
                    }
                }
            }
        ),
    )
    print(
        "Stores migrated to internal DNS; future restart trust configured; no Pod restart requested"
    )


def rollback(state):
    """Restore old server TLS first, retaining dual client trust until verified."""
    baseline = json.loads((state / "baseline.json").read_text())
    # Keep dual client trust until the OLD certificate is back on every listener.
    original = next(x for x in baseline["objects"] if x["kind"] == "Certificate")
    kube(
        "patch",
        "certificate",
        BACKEND_OBJECT_NAME,
        "-n",
        "openbao",
        "--type=json",
        "-p",
        json.dumps([{"op": "replace", "path": "/spec", "value": original["spec"]}]),
    )
    identity = "/home/shaman007/.config/talos-backup/age-key.txt"
    old = json.loads(
        run(["age", "-d", "-i", identity, str(state / "old-backend-tls.json.age")])
    )[0]
    # Feed sensitive JSON patch through stdin, never process arguments.
    # kubectl --patch-file=/dev/stdin keeps restored key material in memory only.
    kube(
        "patch",
        "secret",
        BACKEND_OBJECT_NAME,
        "-n",
        "openbao",
        "--type=json",
        "--patch-file=/dev/stdin",
        payload=json.dumps(
            [
                {"op": "replace", "path": "/data", "value": old["data"]},
                {
                    "op": "add",
                    "path": "/metadata/annotations",
                    "value": old["metadata"].get("annotations", {}),
                },
            ]
        ).encode(),
    )
    print(
        "Old certificate restored; verify hot reload on every Pod BEFORE restoring clients/configs"
    )


def restore_clients(state):
    """Restore clients and reconciliation only after old TLS is live everywhere."""
    # This stage is ONLY for rollback after the old certificate is live again.
    identity = "/home/shaman007/.config/talos-backup/age-key.txt"
    old = json.loads(
        run(["age", "-d", "-i", identity, str(state / "old-backend-tls.json.age")])
    )[0]
    certificate = base64.b64decode(old["data"]["tls.crt"]).decode()
    first_certificate = certificate.split("-----END CERTIFICATE-----", 1)[0]
    first_certificate += "-----END CERTIFICATE-----\n"
    fingerprint = hashlib.sha256(
        ssl.PEM_cert_to_DER_cert(first_certificate)
    ).hexdigest()
    probe(state / "dual-trust.pem", OLD_HOST, fingerprint)
    baseline = json.loads((state / "baseline.json").read_text())
    for obj in baseline["objects"]:
        kind, name, ns = (
            obj["kind"],
            obj["metadata"]["name"],
            obj["metadata"].get("namespace"),
        )
        if kind in ("SecretStore", "ClusterSecretStore"):
            kube(
                "patch",
                kind,
                name,
                *(["-n", ns] if ns else []),
                "--type=json",
                "-p",
                json.dumps(
                    [
                        {
                            "op": "replace",
                            "path": "/spec/provider/vault",
                            "value": obj["spec"]["provider"]["vault"],
                        }
                    ]
                ),
            )
        elif kind == "ConfigMap":
            patch(kind, name, ns, {"data": obj["data"]})
        elif kind == "ServersTransport":
            kube(
                "patch",
                kind,
                name,
                "-n",
                ns,
                "--type=json",
                "-p",
                json.dumps([{"op": "replace", "path": "/spec", "value": obj["spec"]}]),
            )
        elif kind == "Deployment":
            patch(kind, name, ns, {"spec": {"template": obj["spec"]["template"]}})
        elif kind == "StatefulSet":
            patch(kind, name, ns, {"spec": {"template": obj["spec"]["template"]}})
    # Restore child pauses before parent, and preserve their original annotation values.
    apps = [x for x in baseline["objects"] if x["kind"] == "Application"]
    for obj in sorted(
        apps, key=lambda x: x["metadata"]["name"] == "argocd-applications"
    ):
        value = (
            obj["metadata"]
            .get("annotations", {})
            .get("argocd.argoproj.io/skip-reconcile")
        )
        patch(
            "application",
            obj["metadata"]["name"],
            "argocd",
            {"metadata": {"annotations": {"argocd.argoproj.io/skip-reconcile": value}}},
        )
    print(
        "Original clients/configuration and Argo pauses restored; CA objects retained"
    )


def main():
    """Run one explicitly selected stage without implicit subsequent mutations."""
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "snapshot",
            "bootstrap",
            "backup-pki",
            "dual-trust",
            "switch",
            "migrate",
            "rollback",
            "restore-clients",
        ],
    )
    parser.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()
    functions = {
        "snapshot": snapshot,
        "bootstrap": bootstrap,
        "backup-pki": backup_pki,
        "dual-trust": dual_trust,
        "switch": switch,
        "migrate": migrate,
        "rollback": rollback,
        "restore-clients": restore_clients,
    }
    functions[args.stage](args.state_dir)


if __name__ == "__main__":
    main()
