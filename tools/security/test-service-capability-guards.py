#!/usr/bin/env python3
"""Exercise Unbound DNS and uninitialized OpenBao Raft on disposable storage.

Uses rootless Podman with no production mounts, credentials or published ports.
"""

from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]


def smoke(image, user, caps, script, extra=()):
    command = [
        "podman",
        "run",
        "--rm",
        "--network=none",
        "--user",
        user,
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
    ]
    command += ["--cap-add=" + cap for cap in caps]
    command += list(extra)
    command += ["--entrypoint", "/bin/sh", image, "-ec", script]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if not (result.returncode == 0):
        raise AssertionError(result.stdout[-3000:] + result.stderr[-3000:])
    expected = "0000000000000400" if caps else "0000000000000000"
    for field in ["CapEff", "CapBnd"]:
        if not (field + ":\t" + expected in result.stdout):
            raise AssertionError(result.stdout)
    for expected in ["NoNewPrivs:\t1", "Seccomp:\t2"]:
        if not (expected in result.stdout):
            raise AssertionError(result.stdout)


def main():
    deployment = yaml.safe_load((ROOT / "mail/deployment-unbound.yaml").read_text())
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    sc = container["securityContext"]
    if not (sc["capabilities"] == {"drop": ["ALL"], "add": ["NET_BIND_SERVICE"]}):
        raise AssertionError
    if not (sc["readOnlyRootFilesystem"] and sc["allowPrivilegeEscalation"] is False):
        raise AssertionError
    config = yaml.safe_load((ROOT / "mail/config-map-unbound.yaml").read_text())["data"][
        "unbound.conf"
    ]
    # Keep the actual resolver config; add one deterministic local answer.
    config = config.replace(
        "server:\n",
        'server:\n  local-zone: "guard.invalid." static\n'
        '  local-data: "guard.invalid. 60 IN A 192.0.2.123"\n',
        1,
    )
    script = "cat > /tmp/unbound.conf <<'CONFIG'\n" + config + "\nCONFIG\n"
    if not (container["command"] == ["/opt/unbound/sbin/unbound"]):
        raise AssertionError
    if not (container["args"] == ["-d", "-c", "/opt/unbound/etc/unbound/unbound.conf"]):
        raise AssertionError
    script += """/opt/unbound/sbin/unbound -d -c /tmp/unbound.conf >/tmp/unbound.log 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true' EXIT
for attempt in 1 2 3 4 5; do
  if drill @127.0.0.1 guard.invalid A | grep -q '192.0.2.123'; then break; fi
  sleep 1
done
drill @127.0.0.1 guard.invalid A | grep -q '192.0.2.123'
drill -t @127.0.0.1 guard.invalid A | grep -q '192.0.2.123'
grep -E '^(CapEff|CapBnd|NoNewPrivs|Seccomp):' /proc/$server/status
"""
    smoke(
        container["image"],
        "0:0",
        ["NET_BIND_SERVICE"],
        script,
        ["--read-only", "--tmpfs", "/tmp:rw,mode=1777"],
    )
    print("Unbound: UDP/TCP DNS passed; read-only root, only NET_BIND_SERVICE")

    app = yaml.safe_load((ROOT / "argocd/application-openbao.yaml").read_text())
    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    if not (
        values["server"]["statefulSet"]["securityContext"]["container"]
        == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
        }
    ):
        raise AssertionError
    script = """cat > /tmp/raft.hcl <<'CONFIG'
listener "tcp" {
  address = "127.0.0.1:8200"
  tls_disable = true
}
storage "raft" {
  path = "/openbao/data"
  node_id = "guard-smoke"
}
api_addr = "http://127.0.0.1:8200"
cluster_addr = "https://127.0.0.1:8201"
CONFIG
/usr/local/bin/docker-entrypoint.sh bao server -config=/tmp/raft.hcl >/tmp/bao.log 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true' EXIT
for attempt in 1 2 3 4 5; do
  # Uninitialized Raft is expected to return HTTP 501; inspect the JSON body.
  wget -q -O /tmp/health 'http://127.0.0.1:8200/v1/sys/health?uninitcode=200' || true
  if grep -q '"initialized":false' /tmp/health; then break; fi
  sleep 1
done
grep -q '"initialized":false' /tmp/health
grep -E '^(CapEff|CapBnd|NoNewPrivs|Seccomp):' /proc/$server/status
"""
    smoke(
        "quay.io/openbao/openbao:2.7.2",
        "100:1000",
        [],
        script,
        [
            "--env",
            "SKIP_CHOWN=true",
            "--tmpfs",
            "/tmp:rw,mode=1777",
            "--tmpfs",
            "/openbao/data:rw,mode=0777",
        ],
    )
    print("OpenBao 2.7.2: uninitialized Raft health passed; zero capabilities")


if __name__ == "__main__":
    main()
