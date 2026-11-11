#!/usr/bin/env python3
"""Exercise real Nginx images/configs with read-only fixture content and fake FastCGI.

No production application code/data, credentials, endpoints or published ports.
Set NGINX_GUARD_IMAGE to test a deployed immutable image reference.
Explicit writable cache/run tmpfs mounts represent the existing emptyDirs.
"""

from dataclasses import dataclass
from pathlib import Path
import json
import os
import tempfile
import time
import yaml

from probe_commands import run_command

ROOT = Path(__file__).resolve().parents[2]
MOCK = (
    "import json,socketserver,struct\ndef "
    "receive(s,n):\n    out=b''\n    while "
    "len(out)<n:\n        "
    "part=s.recv(n-len(out))\n        if not "
    "part: raise ConnectionError('Incomplete "
    "FastCGI record')\n        out+=part\n    "
    "return out\nclass "
    "Handler(socketserver.BaseRequestHandler)"
    ":\n    def handle(self):\n        total=0\n "
    "       while True:\n            "
    "version,kind,rid,length,padding,_=struct"
    ".unpack('!BBHHBB',receive(self.request,8"
    "))\n            "
    "receive(self.request,length+padding)\n    "
    "        if kind==5:\n                "
    "total+=length\n                if "
    "length==0: break\n        "
    "body=json.dumps({'fastcgi':True,'receive"
    "d_bytes':total}).encode()\n        "
    "payload=b'Content-Type: "
    "application/json\\r\\nCache-Control: "
    "private, no-store\\r\\n\\r\\n'+body\n        "
    "for kind,data in "
    "[(6,payload),(6,b''),(3,struct.pack('!IB"
    "3s',0,0,b'\\0\\0\\0'))]:\n            "
    "self.request.sendall(struct.pack('!BBHHB"
    "B',1,kind,rid,len(data),0,0)+data)\nclass "
    "Server(socketserver.ThreadingTCPServer):"
    "\n    allow_reuse_address=True\n    "
    "daemon_threads=True\nServer(('127.0.0.1',"
    "9000),Handler).serve_forever()\n"
)
REQUEST = """import http.client,json,sys
method,path,size=sys.argv[1],sys.argv[2],int(sys.argv[3])
c=http.client.HTTPConnection('127.0.0.1',8080,timeout=10)
c.request(method,path,body=b'G'*size if size else None)
r=c.getresponse();data=r.read()
print(json.dumps({'status':r.status,'headers':dict(r.getheaders()),'body':data.decode()}))
c.close()
"""


def run(args, timeout=90):
    """Run the probe command and fail when its expected execution does not succeed."""
    r = run_command(args, capture_output=True, text=True, timeout=timeout, check=False)
    if not r.returncode == 0:
        raise AssertionError(r.stdout[-2500:] + r.stderr[-2500:])
    return r.stdout.strip()


@dataclass(frozen=True)
class NginxTarget:
    """Describe the reviewed application configuration and its content mount."""

    name: str
    deployment_path: str
    config_path: str
    root: str
    nginx_name: str
    php_name: str


def load_configuration(target):
    """Check deployed manifest guards before preparing runtime fixtures."""
    pod = yaml.safe_load((ROOT / target.deployment_path).read_text())["spec"]["template"]["spec"]
    c = next(c for c in pod["containers"] if c["name"] == target.nginx_name)
    php = next(c for c in pod["containers"] if c["name"] == target.php_name)
    if (
        next((m for m in c["volumeMounts"] if m["mountPath"] == target.root))["readOnly"]
        is not True
    ):
        raise AssertionError
    if (
        next((m for m in php["volumeMounts"] if m["mountPath"] == target.root)).get(
            "readOnly", False
        )
        is not False
    ):
        raise AssertionError
    if c["securityContext"]["readOnlyRootFilesystem"] is not True:
        raise AssertionError
    if c["securityContext"]["allowPrivilegeEscalation"] is not False:
        raise AssertionError
    if not c["securityContext"]["capabilities"] == {"drop": ["ALL"]}:
        raise AssertionError
    if not pod["securityContext"]["runAsUser"] == pod["securityContext"]["runAsGroup"] == 33:
        raise AssertionError
    config = yaml.safe_load((ROOT / target.config_path).read_text())["data"]["config"]
    return c["image"], config


def prepare_fixtures(directory, config):
    """Create synthetic content, Nginx configuration and a fake FastCGI backend."""
    d = Path(directory)
    content = d / "content"
    content.mkdir()
    content.chmod(0o777)
    for file, body in {
        "index.php": "mock fixture",
        "remote.php": "mock fixture",
        "status.php": "mock fixture",
        "guard.css": "body {color:blue;}\n",
        "wp-content/uploads/guard.txt": "fixture media",
    }.items():
        target = content / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    cfg = d / "config"
    cfg.mkdir(mode=0o755)
    (cfg / "default.conf").write_text(config)
    mock = d / "mock.py"
    mock.write_text(MOCK)
    mock.chmod(0o644)
    return content, cfg, mock


