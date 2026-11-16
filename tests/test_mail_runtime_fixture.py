"""Keep opt-in SMTP fault injection isolated from production routing and data."""

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/security"))
SPEC = importlib.util.spec_from_file_location(
    "mail_runtime_fixture", ROOT / "tools/security/test_mail_capability_guards.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

RUNTIME_SPEC = importlib.util.spec_from_file_location(
    "mail_runtime", ROOT / "tools/security/test_mail_runtime.py"
)
runtime = importlib.util.module_from_spec(RUNTIME_SPEC)
RUNTIME_SPEC.loader.exec_module(runtime)


class MailRuntimeFixtureTests(unittest.TestCase):
    """Prevent real domain rewriting and recursive duplicate-setting logging."""

    def test_daemon_selection_is_independent_of_sidecar_order(self):
        """Probe the named daemon even when another container uses the same image."""
        for name in ("postfix", "dovecot"):
            source = probe.yaml.safe_load(
                (ROOT / ("mail/deployment-" + name + ".yaml")).read_text()
            )
            daemon = next(
                item for item in source["spec"]["template"]["spec"]["containers"]
                if item["name"] == name + "-mail"
            )
            sidecar = {
                "name": "same-image-sidecar",
                "image": daemon["image"],
                "securityContext": {"capabilities": {"add": ["SYS_ADMIN"]}},
            }
            for containers in ([sidecar, daemon], [daemon, sidecar]):
                with self.subTest(daemon=name, first=containers[0]["name"]):
                    document = copy.deepcopy(source)
                    document["spec"]["template"]["spec"]["containers"] = containers
                    with patch.object(probe.yaml, "safe_load", return_value=document):
                        args, selected = probe.command(name)
                    self.assertIs(selected, daemon)
                    self.assertIn("--cap-drop=ALL", args)
                    self.assertNotIn("--cap-add=SYS_ADMIN", args)

    def test_missing_or_duplicate_daemon_names_fail_closed(self):
        """Never fall back to another container when the daemon identity is ambiguous."""
        source = probe.yaml.safe_load(
            (ROOT / "mail/deployment-postfix.yaml").read_text()
        )
        daemon = next(
            item for item in source["spec"]["template"]["spec"]["containers"]
            if item["name"] == "postfix-mail"
        )
        for containers in ([], [dict(daemon, name="other")], [daemon, daemon]):
            with self.subTest(count=len(containers)):
                document = copy.deepcopy(source)
                document["spec"]["template"]["spec"]["containers"] = containers
                with patch.object(probe.yaml, "safe_load", return_value=document), \
                        self.assertRaisesRegex(AssertionError, "exactly one postfix-mail"):
                    probe.command("postfix")

    def test_fixture_delivers_only_locally_without_duplicate_settings(self):
        """Rewriting a bare alias must never send mail to the production domain."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(
                probe, "run", side_effect=["spool", "state", "container"]
            ):
                probe.start_postfix(
                    path,
                    "dovecot-fixture",
                    [],
                    milter="127.0.0.1:11332",
                    fixture_domain="guard.invalid",
                )
            config = (path / "postfix-config").read_text()
            settings = [
                line.split("=", 1)[0].strip()
                for line in config.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            self.assertEqual(len(settings), len(set(settings)))
            for expected in (
                "myorigin = guard.invalid",
                "mydomain = guard.invalid",
                "mydestination = localhost guard.invalid",
                "default_transport = error:Nonlocal delivery disabled in fixture",
                "mailbox_transport = lmtp:inet:127.0.0.1:24",
                "smtpd_milters = inet:127.0.0.1:11332",
                "milter_default_action = tempfail",
            ):
                self.assertIn(expected, config)
            self.assertEqual(
                (path / "postfix-virtual").read_text(), "@guard.invalid guard\n"
            )

    def test_external_fixture_endpoints_rejected_before_container_creation(self):
        """Invalid targets must fail before allocating any external resources."""
        with patch.object(probe, "run") as run:
            for options in (
                {"milter": "rspamd.mail.svc.cluster.local:11332"},
                {"fixture_domain": "andreybondarenko.com"},
            ):
                with self.assertRaises(ValueError):
                    probe.start_postfix(Path("unused-fixture"), "fixture", [], **options)
            run.assert_not_called()

    def test_cleanup_skips_only_missing_owned_volumes(self):
        """Container rm -v may already remove its disposable volumes."""
        with (
            patch.object(
                runtime,
                "native",
                side_effect=[MagicMock(returncode=0), MagicMock(returncode=1)],
            ) as exists,
            patch.object(runtime.guards, "run") as remove,
        ):
            runtime.cleanup_volumes(["owned-present", "owned-missing"])
            self.assertEqual(exists.call_count, 2)
            remove.assert_called_once_with(["podman", "volume", "rm", "owned-present"])
        with (
            patch.object(runtime, "native", return_value=MagicMock(returncode=125)),
            patch.object(runtime.guards, "run") as remove,
        ):
            with self.assertRaises(RuntimeError):
                runtime.cleanup_volumes(["owned"])
            remove.assert_not_called()
