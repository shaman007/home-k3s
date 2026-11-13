"""Exercise native-client gates, literal config safety and preserved workload behavior."""

import importlib.util
import json
import os
import shutil

# Only the reviewed native runtime fixture runner launches processes.
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "tools/bootstrap"
SPEC = importlib.util.spec_from_file_location(
    "application_gates", BOOT / "prepare_application_gates.py"
)
GATES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATES)


def run_native(runtime, arguments, **kwargs):
    """Run trusted native probes against isolated fixtures, without a shell launcher."""
    if set(kwargs) - {"env", "input"}:
        raise ValueError("Only fixture input and environment overrides are allowed")
    if runtime not in {"php", "node", "sh"}:
        raise ValueError("Unexpected runtime")
    executable = shutil.which(runtime)
    if executable is None:
        raise RuntimeError("Install required startup test runtime: " + runtime)
    # Runtime names and arguments come only from the reviewed tests in this file.
    return subprocess.run(  # nosec B603
        [executable, *arguments],
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
        **kwargs,
    )


class LiteralConfigTests(unittest.TestCase):
    """Never execute PVC configs; unsupported syntax fails closed."""

    def parse(self, source, mode="nextcloud"):
        """Parse."""
        harness = (
            "require " + json.dumps(str(BOOT / "probe_data.php")) + ";"
            "$p=new ConfigLiterals(stream_get_contents(STDIN));"
            "try {echo json_encode($p->" + mode + "());}"
            "catch(Throwable){exit(1);}"
        )
        return run_native("php", ["-r", harness], input=source)

    def test_nextcloud_nested_array_and_escaping(self):
        """Nextcloud nested array and escaping."""
        source = (
            r"<?php $CONFIG = array('dbpassword'=>'a\'b\\c\n', "
            "'redis'=>['port'=>'6379','user'=>'acl'], 'list'=>array(1,true,null));"
        )
        result = self.parse(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "dbpassword": "a'b\\c\\n",
                "redis": {"port": "6379", "user": "acl"},
                "list": [1, True, None],
            },
        )

    def test_no_execution_and_duplicate_or_dynamic_values_rejected(self):
        """No execution and duplicate or dynamic values rejected."""
        for source in [
            "<?php $CONFIG=['password'=>getenv('DO_NOT_EXPOSE')];",
            "<?php $CONFIG=['host'=>'a','host'=>'b'];",
            "<?php $CONFIG=['password'=>\"${secret}\"];",
            "<?php $CONFIG=[]; echo 'DO_NOT_EXPOSE';",
            "<?php $CONFIG=['password'=>\"\\x41\"];",
        ]:
            with self.subTest(source=source):
                result = self.parse(source)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout + result.stderr, "")

    def test_wordpress_only_literal_data_definitions(self):
        """Wordpress only literal data definitions."""
        source = (
            "<?php define('ABSPATH', dirname(__FILE__)); define('DB_PASSWORD', 'fixture'); "
            "require 'missing-bootstrap.php'; define('WP_REDIS_PORT',6379);"
        )
        result = self.parse(source, "wordpress")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"DB_PASSWORD": "fixture", "WP_REDIS_PORT": 6379},  # nosec B105
        )
        for value in ["getenv('DO_NOT_EXPOSE')", "'a'.'b'"]:
            self.assertEqual(
                self.parse(
                    "<?php define('DB_PASSWORD'," + value + ");", "wordpress"
                ).returncode,
                1,
            )
        self.assertEqual(
            self.parse(
                "<?php define('DB_HOST','a');define('DB_HOST','b');", "wordpress"
            ).returncode,
            1,
        )

    def test_double_quoted_literal_escapes(self):
        """Double quoted literal escapes."""
        result = self.parse(r'<?php $CONFIG=["value"=>"a\n\$b\\c\"d"];')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"value": 'a\n$b\\c"d'})

    def test_bad_mode_never_logs_credentials(self):
        """Bad mode never logs credentials."""
        result = run_native("php", [str(BOOT / "probe_data.php"), "DO_NOT_EXPOSE"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout + result.stderr, "")


class NativeClientTests(unittest.TestCase):
    """Real shell/Node runtimes with local protocol/command doubles."""

    def shell_probe(self, client, body, mode, **environment):
        """Shell probe."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / client
            path.write_text("#!/bin/sh\n" + body)
            path.chmod(0o700)
            env = dict(
                os.environ,
                PATH=directory + os.pathsep + os.environ["PATH"],
                STARTUP_WAIT_SECONDS="1",
                VALKEY_HOST="fixture.invalid",
            )
            env.update(environment)
            script = "wait_mysql.sh" if mode == "mysql" else "wait_service.sh"
            return run_native("sh", [str(BOOT / script), mode], env=env)

    def test_sql_success_and_bad_auth_are_distinct_and_sanitized(self):
        """Sql success and bad auth are distinct and sanitized."""
        success = self.shell_probe("psql", "echo 1\n", "postgres")
        self.assertEqual(success.returncode, 0, success.stderr)
        failure = self.shell_probe(
            "psql", "echo DO_NOT_EXPOSE >&2\necho 1\nexit 1\n", "postgres"
        )
        self.assertEqual(failure.returncode, 1)
        self.assertNotIn("DO_NOT_EXPOSE", failure.stdout + failure.stderr)
        self.assertIn("timeout", failure.stdout)

    def test_valkey_error_reply_cannot_open_gate(self):
        """Valkey error reply cannot open gate."""
        self.assertEqual(
            self.shell_probe("valkey-cli", "echo PONG\n", "valkey").returncode, 0
        )
        failure = self.shell_probe("valkey-cli", "echo NOAUTH\n", "valkey")
        self.assertEqual(failure.returncode, 1)
        self.assertNotIn("NOAUTH", failure.stdout + failure.stderr)

    def test_retry_recovers_and_stuck_request_is_bounded(self):
        """Retry recovers and stuck request is bounded."""
        with tempfile.TemporaryDirectory() as directory:
            marker = str(Path(directory) / "attempt")
            body = 'if [ ! -f "$MARKER" ]; then touch "$MARKER"; exit 1; fi\necho 1\n'
            recovered = self.shell_probe(
                "psql", body, "postgres", MARKER=marker, STARTUP_WAIT_SECONDS="7"
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertIn("waiting", recovered.stdout)
        stuck = self.shell_probe("psql", "sleep 30\n", "postgres")
        self.assertEqual(stuck.returncode, 1)
        self.assertIn("timeout", stuck.stdout)

    def test_mysql_requires_success_and_exact_sql_result(self):
        """An auth/SQL error cannot open either Firefox database gate."""
        environment = {
            "MYSQL_HOST": "fixture.invalid",
            "MYSQL_USER": "fixture",
            "MYSQL_DATABASE": "fixture",
        }
        for body, expected in [
            ("echo 1\n", 0),
            ("echo 1; echo PRIVATE_DRIVER_ERROR >&2; exit 1\n", 1),
            ("echo '1 extra'\n", 1),
        ]:
            result = self.shell_probe("mariadb", body, "mysql", **environment)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertNotIn("PRIVATE_DRIVER_ERROR", result.stdout + result.stderr)

    def test_http_requires_200_without_redirect(self):
        """Http requires 200 without redirect."""
        source = """const http=require('node:http');
const {probe}=require(process.argv[1]);
(async()=>{const s=http.createServer((q,r)=>{r.writeHead(Number(q.url.slice(1)));r.end();});
await new Promise(r=>s.listen(0,'127.0.0.1',r));
try {let results=[];
for(const status of [200,302,503]) {
results.push(await probe('http://127.0.0.1:'+s.address().port+'/'+status));}
console.log(JSON.stringify(results));}finally{s.close();}})();"""
        result = run_native("node", ["-e", source, str(BOOT / "probe_http.cjs")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [True, False, False])


class ApplicationSourceTests(unittest.TestCase):
    """Validate source drift, gate order, identities, credentials and narrow changes."""

    def test_generated_source_is_current_and_idempotent(self):
        """Generated source is current and idempotent."""
        for relative, expected in GATES.candidates().items():
            path = ROOT / relative
            actual = yaml.safe_load(path.read_text())
            self.assertEqual(actual, expected, relative)
            if actual["kind"] != "ConfigMap":
                self.assertEqual(
                    yaml.safe_load(GATES.update_blocks(path.read_text(), expected)),
                    expected,
                )

    def test_existing_preparation_and_dependency_order(self):
        """Existing preparation and dependency order."""
        expected = {
            "bitwarden/deployment-bitwarden.yaml": [
                "prepare-permissions",
                "wait-for-postgres",
            ],
            "firefox-sync/deployment-firefox-sync.yaml": [
                "wait-for-syncstorage",
                "wait-for-tokenserver",
            ],
            "immich/deployment-immich-server.yaml": [
                "prepare-library",
                "wait-for-postgres",
                "wait-for-valkey",
            ],
            "keycloak/stateful-set-keycloak.yaml": ["wait-for-postgres"],
            "nextcloud/stateful-set-nextcloud-web.yaml": [
                "wait-for-sql",
                "wait-for-valkey",
            ],
            "wordpress/deployment-php.yaml": ["wait-for-sql", "wait-for-valkey"],
            "your-spotify/deployment-ferretdb.yaml": ["wait-for-postgres"],
            "your-spotify/deployment-server.yaml": ["wait-for-ferretdb"],
            "your-spotify/deployment-web.yaml": [
                "prepare-runtime-assets",
                "wait-for-server",
            ],
        }
        candidates = GATES.candidates()
        for relative, names in expected.items():
            pod = candidates[relative]["spec"]["template"]["spec"]
            self.assertEqual([c["name"] for c in pod["initContainers"]], names)
            for gate in pod["initContainers"]:
                if not gate["name"].startswith("wait-for-"):
                    continue
                self.assertFalse(gate["securityContext"]["allowPrivilegeEscalation"])
                self.assertTrue(gate["securityContext"]["readOnlyRootFilesystem"])
                for env in gate["env"]:
                    if env["name"] in {"PGPASSWORD", "MYSQL_PWD"}:
                        self.assertIn("secretKeyRef", env["valueFrom"])
                for mount in gate["volumeMounts"]:
                    self.assertTrue(mount["readOnly"])

    def test_gate_memory_requests_respect_real_namespace_minimums(self):
        """Catch Pod admission failures before Argo replaces a working replica."""
        ranges = {}
        for document in yaml.safe_load_all(
            (ROOT / "namespaces/limit-ranges.yaml").read_text()
        ):
            for limit in document["spec"]["limits"]:
                if limit["type"] == "Container":
                    minimum = limit.get("min", {}).get("memory")
                    if minimum is not None:
                        self.assertTrue(minimum.endswith("Mi"))
                        ranges[document["metadata"]["namespace"]] = int(minimum[:-2])
        for relative, document in GATES.candidates().items():
            if document["kind"] == "ConfigMap":
                continue
            namespace = document["metadata"]["namespace"]
            for gate in document["spec"]["template"]["spec"]["initContainers"]:
                if not gate["name"].startswith("wait-for-"):
                    continue
                request = gate["resources"]["requests"]["memory"]
                self.assertTrue(request.endswith("Mi"))
                self.assertGreaterEqual(
                    int(request[:-2]), ranges.get(namespace, 0), relative
                )

    def test_firefox_checks_both_databases_without_exporting_url_credentials(self):
        """Two schemas use the app password ref; no root credential or URL is copied."""
        document = GATES.candidates()["firefox-sync/deployment-firefox-sync.yaml"]
        gates = document["spec"]["template"]["spec"]["initContainers"]
        databases = []
        for gate in gates:
            env = {entry["name"]: entry for entry in gate["env"]}
            databases.append(env["MYSQL_DATABASE"]["value"])
            self.assertEqual(
                env["MYSQL_PWD"]["valueFrom"]["secretKeyRef"],
                {"name": "firefox-sync-env", "key": "MYSQL_PASSWORD"},
            )
            self.assertFalse(any("URL" in name or "ROOT" in name for name in env))
        self.assertEqual(databases, ["syncstorage", "tokenserver"])

    def test_changed_firefox_connection_contract_requires_review(self):
        """Do not silently copy an embedded password or gate the wrong database."""
        original = GATES.container

        def changed_container(path, name):
            result = original(path, name)
            if name == "syncserver":
                entry = next(
                    e
                    for e in result["env"]
                    if e["name"] == "SYNC_TOKENSERVER__DATABASE_URL"
                )
                entry["value"] = "mysql://sync:PRIVATE_PASSWORD@mysql:3306/tokenserver"
            return result

        with patch.object(GATES, "container", side_effect=changed_container):
            with self.assertRaises(ValueError) as error:
                GATES.candidates()
            self.assertNotIn("PRIVATE_PASSWORD", str(error.exception))

    def test_mastodon_stays_out_of_package(self):
        """Mastodon stays out of package."""
        self.assertFalse(any(p.startswith("mastodon/") for p in GATES.candidates()))


if __name__ == "__main__":
    unittest.main()
