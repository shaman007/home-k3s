"""Check opt-in runtime fixture safety without launching processes or contacting pods."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_mastodon_bounce_filter_runtime as bounce
import test_static_assets_runtime as assets


class SieveFixtureSafetyTest(unittest.TestCase):
    """Keep fixture writes private and ensure setup failures still arrange cleanup."""

    def test_setup_registers_cleanup_before_compiler_failure(self):
        """A failed compiler cannot strand the allocated fixture directory."""
        runtime = type("DisposableBounce", (bounce.MastodonBounceFilterRuntimeTest,), {})
        script = bounce.yaml.safe_load(
            (bounce.ROOT / "mail/config-map-dovecot-cf.yaml").read_text()
        )["data"]["mastodon-registration-bounces.sieve"]
        with tempfile.TemporaryDirectory(prefix="mastodon-bounce-test.") as directory:

            def respond(args, _payload=None):
                if args[0] == "cat":
                    return bounce.subprocess.CompletedProcess(args, 0, stdout=script.encode())
                if args[0] == "mktemp":
                    return bounce.subprocess.CompletedProcess(
                        args, 0, stdout=(directory + "\n").encode()
                    )
                if args[0] == "sievec":
                    raise bounce.subprocess.CalledProcessError(1, args)
                return bounce.subprocess.CompletedProcess(args, 0, stdout=b"")

            with patch.object(runtime, "run_pod", side_effect=respond) as pod:
                try:
                    with self.assertRaises(bounce.subprocess.CalledProcessError):
                        runtime.setUpClass()
                finally:
                    runtime.doClassCleanups()
                self.assertEqual(pod.call_args.args[0], ["rm", "-rf", "--", directory])
                calls = [call.args[0][0] for call in pod.call_args_list]
                self.assertEqual(calls, ["cat", "mktemp", "chown", "sh", "sievec", "rm"])

    def test_deployed_mismatch_allocates_nothing(self):
        """Refuse divergent deployed rules before allocating any fixture."""
        runtime = type("DisposableBounce", (bounce.MastodonBounceFilterRuntimeTest,), {})
        result = bounce.subprocess.CompletedProcess([], 0, stdout=b"different deployed rule")
        with patch.object(runtime, "run_pod", return_value=result) as pod:
            with self.assertRaisesRegex(AssertionError, "differs"):
                runtime.setUpClass()
            self.assertEqual(pod.call_count, 1)
            self.assertEqual(pod.call_args.args[0][0], "cat")

    def test_invalid_allocation_never_writes_or_removes(self):
        """Unexpected allocation output cannot authorize writes or recursive removal."""
        script = bounce.yaml.safe_load(
            (bounce.ROOT / "mail/config-map-dovecot-cf.yaml").read_text()
        )["data"]["mastodon-registration-bounces.sieve"]
        malformed = str(Path(tempfile.gettempdir()) / "mastodon-bounce-test.bad;command")
        for directory in ("/", "/var", "relative", malformed):
            with self.subTest(directory=directory):
                runtime = type("DisposableBounce", (bounce.MastodonBounceFilterRuntimeTest,), {})
                results = [
                    bounce.subprocess.CompletedProcess([], 0, stdout=script.encode()),
                    bounce.subprocess.CompletedProcess([], 0, stdout=directory.encode()),
                ]
                with patch.object(runtime, "run_pod", side_effect=results) as pod:
                    try:
                        with self.assertRaisesRegex(RuntimeError, "private Sieve"):
                            runtime.setUpClass()
                    finally:
                        runtime.doClassCleanups()
                    self.assertEqual(pod.call_count, 2)

    def test_fixture_path_is_positional(self):
        """Shell metacharacters in a path cannot become shell instructions."""
        runtime = bounce.MastodonBounceFilterRuntimeTest
        with patch.object(runtime, "run_pod") as pod:
            runtime.write_fixture("fixture name; unexpected command", b"synthetic")
        args, payload = pod.call_args.args
        self.assertEqual(args[:2], ["sh", "-ec"])
        self.assertIn('"$1"', args[2])
        self.assertIn("umask 077", args[2])
        self.assertNotIn(args[-1], args[2])
        self.assertEqual(payload, b"synthetic")

    def test_pod_commands_have_deadline(self):
        """A stalled diagnostic command cannot hang the test indefinitely."""
        with patch.object(bounce.subprocess, "run") as run:
            bounce.MastodonBounceFilterRuntimeTest.run_pod(["cat", "fixture"])
        self.assertEqual(run.call_args.kwargs["timeout"], 60)
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual(run.call_args.args[0][-2:], ["cat", "fixture"])


class NginxFixtureSafetyTest(unittest.TestCase):
    """Require deliberate source selection before creating servers or processes."""

    def test_missing_source_fails_before_resource_allocation(self):
        """An explicitly requested runtime test cannot silently guess its source."""
        with (
            patch.object(assets, "SOURCE", None),
            patch.object(assets.tempfile, "TemporaryDirectory") as temp,
            patch.object(assets, "PHPServer") as server,
            patch.object(assets.subprocess, "Popen") as process,
        ):
            with self.assertRaisesRegex(RuntimeError, "STATIC_NGINX_SOURCE"):
                assets.StaticAssetsRuntimeTest.setUpClass()
            temp.assert_not_called()
            server.assert_not_called()
            process.assert_not_called()

    def test_source_requires_both_config_files(self):
        """Accept a complete source tree and reject missing configs or escaping symlinks."""
        with tempfile.TemporaryDirectory(prefix="nginx-source-check-") as directory:
            root = Path(directory)
            source = root / "source"
            conf = source / "conf"
            conf.mkdir(parents=True)
            with patch.object(assets, "SOURCE", str(source)):
                with self.assertRaisesRegex(RuntimeError, "conf fixture"):
                    assets.fixture_source()
                (conf / "fastcgi_params").write_text("# synthetic\n")
                (conf / "mime.types").write_text("types {}\n")
                self.assertEqual(assets.fixture_source(), source.resolve())
                (conf / "mime.types").unlink()
                outside = root / "outside"
                outside.write_text("types {}\n")
                (conf / "mime.types").symlink_to(outside)
                with self.assertRaisesRegex(RuntimeError, "conf fixture"):
                    assets.fixture_source()
