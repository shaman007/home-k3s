"""Exercise inactive Mastodon startup/migration sequencing without Rails or live writes."""

import importlib.util
import json
import os
import secrets
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/bootstrap/mastodon_startup.rb"
SPEC = importlib.util.spec_from_file_location(
    "mastodon_native", ROOT / "tools/bootstrap/prepare_mastodon_native.py"
)
NATIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NATIVE)
CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "mastodon_contract", ROOT / "tools/ci/check_mastodon_native_contract.py"
)
CONTRACT = importlib.util.module_from_spec(CONTRACT_SPEC)
CONTRACT_SPEC.loader.exec_module(CONTRACT)

PG_FIXTURE = """module PG
  def self.connect(**options)
    raise 'PRIVATE_DRIVER_PASSWORD' if ENV['PG_FAIL'] == '1'
    $connections = ($connections || 0) + 1
    Connection.new
  end
  class Connection
    def exec(sql)
      ($queries ||= []) << sql
      if sql.include?('pg_try_advisory_lock')
        $locks = ($locks || 0) + 1
        return [{'acquired' => ENV['LOCK_BUSY'] == '1' ? 'f' : 't'}]
      elsif sql.include?('schema_migrations')
        sleep 30 if ENV['SCHEMA_HANG'] == '1'
        raise 'PRIVATE_CONNECTION' if ENV['NO_SCHEMA'] == '1'
        return ($versions || %w[100 200]).map { |v| {'version' => v} }
      end
      raise 'PRIVATE_CONNECTION' if ENV['HEARTBEAT_FAIL'] == '1'
      [{'ready' => '1'}]
    end
    def close
      $closed = ($closed || 0) + 1
    end
  end
end
"""
REDIS_FIXTURE = """class Redis
  def initialize(**options); end
  def ping
    ENV['REDIS_FAIL'] == '1' ? 'NOAUTH PRIVATE_PASSWORD' : 'PONG'
  end
  def close; end
end
"""


