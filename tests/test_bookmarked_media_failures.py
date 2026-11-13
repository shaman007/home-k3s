"""Check bookmarked-media failure handling without hiding incomplete processing."""

import json
import os
from pathlib import Path
import subprocess  # nosec B404
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class BookmarkedMediaFailureTest(unittest.TestCase):
    """Exercise incomplete and failed media processing without hiding errors."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + ":/usr/bin:/bin",
            "IMMICH_INSTANCE_URL": "https://example.invalid/api",
            "IMMICH_API_KEY": "dummy",
            "BOOKMARKED_MEDIA_DOWNLOAD_MAX_ATTEMPTS": "2",
            "BOOKMARKED_MEDIA_DOWNLOAD_RETRY_DELAY_SECONDS": "0",
        }
        self.scripts = yaml.safe_load(
            (ROOT / "mastodon/config-map-bookmarked-media-sync-scripts.yaml").read_text()
        )["data"]

    def stub(self, name, body):
        """Create an executable shell stub in the isolated fixture command directory."""
        file = self.bin / name
        file.write_text("#!/bin/sh\n" + body + "\n")
        file.chmod(0o755)
        return file

    def execute(self, script):
        """Run a shell fragment with fixture commands and capture its result."""
        return subprocess.run(
            ["/bin/sh", "-c", script],
            check=False,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def upload_script(self):
        """Prepare the deployed upload script with local media and command stubs."""
        doc = yaml.safe_load((ROOT / "mastodon/cron-job-bookmarked-media-sync.yaml").read_text())
        source = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][
            2
        ]
        media = self.root / "import"
        media.mkdir()
        (media / "image.jpg").write_text("test")
        for name in ["npm", "immich", "apk", "curl", "descriptions", "node"]:
            self.stub(name, "exit 0")
        return source.replace("/import", str(media)).replace(
            "/scripts/apply-immich-descriptions.sh", "descriptions"
        )

    def test_dependency_skip_marker_prevents_upload_work(self):
        """A successful init skip must never start upload in the next container."""
        source = self.upload_script()
        work = self.root / "work"
        work.mkdir()
        (work / ".dependencies-skipped").touch()
        called = self.root / "unexpected-work"
        for name in ("node", "npm", "immich"):
            self.stub(name, f"touch '{called}'; exit 99")
        result = self.execute(source.replace("/work", str(work)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(called.exists())

    def test_install_login_upload_and_description_failures_fail_job(self):
        """Verify install login upload and description failures fail job."""
        source = self.upload_script()
        for command, body in [
            ("npm", "exit 1"),
            ("immich", "exit 1"),
            ("immich", 'case "$*" in *upload*) exit 1;; esac'),
            ("descriptions", "exit 1"),
        ]:
            with self.subTest(command=command, body=body):
                self.stub(command, body)
                self.assertNotEqual(0, self.execute(source).returncode)
                self.stub(command, "exit 0")

    def test_face_detection_remains_best_effort(self):
        """Verify face detection remains best effort."""
        source = self.upload_script()
        self.stub("curl", "exit 1")
        self.assertEqual(0, self.execute(source).returncode)

    def description_script(self):
        """Prepare description-sync inputs and redirect deployed paths into the fixture."""
        work = self.root / "work"
        (work / "export").mkdir(parents=True)
        (work / "import").mkdir()
        (work / "import/image.jpg").write_text("data")
        entry = {
            "id": "1",
            "relative_path": "image.jpg",
            "status_id": "2",
            "description": "caption",
        }
        (work / "export/bookmarked_media_manifest.jsonl").write_text(json.dumps(entry) + "\n")
        return (
            self.scripts["apply-immich-descriptions.sh"]
            .replace("/work", str(work))
            .replace("/tmp/immich-description-sync", str(self.root / "descriptions"))
        )

    def test_bulk_lookup_http_failure_is_not_hidden_by_jq(self):
        """Verify bulk lookup HTTP failure is not hidden by jq."""
        source = self.description_script()
        self.stub("curl", "exit 22")
        self.assertNotEqual(0, self.execute(source).returncode)

    def test_failed_description_update_fails_script(self):
        """Verify failed description update fails script."""
        source = self.description_script()
        self.stub(
            "curl",
            """case "$*" in *bulk-upload-check*)
          while [ "$#" -gt 0 ]; do
            if [ "$1" = "-o" ]; then shift; """
            """printf '%s' '{"results":[{"id":"1","assetId":"asset-1"}]}' > "$1"; break; fi
            shift
          done;; *) exit 22;; esac""",
        )
        self.assertNotEqual(0, self.execute(source).returncode)

    def fetch_script(self):
        """Prepare media-fetch command stubs and redirect paths into the fixture."""
        work = self.root / "work"
        ruby = self.root / "scripts"
        ruby.mkdir()
        (ruby / "list_bookmarked_media_s3.rb").write_text("")
        entry = json.dumps(
            {"url": "https://example.invalid/image.jpg", "relative_path": "image.jpg"}
        )
        self.stub(
            "kubectl",
            f"""case "$*" in get*) echo pod;; *" -- cat "*) printf '%s\\n' '{entry}';; esac""",
        )
        return (
            self.scripts["fetch-bookmarked-media.sh"]
            .replace("/work", str(work))
            .replace("/scripts", str(ruby))
        )

    def test_missing_object_is_skipped_but_transient_failure_fails(self):
        """Verify missing object is skipped but transient failure fails."""
        source = self.fetch_script()
        self.stub("curl", 'case "$*" in *--head*) printf 404;; *) exit 99;; esac')
        self.assertEqual(0, self.execute(source).returncode)
        log = self.root / "curl.log"
        self.stub(
            "curl",
            f"""printf '%s\\n' "$*" >> '{log}'
case "$*" in *--head*) printf 000; exit 28;; *) exit 28;; esac""",
        )
        self.assertNotEqual(0, self.execute(source).returncode)
        calls = log.read_text().splitlines()
        self.assertEqual(3, len(calls))
        self.assertIn("--max-time 30", calls[0])
        for call in calls[1:]:
            self.assertIn("--max-time 120", call)
            self.assertNotIn("--retry", call)
