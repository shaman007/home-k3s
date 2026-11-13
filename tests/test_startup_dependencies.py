"""Validate the real startup graph and inactive Dawarich gate contracts."""

import importlib.util
import json
import os
import secrets
import shutil

# Only the reviewed test runner below may launch interpreters.
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/bootstrap/wait_dependencies.rb"
spec = importlib.util.spec_from_file_location(
    "startup_candidate", ROOT / "tools/bootstrap/prepare_startup_gate.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
inventory_spec = importlib.util.spec_from_file_location(
    "startup_inventory", ROOT / "tools/bootstrap/inventory_startup.py"
)
inventory = importlib.util.module_from_spec(inventory_spec)
inventory_spec.loader.exec_module(inventory)


def run_fixture(command, **kwargs):
    """Launch only trusted test interpreters with argument lists and no shell."""
    allowed = {Path(sys.executable).resolve(), Path("/usr/bin/ruby").resolve()}
    options = {"capture_output", "text", "check", "timeout", "env"}
    if (
        not command
        or Path(command[0]).resolve() not in allowed
        or set(kwargs) - options
    ):
        raise ValueError("Only fixed test interpreters without a shell are allowed")
    # All scripts/options are defined by these tests; paths use isolated fixtures.
    return subprocess.run(command, check=kwargs.pop("check", False), **kwargs)  # nosec B603


class StartupInventoryTests(unittest.TestCase):
    """Inventory structural dependencies without exporting secret-bearing content."""

    def test_fixture_runner_rejects_shell_and_interpreter_overrides(self):
        """The reviewed subprocess boundary cannot invoke an unapproved executable."""
        for command, options in (
            (["/bin/sh", "-c", "exit 0"], {}),
            ([sys.executable, "--version"], {"shell": True}),
            ([sys.executable, "--version"], {"executable": "/bin/sh"}),
        ):
            with patch.object(subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    run_fixture(command, **options)
                run.assert_not_called()

    def test_references_and_service_hints_never_export_raw_values(self):
        """Resolve a literal database host while keeping opaque references opaque."""
        workload = {
            "kind": "Deployment",
            "metadata": {
                "name": "app",
                "namespace": "pilot",
                "annotations": {"private": "PRIVATE_MARKER"},
            },
            "spec": {
                "template": {
                    "metadata": {"labels": {"app": "app"}},
                    "spec": {
                        "containers": [
                            {
                                "name": "app",
                                "image": "registry.invalid/app:v1",
                                "command": ["PRIVATE_MARKER"],
                                "env": [
                                    {
                                        "name": "DATABASE_URL",
                                        "value": (
                                            "postgres://user:PRIVATE_MARKER@db.pilot.svc/db"
                                            "?token=PRIVATE_MARKER"
                                        ),
                                    },
                                    {"name": "PASSWORD", "value": "PRIVATE_MARKER"},
                                    {
                                        "name": "PASSWORD_REF",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": "db-credentials",
                                                "key": "password",
                                            }
                                        },
                                    },
                                ],
                                "envFrom": [
                                    {"configMapRef": {"name": "app-config"}},
                                    {
                                        "secretRef": {
                                            "name": "optional-secret",
                                            "optional": True,
                                        }
                                    },
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "data",
                                "persistentVolumeClaim": {"claimName": "data"},
                            },
                            {
                                "name": "projected",
                                "projected": {"sources": [{"secret": {"name": "tls"}}]},
                            },
                        ],
                    },
                }
            },
        }
        provider = {
            "kind": "StatefulSet",
            "metadata": {"name": "db", "namespace": "pilot"},
            "spec": {
                "template": {
                    "metadata": {"labels": {"app": "db"}},
                    "spec": {
                        "containers": [
                            {"name": "db", "image": "registry.invalid/db:v1"}
                        ]
                    },
                }
            },
        }
        service = {
            "kind": "Service",
            "metadata": {"name": "db", "namespace": "pilot"},
            "spec": {"selector": {"app": "db"}},
        }
        report = inventory.project({"items": [workload, provider, service]})
        self.assertEqual(report["workload_count"], 2)
        self.assertNotIn("PRIVATE_MARKER", json.dumps(report))
        row = next(row for row in report["workloads"] if row["name"] == "app")
        self.assertEqual(row["required_secrets"], ["db-credentials", "tls"])
        self.assertEqual(row["required_configmaps"], ["app-config"])
        self.assertEqual(row["required_pvcs"], ["data"])
        self.assertEqual(row["literal_host_hints"], ["db.pilot.svc"])
        self.assertEqual(row["service_hints"][0]["providers"], ["StatefulSet/db"])


class StartupGraphTests(unittest.TestCase):
    """Keep source evidence and conditional recovery edges explicit."""

    def test_graph_sources_and_normal_startup_are_valid(self):
        """Resolve evidence and distinguish normal DAG from the conditional recovery ring."""
        graph = yaml.safe_load((ROOT / "docs/startup/dependencies.yaml").read_text())
        nodes = graph["nodes"]
        for name, node in nodes.items():
            self.assertTrue(node["ready"], name)
            for source in node["sources"]:
                self.assertTrue((ROOT / source).exists(), source)
        for edge in graph["edges"]:
            self.assertIn(edge["from"], nodes)
            self.assertIn(edge["to"], nodes)
            self.assertTrue(edge["when"])

        def acyclic(edges):
            pending = set(nodes)
            while pending:
                roots = {
                    n
                    for n in pending
                    if not any(e["to"] == n and e["from"] in pending for e in edges)
                }
                if not roots:
                    return False
                pending -= roots
            return True

        normal = [
            e
            for e in graph["edges"]
            if e["kind"] not in {"recovery", "observed-image", "feature"}
        ]
        self.assertTrue(acyclic(normal))
        recovery = normal + [
            e for e in graph["edges"] if e["kind"] in {"recovery", "observed-image"}
        ]
        self.assertFalse(
            acyclic(recovery),
            "Observed unrolled-out SeaweedFS recovery ring must remain visible",
        )
        self.assertTrue(acyclic([e for e in recovery if e["kind"] != "observed-image"]))


class StartupCandidateTests(unittest.TestCase):
    """Keep preparation inactive and all existing workload behavior except explicit gates."""

    def test_candidate_orders_init_and_worker_without_changing_storage_or_migrations(
        self,
    ):
        """Only explicit gates and readiness may differ from production source."""
        original = yaml.safe_load(
            (ROOT / "dawarich/deployment-dawarich.yaml").read_text()
        )
        baseline = original["spec"]["template"]["spec"]
        baseline["initContainers"] = [
            c
            for c in baseline["initContainers"]
            if c["name"] != "wait-for-data-services"
        ]
        baseline["volumes"] = [
            v for v in baseline["volumes"] if v["name"] != "startup-gate"
        ]
        baseline["containers"][0].pop("readinessProbe", None)
        baseline["containers"][1]["command"] = ["sidekiq-entrypoint.sh"]
        baseline["containers"][1].pop("args", None)
        baseline["containers"][1]["volumeMounts"] = [
            v
            for v in baseline["containers"][1]["volumeMounts"]
            if v["name"] != "startup-gate"
        ]
        original["spec"]["template"]["metadata"].pop("annotations", None)
        config, result = m.candidate(original)
        pod = result["spec"]["template"]["spec"]
        before = original["spec"]["template"]["spec"]
        self.assertEqual(config["data"]["wait_dependencies.rb"], SCRIPT.read_text())
        gate = pod["initContainers"].pop()
        self.assertEqual(gate["name"], "wait-for-data-services")
        self.assertEqual(gate["image"], before["containers"][0]["image"])
        self.assertEqual(gate["command"][:3], ["bundle", "exec", "ruby"])
        self.assertEqual(gate["command"][-1], "dependencies")
        password = next(e for e in gate["env"] if e["name"] == "DATABASE_PASSWORD")
        self.assertEqual(
            password,
            next(
                e
                for e in before["containers"][0]["env"]
                if e["name"] == "DATABASE_PASSWORD"
            ),
        )
        self.assertFalse(gate["securityContext"]["allowPrivilegeEscalation"])
        self.assertTrue(gate["securityContext"]["readOnlyRootFilesystem"])
        self.assertNotIn("db:migrate", str(gate))
        web, worker = pod["containers"]
        self.assertEqual(web.pop("readinessProbe")["httpGet"]["path"], "/api/v1/ready")
        self.assertIn("wait_dependencies.rb web", worker["args"][0])
        self.assertTrue(worker.pop("args")[0].endswith("exec sidekiq-entrypoint.sh\n"))
        worker["command"] = before["containers"][1]["command"]
        worker["volumeMounts"].pop()
        pod["volumes"].pop()
        result["spec"]["template"]["metadata"].pop("annotations")
        self.assertEqual(original, result)

    def test_active_source_is_idempotent_and_matches_script(self):
        """Publishing the source must activate exactly one reproducible gate."""
        config, deployment = m.candidate()
        self.assertEqual(
            yaml.safe_load(
                (ROOT / "dawarich/config-map-startup-gate.yaml").read_text()
            ),
            config,
        )
        self.assertEqual(
            yaml.safe_load((ROOT / "dawarich/deployment-dawarich.yaml").read_text()),
            deployment,
        )
        self.assertEqual(m.candidate(deployment), [config, deployment])

    def test_generator_writes_only_an_inactive_new_file(self):
        """Reject GitOps-tree destinations and never overwrite an existing candidate."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.yaml"
            command = [
                sys.executable,
                str(ROOT / "tools/bootstrap/prepare_startup_gate.py"),
                "--output",
                str(output),
            ]
            result = run_fixture(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            docs = list(yaml.safe_load_all(output.read_text()))
            self.assertEqual([d["kind"] for d in docs], ["ConfigMap", "Deployment"])
            existing = output.read_bytes()
            self.assertNotEqual(
                run_fixture(command, capture_output=True, check=False).returncode,
                0,
            )
            self.assertEqual(output.read_bytes(), existing)
            command[-1] = str(ROOT / "dawarich/not-a-real-gate.yaml")
            self.assertNotEqual(
                run_fixture(command, capture_output=True, check=False).returncode,
                0,
            )
            self.assertFalse(Path(command[-1]).exists())


@unittest.skipUnless(shutil.which("ruby"), "Ruby required for gate behavior tests")
class StartupGateBehaviorTests(unittest.TestCase):
    """Exercise driver failures, deadline behavior and logging in the Ruby gate."""

    def run_gate(self, mode="dependencies", extra=None):
        """Run isolated Ruby with protocol doubles and collect sanitized stage events."""
        pg = r"""
module PG
  class Connection
    def exec(query)
      raise 'PRIVATE_BAD_SQL' unless query == 'SELECT 1'
      raise 'PRIVATE_DB_FAILURE' if ENV['TEST_DB'] == 'fail'
      sleep 1 if ENV['TEST_DB'] == 'hang'
      $db_calls = ($db_calls || 0) + 1
      raise 'PRIVATE_DB_CHANGED' if ENV['TEST_DB'] == 'flip' && $db_calls > 1
      self
    end
    def getvalue(*); ENV['TEST_DB'] == 'wrong' ? '0' : '1'; end
    def close; File.open(ENV.fetch('TEST_TRACE'), 'a') { |f| f.puts 'postgres-close' }; end
  end
  def self.connect(**options)
    raise 'PRIVATE_AUTH_PASSWORD' if ENV['TEST_AUTH'] == 'fail'
    raise 'PRIVATE_BAD_OPTIONS' unless options[:password] == ENV.fetch('TEST_EXPECTED_PASSWORD') && options[:options].include?('default_transaction_read_only=on')
    Connection.new
  end
end
"""
        redis = r"""
class Redis
  def initialize(**options)
    raise 'PRIVATE_BAD_OPTIONS' unless options[:reconnect_attempts] == 0
  end
  def ping
    $redis_calls = ($redis_calls || 0) + 1
    raise 'PRIVATE_CACHE_FAILURE' if ENV['TEST_CACHE'] == 'fail' || (ENV['TEST_CACHE'] == 'recover' && $redis_calls == 1)
    ENV['TEST_CACHE'] == 'wrong' ? 'OK' : 'PONG'
  end
  def close; File.open(ENV.fetch('TEST_TRACE'), 'a') { |f| f.puts 'valkey-close' }; end
end
"""
        web = r"""
class FakeHTTP
  attr_accessor :open_timeout, :read_timeout
  def request(request)
    raise 'PRIVATE_BAD_REQUEST' unless request.path == '/api/v1/ready' && request['Host'] == 'localhost'
    Struct.new(:code, :body).new(ENV.fetch('TEST_HTTP', '200'), ENV.fetch('TEST_BODY', '{"status":"ok"}'))
  end
end
module Net
  class HTTP
    def self.new(host, port, proxy)
      raise 'PRIVATE_BAD_ENDPOINT' unless host == '127.0.0.1' && port == 3000 && proxy.nil?
      FakeHTTP.new
    end
  end
end
"""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "pg.rb").write_text(pg)
            (folder / "redis.rb").write_text(redis)
            trace = folder / "trace"
            fixture_password = secrets.token_urlsafe(16)
            env = {
                **os.environ,
                "RUBYLIB": directory,
                "TEST_TRACE": str(trace),
                "DATABASE_HOST": "fixture",
                "DATABASE_PORT": "5432",
                "DATABASE_USERNAME": "fixture",
                "DATABASE_PASSWORD": fixture_password,
                "TEST_EXPECTED_PASSWORD": fixture_password,
                "DATABASE_NAME": "fixture",
                "REDIS_URL": "redis://fixture",
            }
            env.update(extra or {})
            code = f"require {json.dumps(str(SCRIPT))};\n" + web
            code += (
                f"\nexit StartupGate.wait({json.dumps(mode)}, "
                "budget: 0.08, interval: 0.005, attempt_timeout: 0.01)"
            )
            result = run_fixture(
                ["/usr/bin/ruby", "-e", code],
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertNotIn("PRIVATE", result.stdout + result.stderr)
            self.assertNotIn(fixture_password, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "")
            events = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertTrue(events)
            for event in events:
                self.assertEqual(
                    set(event), {"event", "stage", "result", "duration_seconds"}
                )
            return (
                result.returncode,
                events,
                trace.read_text() if trace.exists() else "",
            )

    def test_sql_and_ping_success_close_both_connections(self):
        """Successful SQL and PING must close both driver connections."""
        status, events, trace = self.run_gate()
        self.assertEqual(status, 0)
        self.assertEqual([e["stage"] for e in events], ["postgres", "valkey"])
        self.assertEqual(trace.splitlines(), ["postgres-close", "valkey-close"])

    def test_failures_wrong_protocol_results_and_timeout_block_startup(self):
        """Failures and misleading replies cannot release dependent processes."""
        for env in (
            {"TEST_AUTH": "fail"},
            {"TEST_DB": "fail"},
            {"TEST_DB": "wrong"},
            {"TEST_DB": "hang"},
            {"TEST_CACHE": "fail"},
            {"TEST_CACHE": "wrong"},
        ):
            with self.subTest(env=env):
                status, events, _ = self.run_gate(extra=env)
                self.assertEqual(status, 1)
                self.assertTrue(any(e["result"] == "not_ready" for e in events))

    def test_recovery_requires_both_checks_in_the_same_iteration(self):
        """Previously ready checks must not mask a subsequent provider failure."""
        status, _, _ = self.run_gate(extra={"TEST_CACHE": "recover"})
        self.assertEqual(status, 0)
        status, _, _ = self.run_gate(extra={"TEST_DB": "flip", "TEST_CACHE": "recover"})
        self.assertEqual(status, 1)

    def test_worker_waits_for_actual_ready_not_redirect_or_invalid_body(self):
        """Only the local ready response may release the worker entrypoint."""
        self.assertEqual(self.run_gate("web")[0], 0)
        for env in (
            {"TEST_HTTP": "503"},
            {"TEST_HTTP": "302"},
            {"TEST_BODY": "PRIVATE_invalid_json"},
            {"TEST_BODY": '{"status":"unavailable"}'},
        ):
            with self.subTest(env=env):
                self.assertEqual(self.run_gate("web", env)[0], 1)


if __name__ == "__main__":
    unittest.main()
