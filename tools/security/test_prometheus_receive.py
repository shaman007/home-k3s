#!/usr/bin/env python3
"""Isolated exact-image Prometheus/Receive outage, auth-file and dedup fixture.

No Kubernetes access, production volumes, real tokens, or external container
network. Only own ephemeral containers/volumes are created and removed.
"""

import copy
import json
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.bootstrap import prepare_prometheus_receive as plan  # pylint: disable=wrong-import-position
from tools.security.probe_commands import run_command  # pylint: disable=wrong-import-position

PROM_IMAGE = plan.read(plan.PROM)["spec"]["template"]["spec"]["containers"][0]["image"]
THANOS_IMAGE = plan.receive_statefulset()["spec"]["template"]["spec"]["containers"][0][
    "image"
]
PYTHON_IMAGE = "docker.io/library/python:3.14-slim"
# This path is inside the disposable container, never a host temporary mount.
CONTAINER_TMPFS = "/tmp:rw,mode=1777"  # nosec B108

EXPORTER = """import base64,http.server,pathlib
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  expected=pathlib.Path('/fixture/expected-token').read_text().strip()
  auth=self.headers.get('Authorization','')
  valid=(self.path=='/metrics' or
         (self.path=='/bearer' and auth=='Bearer '+expected) or
         (self.path=='/basic' and auth=='Basic '+base64.b64encode(('prometheus:'+expected).encode()).decode()))
  self.send_response(200 if valid else 401)
  self.send_header('Content-Type','text/plain; version=0.0.4');self.end_headers()
  self.wfile.write(b'fixture_series 1\\n' if valid else b'denied\\n')
 def log_message(self,*args):pass
http.server.ThreadingHTTPServer(('127.0.0.1',18080),Handler).serve_forever()
"""


def native(args, check=True):
    """Use only bounded local CLI commands; capture fixture-only output."""
    result = run_command(args, capture_output=True, text=True, timeout=180)
    if check and result.returncode:
        raise RuntimeError("Fixture CLI failed: " + result.stderr[-1200:])
    return result


def until(probe, budget=90):
    """Bound every readiness/recovery observation."""
    end = time.monotonic() + budget
    while time.monotonic() < end:
        if probe():
            return
        time.sleep(1)
    raise RuntimeError("Fixture acceptance timed out")