def start_backend(mock):
    """Start the network-isolated backend with no capabilities or writable root."""
    backend = run(
        [
            "podman",
            "run",
            "-d",
            "--network=none",
            "--read-only",
            "--read-only-tmpfs=false",
            "--user=33:33",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "-v",
            str(mock) + ":/guard/mock.py:ro,Z",
            "harbor.andreybondarenko.com/dockerhub/python:3.13-slim",
            "python3",
            "-B",
            "/guard/mock.py",
        ]
    )
    return backend


def start_nginx(backend, content, cfg, target, image):
    """Start Nginx with read-only content and explicit cache and run tmpfs mounts."""
    nginx = run(
        [
            "podman",
            "run",
            "-d",
            "--network=container:" + backend,
            "--read-only",
            "--read-only-tmpfs=false",
            "--user=33:33",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "-v",
            str(content) + ":" + target.root + ":ro,Z",
            "-v",
            str(cfg) + ":/etc/nginx/conf.d:ro,Z",
            "--tmpfs",
            "/var/cache/nginx:rw,mode=1777",
            "--tmpfs",
            "/var/run:rw,mode=1777",
            os.environ.get("NGINX_GUARD_IMAGE", image),
        ]
    )
    return nginx


def request(backend, method, path, size=0):
    """Send a synthetic HTTP request inside the isolated backend network."""
    return json.loads(
        run(
            [
                "podman",
                "exec",
                backend,
                "python3",
                "-B",
                "-c",
                REQUEST,
                method,
                path,
                str(size),
            ]
        )
    )


def check_responses(name, backend):
    """Verify readiness, static content, FastCGI forwarding and large request bodies."""
    for _ in range(25):
        try:
            response = request(backend, "GET", "/guard.css")
            if response["status"] == 200:
                break
        except AssertionError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError(name + " did not become ready")
    if not response["body"] == "body {color:blue;}\n":
        raise AssertionError
    if name == "wordpress":
        if not request(backend, "GET", "/wp-content/uploads/guard.txt")["body"] == "fixture media":
            raise AssertionError
    for method, path, size in [
        ("GET", "/index.php", 0),
        ("POST", "/index.php", 2 * 1024 * 1024),
    ]:
        response = request(backend, method, path, size)
        if not response["status"] == 200:
            raise AssertionError(response)
        body = json.loads(response["body"])
        if not (body["fastcgi"] and body["received_bytes"] == size):
            raise AssertionError(body)
    if name == "nextcloud":
        response = request(backend, "PUT", "/remote.php/dav/guard", 2 * 1024 * 1024)
        if not (
            response["status"] == 200
            and json.loads(response["body"])["received_bytes"] == 2 * 1024 * 1024
        ):
            raise AssertionError


def check_runtime_guards(nginx, root):
    """Verify the read-only mount, blocked writes and process capability guards."""
    mountinfo = run(["podman", "exec", nginx, "cat", "/proc/1/mountinfo"])
    if not any(
        (
            p[4] == root and "ro" in p[5].split(",")
            for p in (s.split() for s in mountinfo.splitlines())
        )
    ):
        raise AssertionError
    run(
        [
            "podman",
            "exec",
            nginx,
            "/bin/sh",
            "-ec",
            'if touch "$1/blocked-write" 2>/dev/null; then exit 1; fi',
            "sh",
            root,
        ]
    )
    status = run(["podman", "exec", nginx, "cat", "/proc/1/status"])
    for expected in [
        "CapEff:\t0000000000000000",
        "CapBnd:\t0000000000000000",
        "NoNewPrivs:\t1",
        "Seccomp:\t2",
    ]:
        if expected not in status:
            raise AssertionError(status)


def check(target):
    """Probe the application with isolated fixtures and always remove its containers."""
    image, config = load_configuration(target)
    containers = []
    try:
        with tempfile.TemporaryDirectory(prefix="nginx-content-") as directory:
            content, cfg, mock = prepare_fixtures(directory, config)
            backend = start_backend(mock)
            containers.append(backend)
            nginx = start_nginx(backend, content, cfg, target, image)
            containers.append(nginx)
            check_responses(target.name, backend)
            check_runtime_guards(nginx, target.root)
            print(
                target.name
                + (
                    ": read-only content, static files, "
                    "FastCGI forwarding and 2MiB request "
                    "bodies passed"
                ),
                flush=True,
            )
    except Exception:
        for cid in containers:
            r = run_command(
                ["podman", "logs", "--tail=20", cid], capture_output=True, text=True, check=False
            )
            print((r.stdout + r.stderr)[-2500:])
        raise
    finally:
        for cid in reversed(containers):
            run(["podman", "rm", "-f", cid])


if __name__ == "__main__":
    check(
        NginxTarget(
            "nextcloud",
            "nextcloud/stateful-set-nextcloud-web.yaml",
            "nextcloud/config-map-nextcloud-config.yaml",
            "/nextcloud",
            "nextcloud-nginx",
            "php-nextcloud",
        )
    )
    check(
        NginxTarget(
            "wordpress",
            "wordpress/deployment-php.yaml",
            "wordpress/config-map-nginx-config.yaml",
            "/code",
            "nginx",
            "php",
        )
    )
