"""Active custom jobs: offline outage, authorization and multi-container barriers."""

import fnmatch
import importlib.util
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "tools/bootstrap"
sys.path.insert(0, str(BOOT))
SPEC = importlib.util.spec_from_file_location(
    "custom_crons", BOOT / "prepare_custom_crons.py"
)
CUSTOM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CUSTOM)
sys.path.pop(0)


class CustomCronTests(unittest.TestCase):
    """Read-only probes must guard every work path, including upload after init."""

    def test_sources_canonical_and_only_seven_custom_jobs(self):
        """Regeneration is idempotent; no Longhorn or application Deployments."""
        documents = CUSTOM.documents()
        self.assertEqual(sum(d["kind"] == "CronJob" for d in documents.values()), 7)
        for path, doc in documents.items():
            self.assertNotIn("longhorn", path)
            self.assertIn(doc["kind"], ("CronJob", "ConfigMap"))
            self.assertEqual(yaml.safe_load((ROOT / path).read_text()), doc)
            if doc["kind"] == "ConfigMap":
                self.assertTrue(doc["immutable"])

    def test_argocd_sources_include_every_dependency_config_map(self):
        """Explicit directory filters must ship script ConfigMaps with their jobs."""
        owners = {
            "logs-check": "logs-check",
            "external-access-daily-report": "external-access-analytics",
            "wordpress-daily-report": "wordpress",
            "nextcloud": "nextcloud",
            "rspamd-spam-trainer": "mail",
            "bookmarked-media-sync": "mastodon-custom",
            "mastodon-spam-list-sync": "mastodon-custom",
        }
        documents = CUSTOM.documents()
        for job in (d for d in documents.values() if d["kind"] == "CronJob"):
            app = yaml.safe_load(
                (
                    ROOT
                    / "argocd"
                    / ("application-" + owners[job["metadata"]["name"]] + ".yaml")
                ).read_text()
            )
            source = app["spec"]["source"]
            options = source.get("directory", {})
            pattern = options.get("include", "*")
            patterns = (
                pattern[1:-1].split(",") if pattern.startswith("{") else [pattern]
            )
            pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
            refs = {v.get("configMap", {}).get("name") for v in pod.get("volumes", [])}
            for path, cm in documents.items():
                if cm["kind"] != "ConfigMap" or cm["metadata"]["name"] not in refs:
                    continue
                relative = Path(path).relative_to(source["path"]).as_posix()
                self.assertTrue(
                    any(fnmatch.fnmatchcase(relative, p) for p in patterns), path
                )
                self.assertFalse(
                    fnmatch.fnmatchcase(relative, options.get("exclude", "")), path
                )

    def test_media_uses_explicit_in_cluster_token_file(self):
        """The gate and inherited fetch must never depend on kubectl fallback."""
        docs = CUSTOM.mastodon(True)
        cm = next(d for d in docs.values() if d["kind"] == "ConfigMap")
        self.assertEqual(
            cm["data"]["mastodon_startup.rb"],
            (BOOT / "mastodon_startup.rb").read_text(),
        )
        config = yaml.safe_load(cm["data"]["kubeconfig"])
        self.assertEqual(
            config["clusters"][0]["cluster"]["server"], "https://kubernetes.default.svc"
        )
        self.assertEqual(
            config["users"][0]["user"],
            {"tokenFile": "/var/run/secrets/kubernetes.io/serviceaccount/token"},
        )
        self.assertIn(
            "export KUBECONFIG=/cron-gate/kubeconfig",
            cm["data"]["bookmarked_job_gate.sh"],
        )

    def test_media_upload_guard_precedes_all_work(self):
        """An init skip cannot release npm, login, upload or description work."""
        job = CUSTOM.mastodon(True)["mastodon/cron-job-bookmarked-media-sync.yaml"]
        pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        init, work = pod["initContainers"][0], pod["containers"][0]
        command = work["command"][-1]
        self.assertLess(
            command.index(".dependencies-skipped"), command.index("npm install")
        )
        self.assertLess(
            command.index("bookmarked_upload_probe.cjs"), command.index("npm install")
        )
        self.assertIn("75) exit 0", command)
        self.assertIn('exit "$status"', command)
        for key in ("IMMICH_API_KEY", "IMMICH_INSTANCE_URL"):
            self.assertEqual(
                next(e for e in init["env"] if e["name"] == key),
                next(e for e in work["env"] if e["name"] == key),
            )
        fetch = (BOOT / "bookmarked_job_gate.sh").read_text()
        self.assertNotIn("mastodon_startup.rb migrate", fetch)
        self.assertIn(
            "bundle exec ruby - schema < /cron-gate/mastodon_startup.rb", fetch
        )
        self.assertIn("timeout -s TERM -k 1 4", fetch)
        self.assertIn(": > /work/.dependencies-skipped", fetch)

    def test_media_init_skip_prevents_export_and_sets_shared_marker(self):
        """Run the actual init wrapper on outage/recovery without reading any media."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in {
                "kubectl": "exit 0",
                "jq": 'printf "%s" "$FIXTURE_POD"',
                "curl": 'cat >/dev/null; printf "%s" "$FIXTURE_HTTP"',
                "fetch": 'touch "$FIXTURE_WORK"; exit 7',
            }.items():
                executable = root / name
                executable.write_text("#!/bin/sh\n" + body + "\n")
                executable.chmod(0o755)
            # Reproduce GitHub's /home/runner/work/... shape even on other hosts.
            helper = root / "checkout/work/home-k3s/tools/bootstrap/mastodon_startup.rb"
            helper.parent.mkdir(parents=True)
            helper.write_text((BOOT / "mastodon_startup.rb").read_text())
            script = (BOOT / "bookmarked_job_gate.sh").read_text()
            # Replace container paths before inserting host paths containing /work.
            script = script.replace("/work", str(root / "work")).replace(
                "/scripts/fetch-bookmarked-media.sh", str(root / "fetch")
            )
            script = script.replace("/cron-gate/mastodon_startup.rb", str(helper))
            for pod, http, expected in (
                ("", "503", 0),
                ("ready-pod", "200", 7),
                ("ready-pod", "403", 77),
            ):
                work = root / "export-started"
                work.unlink(missing_ok=True)
                marker = root / "work/.dependencies-skipped"
                marker.unlink(missing_ok=True)
                result = subprocess.run(  # nosec B603
                    ["/bin/sh", "-c", script],
                    env={
                        **os.environ,
                        "PATH": directory + ":" + os.environ["PATH"],
                        "STARTUP_WAIT_SECONDS": "1" if not pod else "5",
                        "FIXTURE_POD": pod,
                        "FIXTURE_HTTP": http,
                        "FIXTURE_WORK": str(work),
                        "IMMICH_API_KEY": "fixture-key",
                        "IMMICH_INSTANCE_URL": "https://immich.andreybondarenko.com/api",
                    },
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(work.exists(), expected == 7)
                self.assertNotIn(b"fixture-key", result.stdout + result.stderr)
                self.assertEqual(marker.exists(), not bool(pod))

    def test_spam_gate_blocks_work_and_preserves_work_failure(self):
        """Execute the shell barrier with fake local Ruby/rails, no cluster calls."""
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            bundle.write_text(
                '#!/bin/sh\ncase "$*" in *ruby*) exit "$PROBE_STATUS" ;; *) exit 7 ;; esac\n'
            )
            bundle.chmod(0o755)
            for status, expected in (("1", 75), ("0", 7)):
                result = subprocess.run(  # nosec B603
                    ["/bin/sh", str(BOOT / "mastodon_spam_job_gate.sh")],
                    env={
                        **os.environ,
                        "PATH": directory + ":" + os.environ["PATH"],
                        "PROBE_STATUS": status,
                    },
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(result.returncode, expected, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_immich_outage_recovery_denial_and_deadline(self):
        """Exercise actual JS waiting code with a deterministic local clock."""
        code = r"""
const assert = require('node:assert/strict');
const {wait,status} = require(process.argv[1]);
(async () => {
 for (const [codes, expected] of [[[503,200],0],[[0],75],[[401],77],[[403],77],[[404],78]]) {
  let time=0, calls=0;
  const result=await wait({check:async()=>codes[Math.min(calls++,codes.length-1)],
    budgetMs:3,intervalMs:1,now:()=>time,sleep:async ms=>{time+=ms;}});
  assert.equal(result,expected);
  assert.ok(time<=3);
 }
 const server=require('node:http').createServer((req,res)=>{
   assert.equal(req.headers['x-api-key'],'fixture'); res.writeHead(302,{Location:'/ready'});res.end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try {assert.equal(await status(`http://127.0.0.1:${server.address().port}/`, 'fixture',1000),302);}
 finally {server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        result = subprocess.run(  # nosec B603
            [
                shutil.which("node"),
                "-e",
                code,
                str(BOOT / "bookmarked_upload_probe.cjs"),
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
