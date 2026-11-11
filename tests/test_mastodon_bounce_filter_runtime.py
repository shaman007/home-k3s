"""Opt-in Sieve integration checks with synthetic messages containing no tokens."""

import os
from pathlib import Path
import subprocess
import unittest
import uuid
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
        cls.path = "/tmp/mastodon-bounce-test-" + uuid.uuid4().hex
        deployed = os.environ.get(
            "SIEVE_TEST_SCRIPT", "/etc/dovecot/sieve-before/mastodon-registration-bounces.sieve"
        )
        actual = cls.run_pod(["cat", deployed]).stdout.decode()
        if actual != cls.script:
            raise AssertionError("Deployed Sieve rule differs from repository")
        cls.run_pod(
            ["sh", "-c", f"cat > {cls.path}.sieve; sievec {cls.path}.sieve"], cls.script.encode()
        )

    @classmethod
    def run_pod(cls, args, payload=None):
        """Execute a test command with optional input inside the existing Dovecot pod."""
        return subprocess.run(
            ["kubectl", "exec", "-i", "-n", "mail", "deployment/dovecot", "--", *args],
            input=payload,
            capture_output=True,
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.run_pod(["rm", "-f", cls.path + ".sieve", cls.path + ".svbin", cls.path + ".eml"])

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
                self.run_pod(
                    ["sh", "-c", f"cat > {self.path}.eml; chmod 644 {self.path}.eml"],
                    message.encode(),
                )
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