class Fixture:
    """Own all temporary data, processes and no-uplink networking explicitly."""

    def __init__(self, work):
        self.work = work
        self.containers = []
        self.volumes = []
        self.anchor = None
        self.prom = None
        self.receive = None
        self.started = None

    def prepare(self):
        """Synthetic auth only; preserve actual optional scrape HTTP client settings."""
        self.work.chmod(0o755)
        (self.work / "exporter.py").write_text(EXPORTER)
        (self.work / "expected-token").write_text("fixture-token-one")
        for name in ["hister", "spotify", "meilisearch"]:
            (self.work / name).mkdir(mode=0o755)
        config = {
            "global": {
                "scrape_interval": "1s",
                "evaluation_interval": "1s",
                "external_labels": {"cluster": "prometheus"},
            },
            "rule_files": ["/fixture/rules.yml"],
            "scrape_configs": [
                {
                    "job_name": "fixture",
                    "static_configs": [{"targets": ["127.0.0.1:18080"]}],
                }
            ],
            "remote_write": [copy.deepcopy(plan.remote_write())],
        }
        config["remote_write"][0]["url"] = "http://127.0.0.1:19291/api/v1/receive"
        # A separate synthetic queue exercises the lazy dropped-sample CounterVec.
        config["remote_write"].append(
            {
                "name": "fixture-drop",
                "url": "http://127.0.0.1:19292/api/v1/receive",
                "queue_config": {
                    "min_shards": 1,
                    "max_shards": 1,
                    "capacity": 1000,
                    "max_samples_per_send": 100,
                    "sample_age_limit": "1ms",
                },
            }
        )
        original = yaml.safe_load(plan.read(plan.CONFIG)["data"]["prometheus.yaml"])
        for original_job in original["scrape_configs"]:
            if original_job["job_name"] not in ["hister", "spotify", "meilisearch"]:
                continue
            job = copy.deepcopy(original_job)
            job["scrape_interval"] = "1s"
            job["scrape_timeout"] = "1s"
            job["static_configs"] = [{"targets": ["127.0.0.1:18080"]}]
            job["metrics_path"] = (
                "/basic" if job["job_name"] == "spotify" else "/bearer"
            )
            config["scrape_configs"].append(job)
        (self.work / "prom.yml").write_text(yaml.safe_dump(config))
        (self.work / "rules.yml").write_text(
            yaml.safe_dump(
                {
                    "groups": [
                        {
                            "name": "fixture",
                            "rules": [
                                {
                                    "alert": "FixtureCoreAlert",
                                    "expr": 'up{job="fixture"} == 1',
                                    "for": "1s",
                                }
                            ],
                        }
                    ]
                }
            )
        )
        for file in self.work.iterdir():
            if file.is_file():
                file.chmod(0o644)

    def volume(self):
        """Allocate only fresh explicitly labelled fixture volumes."""
        value = native(
            [
                "podman",
                "volume",
                "create",
                "--label",
                "home-k3s.fixture=prometheus-receive",
            ]
        ).stdout.strip()
        self.volumes.append(value)
        return value

    def launch(self, image, args, *, user="65534:65534", mounts=()):
        """Start a hardened local process in the fixture's private network namespace."""
        cmd = [
            "podman",
            "run",
            "-d",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--label=home-k3s.fixture=prometheus-receive",
            "--read-only",
            "--user=" + user,
            "--tmpfs",
            CONTAINER_TMPFS,
            "--network=" + ("container:" + self.anchor if self.anchor else "none"),
            "-v",
            str(self.work) + ":/fixture:ro,z",
        ]
        for mount in mounts:
            cmd += ["-v", mount]
        cid = native([*cmd, image, *args]).stdout.strip()
        self.containers.append(cid)
        return cid

    def request(self, url):
        """Only fixed loopback fixture URLs are used; never production APIs."""
        code = (
            "import urllib.request,sys;"
            "print(urllib.request.urlopen(sys.argv[1],timeout=3).read().decode())"
        )
        result = native(
            ["podman", "exec", self.anchor, "python", "-c", code, url], False
        )
        return result.stdout if result.returncode == 0 else None

    def query(self, expression, port=19090, dedup=True):
        """Read a numeric result from the actual fixture HTTP query API."""
        params = urlencode({"query": expression, "dedup": str(dedup).lower()})
        data = self.request(f"http://127.0.0.1:{port}/api/v1/query?{params}")
        if data is None:
            return None
        result = json.loads(data)["data"]["result"]
        return float(result[0]["value"][1]) if result else None

    def auth_ready(self, value):
        """All optional auth jobs must reflect the actual last scrape outcome."""
        return all(
            self.query('up{job="' + n + '"}') == value
            for n in ["hister", "spotify", "meilisearch"]
        )

    def core_alert_fires(self):
        """Verify evaluation, not only the management health endpoint."""
        data = self.request("http://127.0.0.1:19090/api/v1/alerts")
        return bool(data) and any(
            a["state"] == "firing" for a in json.loads(data)["data"]["alerts"]
        )

    def boot(self):
        """Start Prometheus with Receive absent and three empty projected token dirs."""
        self.prepare()
        self.anchor = self.launch(PYTHON_IMAGE, ["python", "/fixture/exporter.py"])
        self.volume()
        mounts = [self.volumes[0] + ":/data:U,z"]
        mounts += [
            str(self.work / name) + ":/etc/prometheus-" + name + ":ro,z"
            for name in ["hister", "spotify", "meilisearch"]
        ]
        self.prom = self.launch(
            PROM_IMAGE,
            [
                "--config.file=/fixture/prom.yml",
                "--storage.tsdb.path=/data",
                "--web.listen-address=127.0.0.1:19090",
                "--storage.tsdb.min-block-duration=2h",
                "--storage.tsdb.max-block-duration=2h",
            ],
            mounts=mounts,
        )
        self.started = native(
            ["podman", "inspect", "--format", "{{.State.StartedAt}}", self.prom]
        ).stdout.strip()
        until(lambda: self.request("http://127.0.0.1:19090/-/ready") is not None)
        until(lambda: self.query('up{job="fixture"}') == 1 and self.auth_ready(0))
        until(self.core_alert_fires)
        metrics = self.request("http://127.0.0.1:19090/metrics")
        if not any(
            line.startswith(
                "prometheus_remote_storage_queue_highest_sent_timestamp_seconds{"
            )
            and 'remote_name="thanos-receive"' in line
            for line in metrics.splitlines()
        ):
            raise AssertionError("Queue metric labels unavailable")
        # CounterVec emits no family at zero; deliberately drop only fixture data.
        until(
            lambda: any(
                line.startswith("prometheus_remote_storage_samples_dropped_total{")
                and 'remote_name="fixture-drop"' in line
                for line in (
                    self.request("http://127.0.0.1:19090/metrics") or ""
                ).splitlines()
            )
        )
        print(
            "PASS Prometheus boot/scrapes/rules with Receiver and all three credentials absent",
            flush=True,
        )

    def auth_rotation(self):
        """Credentials appear and rotate; require a new scrape rather than cached up=1."""
        for name in ["hister", "spotify", "meilisearch"]:
            (self.work / name / "token").write_text("fixture-token-one")
        until(lambda: self.auth_ready(1))
        rotated = time.time()
        (self.work / "expected-token").write_text("fixture-token-two")
        for name in ["hister", "spotify", "meilisearch"]:
            (self.work / name / "token").write_text("fixture-token-two")
        until(
            lambda: (
                self.auth_ready(1)
                and all(
                    (self.query('timestamp(up{job="' + n + '"})') or 0) > rotated
                    for n in ["hister", "spotify", "meilisearch"]
                )
            )
        )
        print(
            "PASS optional bearer/basic files appear and rotate without process restart",
            flush=True,
        )

    def start_thanos(self):
        """Use independent Receive storage and a read-only historical sidecar fixture."""
        args = plan.receive_statefulset()["spec"]["template"]["spec"]["containers"][0][
            "args"
        ]
        args = [
            a.replace("$(POD_NAME)", "receive-fixture")
            for a in args
            if not a.startswith("--objstore.")
        ]
        self.receive = self.launch(
            THANOS_IMAGE, args, user="1001:1001", mounts=[self.volume() + ":/data:U,z"]
        )
        until(lambda: self.request("http://127.0.0.1:10902/-/ready") is not None)
        self.launch(
            THANOS_IMAGE,
            [
                "sidecar",
                "--tsdb.path=/data",
                "--prometheus.url=http://127.0.0.1:19090",
                "--grpc-address=127.0.0.1:19091",
                "--http-address=127.0.0.1:19094",
            ],
            mounts=[self.volumes[0] + ":/data:ro,z"],
        )
        self.launch(
            THANOS_IMAGE,
            [
                "query",
                "--http-address=127.0.0.1:19092",
                "--grpc-address=127.0.0.1:19093",
                "--endpoint=127.0.0.1:10901",
                "--endpoint=127.0.0.1:19091",
                "--query.replica-label=replica",
            ],
        )
        until(
            lambda: (
                self.query('count(fixture_series{job="fixture"})', 19092, False) == 2
            )
        )
        until(lambda: self.query('count(fixture_series{job="fixture"})', 19092) == 1)
        print(
            "PASS real remote_write, tenant/cluster preservation and sidecar/Receive dedup",
            flush=True,
        )

    def outage(self):
        """Receiver and credential loss must leave fresh scrapes and rule evaluation alive."""
        before = self.query('timestamp(fixture_series{job="fixture"})')
        native(["podman", "stop", "--time=5", self.receive])
        until(
            lambda: (
                (self.query('timestamp(fixture_series{job="fixture"})') or 0) > before
            )
        )
        if (
            self.request("http://127.0.0.1:19090/-/ready") is None
            or not self.core_alert_fires()
        ):
            raise AssertionError("Receiver outage affected Prometheus readiness/rules")
        (self.work / "hister" / "token").unlink()
        until(lambda: self.query('up{job="hister"}') == 0)
        native(["podman", "start", self.receive])
        until(
            lambda: (
                (
                    self.query(
                        'timestamp(fixture_series{job="fixture",replica="receive-fixture"})',
                        19092,
                        False,
                    )
                    or 0
                )
                > before
            )
        )
        started = native(
            ["podman", "inspect", "--format", "{{.State.StartedAt}}", self.prom]
        ).stdout.strip()
        if started != self.started:
            raise AssertionError("Prometheus process restarted")
        print(
            "PASS Receive outage/recovery and token disappearance leave Prometheus running",
            flush=True,
        )

    def cleanup(self):
        """Delete only container IDs/volume names created by this fixture instance."""
        for cid in reversed(self.containers):
            native(["podman", "rm", "-f", cid], False)
        for value in self.volumes:
            native(["podman", "volume", "rm", value])


def main():
    """Run the full isolated fault matrix and always clean up owned artifacts."""
    with tempfile.TemporaryDirectory(prefix="prometheus-receive-fixture-") as directory:
        fixture = Fixture(Path(directory))
        try:
            fixture.boot()
            fixture.auth_rotation()
            fixture.start_thanos()
            fixture.outage()
        finally:
            fixture.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
