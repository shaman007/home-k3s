"""Run native scripts against local fixtures only; no production service calls."""

import json
import os
import shutil
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "tools/bootstrap"


def native(runtime, arguments, **kwargs):
    """Run a fixed reviewed local runtime with a bounded fixture."""
    executable = shutil.which(runtime)
    if executable is None:
        raise RuntimeError("Missing existing native test runtime: " + runtime)
    return subprocess.run(  # nosec B603
        [executable, *arguments],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        **kwargs,
    )


class NativeDependencyTests(unittest.TestCase):
    """No dependency check may execute work, leak driver output or wait forever."""

    def shell_fixture(self, script, executable, body, *, arguments=(), budget=1):
        """Run the real shell wrapper, replacing only the native client/work fixture."""
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / executable
            program.write_text("#!/bin/sh\n" + body)
            program.chmod(0o755)
            env = dict(
                os.environ,
                PATH=directory + os.pathsep + os.environ.get("PATH", ""),
                STARTUP_WAIT_SECONDS=str(budget),
            )
            return native("sh", [str(BOOT / script), *arguments], env=env)

    def test_nextcloud_skip_never_calls_cron_and_hides_probe_output(self):
        """The skip is in the main wrapper, not a successful init releasing work."""
        result = self.shell_fixture(
            "nextcloud_job_gate.sh",
            "php",
            """
if [ "$1" = /nextcloud/cron.php ]; then echo WORK-MUST-NOT-RUN; exit 17; fi
echo synthetic-driver-detail
echo synthetic-driver-error >&2
exit 1
""",
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["result"], "skipped")
        self.assertNotIn("synthetic-driver", result.stdout + result.stderr)
        self.assertNotIn("WORK-MUST-NOT-RUN", result.stdout + result.stderr)

    def test_nextcloud_work_exit_code_is_preserved(self):
        """Healthy dependencies must not turn a failed cron invocation into success."""
        result = self.shell_fixture(
            "nextcloud_job_gate.sh",
            "php",
            """
if [ "$1" = /nextcloud/cron.php ]; then echo WORK-RAN; exit 17; fi
exit 0
""",
            budget=5,
        )
        self.assertEqual(result.returncode, 17)
        self.assertIn('"result":"ready"', result.stdout)
        self.assertIn("WORK-RAN", result.stdout)

    def test_nextcloud_status_requires_installed_not_upgrading_not_maintenance(self):
        """Status booleans are strict; incomplete or string-valued replies stay closed."""
        cases = [
            ({"installed": True, "maintenance": False, "needsDbUpgrade": False}, True),
            ({"installed": True, "maintenance": True, "needsDbUpgrade": False}, False),
            ({"installed": True, "maintenance": False, "needsDbUpgrade": True}, False),
            (
                {"installed": False, "maintenance": False, "needsDbUpgrade": False},
                False,
            ),
            (
                {"installed": True, "maintenance": "false", "needsDbUpgrade": False},
                False,
            ),
            ({"installed": True, "maintenance": False}, False),
        ]
        harness = (
            "require "
            + json.dumps(str(BOOT / "nextcloud_job_ready.php"))
            + ";echo json_encode(nextcloudJobReady(json_decode(stream_get_contents(STDIN),true)));"
        )
        for payload, expected in cases:
            result = native("php", ["-r", harness], input=json.dumps(payload))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)

    def test_mail_training_skips_before_work_and_requires_http_200(self):
        """A redirect or failed Rspamd cannot start the existing mailbox trainer."""
        arguments = ["sh", "-c", "echo WORK-RAN; exit 17"]
        for status in ("503", "302"):
            result = self.shell_fixture(
                "mail_training_gate.sh",
                "curl",
                f"echo {status}\nexit 0\n",
                arguments=arguments,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["result"], "skipped")
            self.assertNotIn("WORK-RAN", result.stdout)
        result = self.shell_fixture(
            "mail_training_gate.sh",
            "curl",
            "echo 200\nexit 0\n",
            arguments=arguments,
            budget=5,
        )
        self.assertEqual(result.returncode, 17)
        self.assertIn("WORK-RAN", result.stdout)

    def test_nextcloud_http_probe_rejects_redirect_errors_and_invalid_body(self):
        """Run the real PHP entrypoint with an isolated HTTP stream fixture."""
        path = json.dumps(str(BOOT / "nextcloud_job_ready.php"))
        harness = r"""
$fixture=json_decode(stream_get_contents(STDIN),true);
class FixtureHttp {
    public $context;
    private int $position=0;
    public function stream_open($path,$mode,$options,&$opened_path): bool {
        $context=stream_context_get_options($this->context);
        if (($context['http']['follow_location'] ?? null)!==0) return false;
        $GLOBALS['http_response_header']=[$GLOBALS['fixture']['status']];
        return true;
    }
    public function stream_read(int $count): string {
        $part=substr($GLOBALS['fixture']['body'],$this->position,$count);
        $this->position+=strlen($part);
        return $part;
    }
    public function stream_eof(): bool {
        return $this->position>=strlen($GLOBALS['fixture']['body']);
    }
    public function stream_stat(): array {return [];}
}
stream_wrapper_unregister('http');
stream_wrapper_register('http',FixtureHttp::class);
"""
        harness += "$_SERVER['SCRIPT_FILENAME']=" + path + ";require " + path + ";"
        healthy = json.dumps(
            {"installed": True, "maintenance": False, "needsDbUpgrade": False}
        )
        for status, body, expected in (
            ("HTTP/1.1 200 OK", healthy, 0),
            ("HTTP/1.1 302 Found", healthy, 1),
            ("HTTP/1.1 500 Error", healthy, 1),
            ("HTTP/1.1 200 OK", "not-json", 1),
            ("HTTP/1.1 200 OK", "x" * 65537, 1),
        ):
            result = native(
                "php",
                ["-r", harness],
                input=json.dumps({"status": status, "body": body}),
            )
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertEqual(result.stdout, "")

    def test_karakeep_real_http_contracts_and_total_deadline(self):
        """Wrong JSON, redirect and a hanging response must not release the workers."""
        code = r"""
const assert = require('node:assert/strict');
const http = require('node:http');
const {probe, wait} = require(process.argv[1]);
(async()=>{
  let hits=[];
  const server=http.createServer((req,res)=>{
    hits.push(req.url);
    if(req.url==='/hang'){res.writeHead(200);res.write('{');return;}
    if(req.url==='/redirect'){res.writeHead(302,{Location:'/ready'});res.end();return;}
    res.writeHead(200,{'Content-Type':'application/json'});
    res.end(req.url==='/ready'?'{"status":"available"}':req.url==='/chrome'?'{"webSocketDebuggerUrl":"ws://fixture"}':'{"status":"unavailable"}');
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  try{
    const base='http://127.0.0.1:'+server.address().port;
    assert.equal(await probe(base+'/ready','status','available',1000),true);
    assert.equal(await probe(base+'/wrong','status','available',1000),false);
    assert.equal(await probe(base+'/chrome','webSocketDebuggerUrl',null,1000),true);
    assert.equal(await probe(base+'/redirect','status','available',1000),false);
    assert.deepEqual(hits,['/ready','/wrong','/chrome','/redirect']);
    const start=Date.now();
    assert.equal(await probe(base+'/hang','status','available',50),false);
    assert(Date.now()-start<1000);
    let now=0;
    assert.equal(await wait({budgetMs:30,intervalMs:10,now:()=>now,sleep:async(ms)=>{now+=ms;},check:async()=>now>=20}),true);
    now=0;
    assert.equal(await wait({budgetMs:30,intervalMs:10,now:()=>now,sleep:async(ms)=>{now+=ms;},check:async()=>false}),false);
    console.log('native-contracts-ok');
  }finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
})().catch(()=>{console.error('fixture-failed');process.exitCode=1;});
"""
        result = native("node", ["-e", code, str(BOOT / "karakeep_worker_gate.cjs")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "native-contracts-ok")


if __name__ == "__main__":
    unittest.main()
