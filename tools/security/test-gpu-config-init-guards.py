#!/usr/bin/env python3
"""Real config-manager with mock node list/watch; no real API, devices or credentials."""

import json
from pathlib import Path
import subprocess
import tempfile
import time

IMAGE = "nvcr.io/nvidia/k8s-device-plugin:v0.20.1"
MOCK = "harbor.andreybondarenko.com/dockerhub/python:3.13-slim"
SERVER = (
    "\nfrom http.server import "
    "BaseHTTPRequestHandler,ThreadingHTTPServ"
    "er\nfrom urllib.parse import "
    "urlparse,parse_qs\nimport "
    "json,os,time\nlabel=os.environ['LABEL']\nn"
    "ode={'apiVersion':'v1','kind':'Node','me"
    "tadata':{'name':'guard-fixture','resourc"
    "eVersion':'1','labels':{'nvidia.com/devi"
    "ce-plugin.config':label}}}\nclass "
    "H(BaseHTTPRequestHandler):\n def "
    "do_GET(self):\n  "
    "path=urlparse(self.path);query=parse_qs("
    "path.query)\n  if "
    "path.path!='/api/v1/nodes':self.send_err"
    "or(404);return\n  "
    "print('node-read',flush=True)\n  "
    "self.send_response(200);self.send_header"
    "('Content-Type','application/json');self"
    ".end_headers()\n  try:\n   if "
    "query.get('watch')==['true']:\n    "
    "self.wfile.write((json.dumps({'type':'AD"
    "DED','object':node})+'\\n').encode());sel"
    "f.wfile.flush()\n    "
    "self.wfile.write((json.dumps({'type':'BO"
    "OKMARK','object':{'apiVersion':'v1','kin"
    "d':'Node','metadata':{'resourceVersion':"
    "'1','annotations':{'k8s.io/initial-event"
    "s-end':'true'}}}})+'\\n').encode());self."
    "wfile.flush();time.sleep(5)\n   "
    "else:self.wfile.write(json.dumps({'apiVe"
    "rsion':'v1','kind':'NodeList','metadata'"
    ":{'resourceVersion':'1'},'items':[node]}"
    ").encode())\n  except "
    "(BrokenPipeError,ConnectionResetError):p"
    "ass\n def log_message(self,*args):pass\nTh"
    "readingHTTPServer(('127.0.0.1',9500),H)."
    "serve_forever()\n"
)


def run(*args, check=True):
    """Run the probe command and fail when its expected execution does not succeed."""
    p = subprocess.run(["podman", *args], capture_output=True, text=True, timeout=90, check=False)
    if check:
        if not p.returncode == 0:
            raise AssertionError(p.stdout[-1500:] + p.stderr[-1500:])
    return p.stdout.strip() if check else p


