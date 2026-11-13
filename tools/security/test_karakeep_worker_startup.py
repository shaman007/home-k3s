#!/usr/bin/env python3
"""Exercise the real Karakeep s6 startup on empty data and loopback-only fixtures."""

import json
import tempfile
import time
from pathlib import Path

import yaml
from probe_commands import run_command

ROOT = Path(__file__).resolve().parents[2]


def run(args, check=True):
    """Bound argv execution; output contains only disposable fixture data."""
    result = run_command(args, check=False, capture_output=True, text=True, timeout=90)
    if check and result.returncode:
        raise AssertionError(result.stderr[-2500:] + result.stdout[-1000:])
    return result


def until(check, budget=90):
    """Bound the complete observation window."""
    end = time.monotonic() + budget
    while time.monotonic() < end:
        if check():
            return
        time.sleep(1)
    raise AssertionError("Fixture did not reach the expected state")


def main():
    """Start actual s6, toggle only fake providers, then remove this container."""
    deployment = yaml.safe_load(
        (ROOT / "karakeep/deployment-karakeep.yaml").read_text()
    )
    web = next(
        c
        for c in deployment["spec"]["template"]["spec"]["containers"]
        if c["name"] == "web"
    )
    cid = None
    with tempfile.TemporaryDirectory(prefix="karakeep-s6-") as directory:
        fixture = Path(directory)
        fixture.chmod(0o755)
        (fixture / "runtime").mkdir()
        (fixture / "data").mkdir()
        (fixture / "gate.cjs").write_text(
            (ROOT / "tools/bootstrap/karakeep_worker_gate.cjs").read_text()
        )
        (fixture / "run").write_text(
            "#!/command/with-contenv sh\ncd /app/apps/workers\nexec node /fixture/gate.cjs\n"
        )
        (fixture / "run").chmod(0o555)
        (fixture / "gate.cjs").chmod(0o444)
        # Provider modes are fixture-only files, never production configuration.
        (fixture / "providers.cjs").write_text("""
const http = require("node:http");
const fs = require("node:fs");
http.createServer((req,res) => {
  const ready = fs.existsSync("/fixture/chrome-ready");
  res.writeHead(ready ? 200 : 503, {"Content-Type":"application/json"});
  res.end(JSON.stringify(ready ? {webSocketDebuggerUrl:"ws://127.0.0.1:9222/devtools/browser/fixture"} : {}));
}).listen(9222,"127.0.0.1");
http.createServer((req,res) => {
  const ready = fs.existsSync("/fixture/meili-ready");
  res.writeHead(ready ? 200 : 503, {"Content-Type":"application/json"});
  res.end(JSON.stringify(ready ? {status:"available"} : {}));
}).listen(7700,"127.0.0.1");
""")
        (fixture / "providers.cjs").chmod(0o444)
        try:
            args = [
                "podman",
                "run",
                "-d",
                "--network=none",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--read-only",
                "--user=1000:1000",
                "-v",
                str(fixture / "runtime") + ":/run:U,Z",
                "--tmpfs",
                "/tmp:rw,mode=1777",
                "-v",
                str(fixture / "data") + ":/data:U,Z",
                "--add-host=meilisearch.karakeep.svc.cluster.local:127.0.0.1",
                "--add-host=chrome.karakeep.svc.cluster.local:127.0.0.1",
                "-v",
                str(fixture) + ":/fixture:ro,Z",
                "-v",
                str(fixture / "run") + ":/etc/s6-overlay/s6-rc.d/svc-workers/run:ro,Z",
            ]
            for key, value in {
                "DATA_DIR": "/data",
                "BROWSER_WEB_URL": "http://chrome.karakeep.svc.cluster.local:9222",
                "MEILI_ADDR": "http://meilisearch.karakeep.svc.cluster.local:7700",
                "NEXTAUTH_SECRET": "disposable-fixture-only",
                "NEXTAUTH_URL": "http://127.0.0.1:3000",
                "DISABLE_SIGNUPS": "true",
            }.items():
                args += ["-e", key + "=" + value]
            cid = run([*args, web["image"]]).stdout.strip()
            run(["podman", "exec", "-d", cid, "node", "/fixture/providers.cjs"])

            def web_ready():
                return (
                    run(
                        [
                            "podman",
                            "exec",
                            cid,
                            "node",
                            "-e",
                            (
                                'fetch("http://127.0.0.1:3000")'
                                ".then(r=>process.exit(r.status<500?0:1))"
                                ".catch(()=>process.exit(1))"
                            ),
                        ],
                        False,
                    ).returncode
                    == 0
                )

            def workers():
                result = run(
                    [
                        "podman",
                        "exec",
                        cid,
                        "node",
                        "-e",
                        """
const fs=require("node:fs");let found=false;
for(const p of fs.readdirSync("/proc").filter(x=>/^\\d+$/.test(x))) {
try { const argv=fs.readFileSync(`/proc/${p}/cmdline`,"utf8").split("\\0");
if(argv[1]==="dist/index.js") found=true; } catch {}
} process.exit(found?0:1);
""",
                    ],
                    False,
                )
                return result.returncode == 0

            until(web_ready)
            assert not workers(), "Workers started before providers"
            (fixture / "chrome-ready").touch(mode=0o444)
            time.sleep(6)
            assert web_ready() and not workers(), "Meili missing must gate workers only"
            (fixture / "meili-ready").touch(mode=0o444)
            until(workers, 30)
            assert web_ready(), "Worker release must preserve web"
            logs = run(["podman", "logs", cid]).stdout
            assert '"event":"karakeep_worker_dependencies","result":"ready"' in logs
            run(["podman", "stop", "--time", "10", cid])
            state = json.loads(run(["podman", "inspect", cid]).stdout)[0]["State"]
            assert not state["Running"] and state["ExitCode"] != 137, (
                "s6 needed forced kill"
            )
            print(
                "Real s6: migrations/web start with providers down; workers wait for both; "
                "exec and graceful stop passed"
            )
        except Exception:
            if cid:
                result = run(["podman", "logs", "--tail=35", cid], False)
                print(result.stdout + result.stderr)
            raise
        finally:
            if cid:
                run(["podman", "rm", "-f", "-v", cid])
            run(
                [
                    "podman",
                    "unshare",
                    "chown",
                    "-R",
                    "0:0",
                    str(fixture / "runtime"),
                    str(fixture / "data"),
                ]
            )


if __name__ == "__main__":
    main()
