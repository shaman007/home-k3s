"""Opt-in Sieve integration checks with synthetic messages containing no tokens."""

import os
from pathlib import Path, PurePosixPath
import subprocess
import unittest
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("RUN_CLUSTER_TESTS") == "1", "requires live Dovecot")
class MastodonBounceFilterRuntimeTest(unittest.TestCase):
    """Exercise the Mastodon bounce filter with isolated runtime fixtures."""

    @classmethod
    def setUpClass(cls):
        cls.script = yaml.safe_load((ROOT / "mail/config-map-dovecot-cf.yaml").read_text())["data"][
            "mastodon-registration-bounces.sieve"
        ]
        deployed = os.environ.get(
            "SIEVE_TEST_SCRIPT", "/etc/dovecot/sieve-before/mastodon-registration-bounces.sieve"
        )
        actual = cls.run_pod(["cat", deployed]).stdout.decode()
        if actual != cls.script:
            raise AssertionError("Deployed Sieve rule differs from repository")
        directory = (
            cls.run_pod(["mktemp", "-d", "-t", "mastodon-bounce-test.XXXXXXXXXX"])
            .stdout.decode()
            .strip()
        )
        allocated = PurePosixPath(directory)
        if (
            len(allocated.parts) != 3
            or allocated.parts[:2] != ("/", "tmp")
            or not re.fullmatch(r"mastodon-bounce-test\.[A-Za-z0-9_]{6,32}", allocated.name)
        ):
            raise RuntimeError("Unexpected private Sieve fixture directory")
        cls.addClassCleanup(cls.run_pod, ["rm", "-rf", "--", directory])
        cls.run_pod(["chown", "1000:1000", directory])
        cls.path = directory + "/fixture"
        cls.write_fixture(cls.path + ".sieve", cls.script.encode())
        cls.run_pod(["sievec", cls.path + ".sieve"])
        cls.run_pod(["chown", "1000:1000", cls.path + ".svbin"])

    @classmethod
    def run_pod(cls, args, payload=None):
        """Execute a test command with optional input inside the existing Dovecot pod."""
        return subprocess.run(
            ["kubectl", "exec", "-i", "-n", "mail", "deployment/dovecot", "--", *args],
            input=payload,
            capture_output=True,
            check=True,
            timeout=60,
        )

    @classmethod
    def write_fixture(cls, path, payload):
        """Write private synthetic data with a positional path, never shell interpolation."""
        cls.run_pod(
            ["sh", "-ec", 'umask 077; cat > "$1"; chown 1000:1000 "$1"', "fixture", path],
            payload,
        )

    def test_registration_bounces_only(self):
        """Filter registration bounces while preserving unrelated mail."""
        template = """Return-Path: <>
From: Mail Delivery System <MAILER-DAEMON@example.invalid>
To: shaman007@andreybondarenko.com
Subject: Synthetic Sieve fixture
MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status; boundary="test"

--test
Content-Type: text/plain

Synthetic delivery failure.
--test
Content-Type: message/delivery-status

Reporting-MTA: dns; example.invalid

Action: failed
Status: 5.1.1
--test
Content-Type: message/rfc822

From: notifications@andreybondarenko.com
To: nonexistent@example.invalid
Subject: Mastodon: Confirmation instructions for mastodon.andreybondarenko.com

Synthetic content; no confirmation link.
--test--
"""
        cases = [
            ("registration bounce", template, "shaman007", "Trash"),
            (
                "postmaster sender",
                template.replace("MAILER-DAEMON@", "postmaster@"),
                "shaman007",
                "Trash",
            ),
            (
                "personal bounce",
                template.replace("From: notifications@", "From: me@"),
                "shaman007",
                "INBOX",
            ),
            (
                "password reset bounce",
                template.replace("Confirmation instructions", "Reset password instructions"),
                "shaman007",
                "INBOX",
            ),
            (
                "another instance",
                template.replace("mastodon.andreybondarenko.com", "other.example.invalid"),
                "shaman007",
                "INBOX",
            ),
            (
                "not a DSN",
                template.replace(
                    "multipart/report; report-type=delivery-status", "multipart/mixed"
                ),
                "shaman007",
                "INBOX",
            ),
            ("another mailbox", template, "other-user", "INBOX"),
        ]
        for name, message, user, folder in cases:
            with self.subTest(name=name):
                self.write_fixture(self.path + ".eml", message.encode())
                result = self.run_pod(
                    [
                        "sieve-test",
                        "-o",
                        "mail_uid=1000",
                        "-o",
                        "mail_gid=1000",
                        "-r",
                        user + "@andreybondarenko.com",
                        self.path + ".sieve",
                        self.path + ".eml",
                    ]
                )
                output = result.stdout.decode()
                self.assertIn("store message in folder: " + folder, output)
                self.assertNotIn(
                    "store message in folder: " + ("INBOX" if folder == "Trash" else "Trash"),
                    output,
                )


if __name__ == "__main__":
    unittest.main()
