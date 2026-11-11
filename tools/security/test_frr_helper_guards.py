#!/usr/bin/env python3
"""Real FRR VTY/reload/metrics on disposable files and an isolated network."""

from pathlib import Path
import tempfile
import time

from probe_commands import run_command

FRR = "quay.io/frrouting/frr:10.4.3"
HELPERS = "quay.io/metallb/frr-k8s:v0.0.25"


def run(*args, check=True):
    """Run the probe command and fail when its expected execution does not succeed."""
    p = run_command(["podman", *args], capture_output=True, text=True, timeout=90, check=False)
    if check:
        if not p.returncode == 0:
            raise AssertionError(p.stdout[-3000:] + p.stderr[-3000:])
    return p.stdout.strip() if check else p


def prepare_fixture(d):
    """Create disposable FRR configuration and reviewed owner-only daemon config."""
    d.chmod(0o755)
    for name in ["conf", "run", "reload", "bin"]:
        (d / name).mkdir(mode=0o777 if name != "bin" else 0o755)
    # Account for umask; production shared directories are mode 0777.
    for name in ["conf", "run", "reload"]:
        (d / name).chmod(0o777)
    config = d / "conf/frr.conf"
    config.write_text(
        (
            "frr defaults traditional\nhostname "
            "guardbase\nservice "
            "integrated-vtysh-config\nrouter bgp "
            "64512\n bgp router-id 192.0.2.1\n"
        )
    )
    config.chmod(0o600)
    (d / "conf/vtysh.conf").write_text("service integrated-vtysh-config\n")
    (d / "conf/vtysh.conf").chmod(0o644)
    p = run_command(
        ["podman", "unshare", "chown", "100:101", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )
    if not p.returncode == 0:
        raise AssertionError(p.stderr)
    return config


def copy_helpers(d, containers):
    """Copy the actual helper binaries while retaining cleanup ownership of the image fixture."""
    image = run("create", "--network=none", "--entrypoint=sh", HELPERS, "-c", "true")
    containers.append(image)
    for name in ["frr-metrics", "frr-status", "frr-reloader.sh"]:
        run("cp", image + ":/" + name, str(d / "bin" / name))
        (d / "bin" / name).chmod(0o755)
    run("rm", image)
    containers.remove(image)


def start_daemon(mounts):
    """Start the UID-100 FRR daemon with no capabilities, routes or BGP listener."""
    daemon = run(
        "run",
        "-d",
        "--network=none",
        "--user=100:102",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        *mounts,
        "--entrypoint=/usr/lib/frr/bgpd",
        FRR,
        "-S",
        "-Z",
        "-p",
        "0",
        "-P",
        "0",
        "-f",
        "/etc/frr/frr.conf",
        "-i",
        "/var/run/frr/bgpd.pid",
        "--log",
        "stdout",
    )
    return daemon


def check_daemon(daemon):
    """Require actual VTY readiness, BGP queries and the expected socket ownership/mode."""
    for _ in range(30):
        p = run("exec", daemon, "/usr/bin/vtysh", "-c", "show running-config", check=False)
        if p.returncode == 0 and "guardbase" in p.stdout:
            break
        if run("inspect", "--format={{.State.Running}}", daemon) != "true":
            raise AssertionError(run("logs", daemon))
        time.sleep(0.2)
    else:
        raise AssertionError(run("logs", daemon))
    # Production helpers use vtysh to query these daemon sockets.
    data = run("exec", daemon, "/usr/bin/vtysh", "-c", "show bgp vrf all json")
    if "default" not in data:
        raise AssertionError(data)
    info = run(
        "exec",
        daemon,
        "sh",
        "-ec",
        'stat -c "%u:%g %a" /var/run/frr/bgpd.vty; cat /proc/1/status',
    )
    if "100:102 770" not in info:
        raise AssertionError(info)


def check_reload_commands(d, mounts, daemon):
    """Exercise real syntax/reload commands with only DAC_OVERRIDE and verify application."""
    # Root reloader retains only DAC_OVERRIDE to read owner-100 mode-0600 config.
    (d / "reload/frr.conf").write_text(
        (
            "frr defaults traditional\nhostname "
            "guardchanged\nservice "
            "integrated-vtysh-config\nrouter bgp "
            "64512\n bgp router-id 192.0.2.2\n"
        )
    )
    (d / "reload/frr.conf").chmod(0o644)
    command = [
        "run",
        "--rm",
        "--network=container:" + daemon,
        "--user=0:102",
        "--cap-drop=ALL",
        "--cap-add=DAC_OVERRIDE",
        "--security-opt=no-new-privileges",
        *mounts,
        "-v",
        str(d / "reload") + ":/etc/frr_reloader:z",
        "--entrypoint=sh",
        FRR,
        "-ec",
    ]
    # Real frr-reload.py performs syntax checking and vtysh command application.
    output = run(
        *command,
        (
            "python3 /usr/lib/frr/frr-reload.py "
            "--test --stdout "
            "/etc/frr_reloader/frr.conf; python3 "
            "/usr/lib/frr/frr-reload.py --reload "
            "--overwrite --stdout "
            "/etc/frr_reloader/frr.conf; cat "
            "/proc/self/status"
        ),
    )
    if not ("CapEff:\t0000000000000002" in output and "NoNewPrivs:\t1" in output):
        raise AssertionError(output)
    running = run("exec", daemon, "/usr/bin/vtysh", "-c", "show running-config")
    if "bgp router-id 192.0.2.2" not in running:
        raise AssertionError(output + "\n" + running)


def start_reloader(d, mounts, daemon):
    """Start the real reloader shell sharing only the reviewed daemon namespaces."""
    # Exercise the actual reloader shell, lock, signal and status path.
    reloader = run(
        "run",
        "-d",
        "--network=container:" + daemon,
        "--pid=container:" + daemon,
        "--user=0:102",
        "--cap-drop=ALL",
        "--cap-add=DAC_OVERRIDE",
        "--security-opt=no-new-privileges",
        *mounts,
        "-v",
        str(d / "reload") + ":/etc/frr_reloader:z",
        "-v",
        str(d / "bin") + ":/guard-bin:ro,z",
        "--entrypoint=/guard-bin/frr-reloader.sh",
        FRR,
    )
    return reloader


def check_reloader(d, config, mounts, daemon, reloader):
    """Verify permission denials, same-UID signalling, applied reload and minimal helper guards."""
    for _ in range(30):
        if (d / "reload/reloader.pid").exists():
            break
        time.sleep(0.2)
    else:
        raise AssertionError(run("logs", reloader))
    pid = int((d / "reload/reloader.pid").read_text())
    config.chmod(0o600)
    p = run_command(
        ["podman", "unshare", "chown", "100:101", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )
    if not p.returncode == 0:
        raise AssertionError(p.stderr)
    no_dac = run(
        "run",
        "--rm",
        "--network=none",
        "--user=0:102",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        *mounts,
        "--entrypoint=sh",
        FRR,
        "-ec",
        "head -c 1 /etc/frr/frr.conf",
        check=False,
    )
    if not (no_dac.returncode != 0 and "denied" in no_dac.stderr.lower()):
        raise AssertionError(no_dac.stdout + no_dac.stderr)
    no_kill = run("exec", "--user=0:0", daemon, "sh", "-c", "kill -0 1", check=False)
    if not no_kill.returncode != 0:
        raise AssertionError("Root without KILL unexpectedly signalled UID-100 daemon")
    (d / "reload/frr.conf").write_text(
        (
            "frr defaults traditional\nhostname "
            "guardchanged\nservice "
            "integrated-vtysh-config\nrouter bgp "
            "64512\n bgp router-id 192.0.2.3\n"
        )
    )
    # Same UID as production controller, with zero capabilities, can signal the reloader.
    run("exec", "--user=0:0", daemon, "sh", "-ec", "kill -HUP " + str(pid))
    for _ in range(50):
        statusfile = d / "reload/.status"
        if statusfile.exists() and "success" in statusfile.read_text():
            break
        time.sleep(0.2)
    else:
        raise AssertionError(run("logs", reloader))
    if "bgp router-id 192.0.2.3" not in run(
        "exec", daemon, "/usr/bin/vtysh", "-c", "show running-config"
    ):
        raise AssertionError
    helper_status = run("exec", "--user=0:0", reloader, "cat", "/proc/" + str(pid) + "/status")
    if not ("CapEff:\t0000000000000002" in helper_status and "NoNewPrivs:\t1" in helper_status):
        raise AssertionError(helper_status)


def prepare_exporter_fixture(d):
    """Generate fixture-only TLS material, service-account data and local API script path."""
    # Real exporters authenticate against a loopback-only Kubernetes fixture.
    tls = d / "tls"
    tls.mkdir(mode=0o755)
    credentials = d / "credentials"
    credentials.mkdir(mode=0o755)
    result = run_command(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:P-256",
            "-nodes",
            "-subj",
            "/CN=guard-fixture",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-days",
            "1",
            "-keyout",
            str(tls / "server.key"),
            "-out",
            str(tls / "server.crt"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if not result.returncode == 0:
        raise AssertionError(result.stderr)
    (tls / "server.key").chmod(0o600)
    (tls / "server.crt").chmod(0o644)
    (credentials / "ca.crt").write_bytes((tls / "server.crt").read_bytes())
    (credentials / "token").write_text("fixture-only")
    (credentials / "namespace").write_text("fixture")
    for file in credentials.iterdir():
        file.chmod(0o644)
    api_script = Path(__file__).with_name("frr_fixture_api.py")
    return tls, credentials, api_script


def check_metrics(daemon, metrics, probe):
    """Require authenticated HTTPS metrics and a running exporter with successful BGP queries."""
    for _ in range(30):
        p = run(
            "run",
            "--rm",
            "--network=container:" + daemon,
            "--user=65534:65534",
            "--cap-drop=ALL",
            "harbor.andreybondarenko.com/dockerhub/python:3.13-slim",
            "python3",
            "-c",
            probe,
            check=False,
        )
        if p.returncode == 0:
            break
        if run("inspect", "--format={{.State.Running}}", metrics) != "true":
            raise AssertionError(run("logs", metrics))
        time.sleep(0.2)
    else:
        raise AssertionError(p.stdout + p.stderr + run("logs", metrics))
    if "failed to fetch BGP neighbors" in run("logs", metrics):
        raise AssertionError


def check_status_exporter(status_exporter, api):
    """Require resource caches, authorization reviews and continued status-exporter readiness."""
    for _ in range(30):
        logs = run("logs", api)
        if "pod-read" in logs and "resource-read" in logs:
            break
        if run("inspect", "--format={{.State.Running}}", status_exporter) != "true":
            raise AssertionError(run("logs", status_exporter))
        time.sleep(0.2)
    else:
        raise AssertionError(run("logs", status_exporter))
    time.sleep(2)
    if not run("inspect", "--format={{.State.Running}}", status_exporter) == "true":
        raise AssertionError(run("logs", status_exporter))
    logs = run("logs", api)
    if not ("token-review" in logs and "access-review" in logs):
        raise AssertionError(logs)


def check_exporter_guards(exporters):
    """Require zero capability sets, no-new-privileges, seccomp and UID-100 on both exporters."""
    for cid in exporters:
        output = run("exec", cid, "cat", "/proc/1/status")
        for flag in [
            "CapEff:\t0000000000000000",
            "CapBnd:\t0000000000000000",
            "NoNewPrivs:\t1",
            "Seccomp:\t2",
        ]:
            if flag not in output:
                raise AssertionError(output)
        if not output.split("Uid:", 1)[1].splitlines()[0].split() == ["100"] * 4:
            raise AssertionError


def check_exporters(d, mounts, daemon, containers):
    """Start isolated API/metrics/status fixtures and verify their actual behavior and guards."""
    tls, credentials, api_script = prepare_exporter_fixture(d)
    api = run(
        "run",
        "-d",
        "--network=container:" + daemon,
        "--user=0:0",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "-v",
        str(tls) + ":/fixture:ro,z",
        "-v",
        str(api_script) + ":/api.py:ro,z",
        "harbor.andreybondarenko.com/dockerhub/python:3.13-slim",
        "python3",
        "-u",
        "/api.py",
    )
    containers.append(api)
    time.sleep(0.5)
    exporter_args = [
        "run",
        "-d",
        "--network=container:" + daemon,
        "--user=100:102",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        *mounts,
        "-v",
        str(credentials) + ":/var/run/secrets/kubernetes.io/serviceaccount:ro,z",
        "-v",
        str(d / "bin") + ":/guard-bin:ro,z",
        "-e",
        "KUBERNETES_SERVICE_HOST=127.0.0.1",
        "-e",
        "KUBERNETES_SERVICE_PORT=6443",
    ]
    metrics = run(
        *exporter_args,
        "--entrypoint=/guard-bin/frr-metrics",
        FRR,
        "--metrics-port=9141",
        "--metrics-bind-address=127.0.0.1",
    )
    containers.append(metrics)
    probe = (
        "import urllib.request,ssl; "
        "c=ssl._create_unverified_context();r=url"
        'lib.request.Request("https://127.0.0.1:9'
        '141/metrics",headers={"Authorization":"B'
        'earer fixture-only"});b=urllib.request.u'
        "rlopen(r,context=c,timeout=5).read();ass"
        'ert b"go_" in '
        'b;print("metrics-authenticated-200")'
    )
    check_metrics(daemon, metrics, probe)
    status_exporter = run(
        *exporter_args,
        "--entrypoint=/guard-bin/frr-status",
        FRR,
        "--node-name=guard-node",
        "--namespace=fixture",
        "--pod-name=guard-pod",
        "--poll-interval=1s",
        "--log-level=error",
    )
    containers.append(status_exporter)
    check_status_exporter(status_exporter, api)
    check_exporter_guards([metrics, status_exporter])


def main():
    """Real FRR VTY/reload/metrics on disposable files and an isolated network."""
    containers = []
    with tempfile.TemporaryDirectory(prefix="frr-helper-guards-") as directory:
        d = Path(directory)
        config = prepare_fixture(d)
        try:
            copy_helpers(d, containers)
            mounts = [
                "-v",
                str(d / "conf") + ":/etc/frr:z",
                "-v",
                str(d / "run") + ":/var/run/frr:z",
            ]
            daemon = start_daemon(mounts)
            containers.append(daemon)
            check_daemon(daemon)
            check_reload_commands(d, mounts, daemon)
            reloader = start_reloader(d, mounts, daemon)
            containers.append(reloader)
            check_reloader(d, config, mounts, daemon, reloader)
            check_exporters(d, mounts, daemon, containers)
            print(
                (
                    "PASS: real UID-100 VTY socket queries "
                    "and root DAC_OVERRIDE-only "
                    "syntax/reload; real SIGHUP/lock/status "
                    "success, authenticated HTTPS metrics and "
                    "status API caches; no kernel routes or "
                    "BGP listener"
                )
            )
        finally:
            for cid in reversed(containers):
                run("rm", "-f", cid)


if __name__ == "__main__":
    main()