def main():
    """Real config-manager with mock node list/watch; no real API, devices or credentials."""
    with tempfile.TemporaryDirectory(prefix="gpu-config-guard-") as directory:
        d = Path(directory)
        d.chmod(0o755)
        config = {
            "apiVersion": "v1",
            "kind": "Config",
            "clusters": [{"name": "fixture", "cluster": {"server": "http://127.0.0.1:9500"}}],
            "users": [{"name": "fixture", "user": {}}],
            "contexts": [{"name": "fixture", "context": {"cluster": "fixture", "user": "fixture"}}],
            "current-context": "fixture",
        }
        (d / "kubeconfig").write_text(json.dumps(config))
        (d / "kubeconfig").chmod(0o644)
        source = d / "source"
        source.mkdir(mode=0o755)
        (source / "default").write_text("version: v1\nflags:\n  migStrategy: none\n")
        (source / "default").chmod(0o644)
        for label, expected, user, default, mode in [
            ("default", "/available-configs/default", "1000:1000", "default", "0777"),
            ("", "/dev/null", "1000:1000", "", "0777"),
            ("default", None, "1000:1000", "default", "0755"),
        ]:
            mock = None
            try:
                mock = run(
                    "run",
                    "-d",
                    "--network=none",
                    "--user=65534:65534",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "-e",
                    "LABEL=" + label,
                    MOCK,
                    "python3",
                    "-u",
                    "-c",
                    SERVER,
                )
                time.sleep(0.5)
                script = "config-manager; readlink /config/config.yaml; cat /proc/self/status"
                args = [
                    "run",
                    "--rm",
                    "--network=container:" + mock,
                    "--user=" + user,
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--tmpfs=/config:mode=" + mode,
                    "-v",
                    str(source) + ":/available-configs:ro,Z",
                    "-v",
                    str(d / "kubeconfig") + ":/fixture-kubeconfig:ro,Z",
                ]
                for k, v in {
                    "KUBECONFIG": "/fixture-kubeconfig",
                    "NODE_NAME": "guard-fixture",
                    "NODE_LABEL": "nvidia.com/device-plugin.config",
                    "ONESHOT": "true",
                    "SEND_SIGNAL": "false",
                    "CONFIG_FILE_SRCDIR": "/available-configs",
                    "CONFIG_FILE_DST": "/config/config.yaml",
                    "DEFAULT_CONFIG": default,
                    "FALLBACK_STRATEGIES": "empty",
                }.items():
                    args += ["-e", k + "=" + v]
                p = run(*args, "--entrypoint=sh", IMAGE, "-ec", script, check=False)
                if expected is None:
                    if not (
                        p.returncode != 0 and "permission denied" in (p.stdout + p.stderr).lower()
                    ):
                        raise AssertionError(p.stdout + p.stderr)
                else:
                    if not (p.returncode == 0 and expected in p.stdout):
                        raise AssertionError(p.stdout + p.stderr)
                    for text in [
                        "CapEff:\t0000000000000000",
                        "CapBnd:\t0000000000000000",
                        "NoNewPrivs:\t1",
                        "Seccomp:\t2",
                    ]:
                        if not text in p.stdout:
                            raise AssertionError(p.stdout)
                # Oneshot may select its default before the informer makes a request.
                # The separate watch fixture below verifies real node list/watch.
            finally:
                if mock:
                    run("rm", "-f", mock)
        (source / "alternate").write_text("version: v1\n")
        (source / "alternate").chmod(0o644)
        mock = cid = None
        try:
            mock = run(
                "run",
                "-d",
                "--network=none",
                "--user=65534:65534",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "-e",
                "LABEL=alternate",
                MOCK,
                "python3",
                "-u",
                "-c",
                SERVER,
            )
            time.sleep(0.5)
            cid = run(
                "run",
                "-d",
                "--network=container:" + mock,
                "--user=1000:1000",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--tmpfs=/config:mode=0777",
                "-v",
                str(source) + ":/available-configs:ro,Z",
                "-v",
                str(d / "kubeconfig") + ":/fixture-kubeconfig:ro,Z",
                "-e",
                "KUBECONFIG=/fixture-kubeconfig",
                "-e",
                "NODE_NAME=guard-fixture",
                "-e",
                "ONESHOT=false",
                "-e",
                "SEND_SIGNAL=false",
                "-e",
                "CONFIG_FILE_SRCDIR=/available-configs",
                "-e",
                "CONFIG_FILE_DST=/config/config.yaml",
                "-e",
                "DEFAULT_CONFIG=default",
                "-e",
                "FALLBACK_STRATEGIES=empty",
                "--entrypoint=config-manager",
                IMAGE,
            )
            for _ in range(40):
                p = run("exec", cid, "readlink", "/config/config.yaml", check=False)
                if p.returncode == 0 and p.stdout.strip() == "/available-configs/alternate":
                    break
                time.sleep(0.25)
            else:
                raise AssertionError("Node watch did not select alternate config")
            p = run("logs", mock, check=False)
            if not "node-read" in p.stdout + p.stderr:
                raise AssertionError
            status = run("exec", cid, "cat", "/proc/1/status")
            for text in [
                "CapEff:\t0000000000000000",
                "CapBnd:\t0000000000000000",
                "NoNewPrivs:\t1",
                "Seccomp:\t2",
            ]:
                if not text in status:
                    raise AssertionError(status)
        finally:
            if cid:
                run("rm", "-f", cid)
            if mock:
                run("rm", "-f", mock)
        if not (source / "default").read_text().startswith("version: v1"):
            raise AssertionError
    print(
        (
            "PASS: UID-1000 one-shot/default/fallback "
            "and real node list/watch, zero "
            "capabilities, NNP/seccomp with live "
            "mode-0777 destination; mode-0755 "
            "boundary rejected as expected"
        )
    )


if __name__ == "__main__":
    main()