def ruby_fixture(code, environment=None, bundle=None):
    """Run reviewed Ruby code with isolated native-driver/command doubles, never a shell."""
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory)
        (fixture / "pg.rb").write_text(PG_FIXTURE)
        (fixture / "redis.rb").write_text(REDIS_FIXTURE)
        for folder, filename in [
            ("db/migrate", "100_initial.rb"),
            ("db/post_migrate", "200_after.rb"),
        ]:
            (fixture / folder).mkdir(parents=True)
            (fixture / folder / filename).write_text("# version fixture\n")
        if bundle:
            executable = fixture / "bundle"
            executable.write_text("#!/usr/bin/ruby\n" + bundle)
            executable.chmod(0o700)
        credential = "PRIVATE_" + secrets.token_hex(12)
        env = dict(
            os.environ,
            MASTODON_MIGRATION_OWNER="web-init",
            MASTODON_ALLOW_PENDING_MIGRATIONS="true",
            DB_HOST="db.invalid",
            DB_USER="fixture",
            DB_PASS=credential,
            DB_NAME="fixture",
            REDIS_HOST="redis.invalid",
            REDIS_PASSWORD=credential,
            PATH=directory + os.pathsep + os.environ["PATH"],
        )
        env.update(environment or {})
        harness = (
            """$stdout.sync=true
begin
  ok = begin
"""
            + code
            + """
  end
rescue StandardError, LoadError
  ok=false
end
child_alive=false
if $child_pid
  begin
    Process.kill(0,$child_pid)
    child_alive=true
  rescue Errno::ESRCH
    child_alive=false
  end
end
puts JSON.generate(test_result:ok,closed:($closed||0),connections:($connections||0),
                   queries:($queries||[]),spawned:($spawned||0),child_alive:child_alive)
"""
        )
        # Fixed interpreter and reviewed fixture code/paths; no executable or shell override.
        result = subprocess.run(  # nosec B603
            ["/usr/bin/ruby", "-I", directory, "-r", str(SCRIPT), "-e", harness],
            cwd=directory,
            env=env,
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        if result.returncode:
            raise AssertionError("Ruby fixture failed: " + result.stderr)
        return result, json.loads(result.stdout.splitlines()[-1])


class MastodonStartupRuntimeTests(unittest.TestCase):
    """Exercise failure/recovery and a real bounded native child, not production migrations."""

    def test_dependency_auth_and_redis_failures_are_sanitized(self):
        """Either datastore failure blocks startup without driver/credential output."""
        for env, expected in [
            ({}, True),
            ({"PG_FAIL": "1"}, False),
            ({"REDIS_FAIL": "1"}, False),
        ]:
            output, status = ruby_fixture(
                "MastodonStartup.wait('dependencies',budget:0.025,interval:0.001,"
                "attempt_timeout:0.01)",
                env,
            )
            self.assertEqual(status["test_result"], expected)
            self.assertNotIn("PRIVATE", output.stdout + output.stderr)

    def test_post_migrations_and_in_progress_writer_block_all_consumers(self):
        """Main migrations alone or a held writer lock cannot release schema gates."""
        for setup, env, expected in [
            ("", {}, True),
            ("$versions=%w[100];", {}, False),
            ("", {"LOCK_BUSY": "1"}, False),
            ("", {"NO_SCHEMA": "1"}, False),
        ]:
            result, status = ruby_fixture(
                setup + "MastodonStartup.wait('schema',budget:0.02,interval:0.001,"
                "attempt_timeout:0.01)",
                env,
            )
            self.assertEqual(status["test_result"], expected)
            self.assertEqual(status["closed"], status["connections"])
            self.assertTrue(
                any("pg_try_advisory_lock_shared" in q for q in status["queries"])
            )
            self.assertNotIn("PRIVATE", result.stdout + result.stderr)

    def test_only_owner_migrates_and_initialized_current_schema_is_noop(self):
        """Initial cutover on the same version performs no migration writes."""
        output, status = ruby_fixture("MastodonStartup.migrate")
        self.assertTrue(status["test_result"])
        self.assertIn("already_applied", output.stdout)
        self.assertEqual(status["spawned"], 0)
        _, denied = ruby_fixture(
            "MastodonStartup.migrate", {"MASTODON_MIGRATION_OWNER": "consumer"}
        )
        self.assertFalse(denied["test_result"])
        self.assertEqual(denied["connections"], 0)
        _, empty = ruby_fixture("$versions=[];MastodonStartup.migrate")
        self.assertFalse(empty["test_result"])
        self.assertEqual(empty["closed"], 1)
        _, denied_write = ruby_fixture(
            "$versions=%w[100];MastodonStartup.migrate",
            {"MASTODON_ALLOW_PENDING_MIGRATIONS": "false"},
        )
        self.assertFalse(denied_write["test_result"])
        self.assertEqual(denied_write["spawned"], 0)

    def test_migration_must_complete_all_expected_versions(self):
        """A zero exit alone cannot release consumers when post-migration IDs remain missing."""
        for completion, expected in [
            ("$versions << '200'", True),
            ("nil", False),
            ("raise 'PRIVATE_DRIVER_ERROR'", False),
        ]:
            setup = (
                "$versions=%w[100];def MastodonStartup.run_migration(connection,deadline);"
                "$spawned=1;" + completion + ";end;"
            )
            output, status = ruby_fixture(setup + "MastodonStartup.migrate")
            self.assertEqual(status["test_result"], expected)
            self.assertEqual(status["spawned"], 1)
            self.assertEqual(status["closed"], 1)
            self.assertNotIn("PRIVATE", output.stdout + output.stderr)

    def test_busy_migration_lock_never_spawns_second_writer(self):
        """Exclusive coordinator acquisition is bounded and fail closed."""
        _, status = ruby_fixture(
            "$versions=%w[100];MastodonStartup.migrate(budget:0.02,interval:0.001)",
            {"LOCK_BUSY": "1"},
        )
        self.assertFalse(status["test_result"])
        self.assertEqual(status["spawned"], 0)
        self.assertEqual(status["closed"], 1)

    def test_native_migration_failure_timeout_and_lost_lock_cleanup(self):
        """Real child failure/timeouts/session loss cannot leave a migration process running."""
        for child, environment in [
            ("warn 'PRIVATE_CHILD_PASSWORD';exit 1", {}),
            ("sleep 30", {}),
            ("sleep 30", {"HEARTBEAT_FAIL": "1"}),
        ]:
            output, status = ruby_fixture(
                "class << Process;alias original_spawn spawn;"
                "def spawn(*args,**options);$child_pid=original_spawn(*args,**options);end;end;"
                "$versions=%w[100];MastodonStartup.migrate(budget:0.05,interval:0.001)",
                environment,
                bundle=child,
            )
            self.assertFalse(status["test_result"])
            self.assertFalse(status["child_alive"])
            self.assertEqual(status["closed"], 1)
            self.assertNotIn("PRIVATE", output.stdout + output.stderr)

    def test_stalled_schema_query_is_bounded_and_closes_owner_session(self):
        """A broken transport cannot hold the coordinator indefinitely before spawning."""
        _, status = ruby_fixture("MastodonStartup.migrate", {"SCHEMA_HANG": "1"})
        self.assertFalse(status["test_result"])
        self.assertEqual(status["closed"], 1)
        self.assertEqual(status["spawned"], 0)

    def test_writer_uses_fixed_argv_and_full_migration_environment(self):
        """The native child receives no shell command or predeploy-only migration flag."""
        child = (
            "exit((ARGV == %w[exec rake db:migrate] && "
            "!ENV.key?('SKIP_POST_DEPLOYMENT_MIGRATIONS')) ? 0 : 2)"
        )
        _, status = ruby_fixture(
            "c=MastodonStartup.postgres;begin;"
            "MastodonStartup.run_migration(c,MastodonStartup.now+2);true;"
            "ensure;c.close;end",
            {"SKIP_POST_DEPLOYMENT_MIGRATIONS": "true"},
            bundle=child,
        )
        self.assertTrue(status["test_result"])


class MastodonNativeSourceTests(unittest.TestCase):
    """Keep native preparation inactive, scope credentials and preserve service contracts."""

    def test_active_argo_and_custom_owner_do_not_activate_candidate(self):
        """Ordinary publication of this package cannot replace the running Helm application."""
        app = yaml.safe_load((ROOT / "argocd/application-mastodon.yaml").read_text())
        self.assertEqual(app["spec"]["sources"][0]["chart"], "mastodon")
        self.assertEqual(app["spec"]["sources"][0]["targetRevision"], "1.2.8")
        custom = yaml.safe_load(
            (ROOT / "argocd/application-mastodon-custom.yaml").read_text()
        )
        self.assertFalse(custom["spec"]["source"]["directory"]["recurse"])
        self.assertNotIn("native", custom["spec"]["source"]["directory"]["include"])

    def test_source_is_current_and_only_web_has_migration_permission(self):
        """All roles share the desired schema image; only web contains a writer init."""
        documents = NATIVE.candidates()
        web_image = documents["deployment-mastodon-web.yaml"]["spec"]["template"][
            "spec"
        ]["containers"][0]["image"]
        for filename, expected in documents.items():
            self.assertEqual(
                yaml.safe_load((NATIVE.DIRECTORY / filename).read_text()), expected
            )
            self.assertNotIn(
                expected["kind"],
                {"Job", "Secret", "PersistentVolumeClaim", "Role", "RoleBinding"},
            )
            self.assertNotIn(
                "helm.sh/hook", expected["metadata"].get("annotations", {})
            )
            if expected["kind"] != "Deployment":
                continue
            pod = expected["spec"]["template"]["spec"]
            if filename != "deployment-mastodon-streaming.yaml":
                self.assertTrue(all(c["image"] == web_image for c in pod["containers"]))
            modes = [c["command"][-1] for c in pod["initContainers"]]
            self.assertEqual(
                modes,
                ["dependencies", "migrate", "schema"]
                if filename.endswith("-web.yaml")
                else ["dependencies", "schema"],
            )
            self.assertFalse(pod["automountServiceAccountToken"])
            for gate in pod["initContainers"]:
                self.assertEqual(gate["image"], web_image)
                self.assertFalse(gate["securityContext"]["allowPrivilegeEscalation"])
                self.assertEqual(
                    gate["securityContext"]["capabilities"]["drop"], ["ALL"]
                )
                for entry in gate["env"]:
                    if entry["name"] in NATIVE.ENV_NAMES:
                        self.assertIn("secretKeyRef", entry["valueFrom"])
                if gate["command"][-1] == "migrate":
                    env = {e["name"]: e for e in gate["env"]}
                    self.assertEqual(
                        env["MASTODON_PROMETHEUS_EXPORTER_ENABLED"]["value"], "false"
                    )
                    self.assertEqual(
                        env["MASTODON_ALLOW_PENDING_MIGRATIONS"]["value"], "false"
                    )
                if gate["command"][-1] != "migrate":
                    self.assertEqual({e["name"] for e in gate["env"]}, NATIVE.ENV_NAMES)

    def test_contract_checker_rejects_lost_integrations_or_service_selectors(self):
        """A startup gate must not hide unrelated env/queue/route changes."""
        documents = list(NATIVE.candidates().values())
        by_key = {(d["kind"], d["metadata"]["name"]): d for d in documents}
        baseline = {
            k: v
            for k, v in by_key.items()
            if k != ("ConfigMap", "mastodon-startup-gate")
        }
        self.assertEqual(CONTRACT.check(baseline, by_key), [])
        changed = json.loads(json.dumps(by_key[("ConfigMap", "mastodon-env")]))
        changed["data"]["S3_ENDPOINT"] = "https://wrong.invalid"
        bad = dict(by_key)
        bad[("ConfigMap", "mastodon-env")] = changed
        self.assertTrue(CONTRACT.check(baseline, bad))
        changed_service = json.loads(json.dumps(by_key[("Service", "mastodon-web")]))
        changed_service["spec"]["selector"] = {"app": "wrong"}
        bad = dict(by_key)
        bad[("Service", "mastodon-web")] = changed_service
        self.assertTrue(CONTRACT.check(baseline, bad))


if __name__ == "__main__":
    unittest.main()
