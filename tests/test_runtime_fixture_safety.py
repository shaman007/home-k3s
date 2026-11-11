"""Check opt-in runtime fixture safety without launching processes or contacting pods."""

from contextlib import contextmanager
from functools import partial
import importlib.util
import json
import io
import subprocess
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from nginx_fixture import fixture_binary

import test_mastodon_bounce_filter_runtime as bounce
import test_static_assets_runtime as assets
import test_media_cache_runtime as media


@contextmanager
def tracked_directory(allocate, directories, **options):
    """Record a real private directory while preserving its context cleanup contract."""
    with allocate(**options) as directory:
        directories.append(Path(directory))
        yield directory


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

    def test_binary_selection_never_uses_path_or_nonexecutable_files(self):
        """Require a deliberate executable file while preserving paths with spaces."""
        with tempfile.TemporaryDirectory(prefix="nginx-binary-check-") as directory:
            root = Path(directory)
            binary = root / "selected nginx"
            binary.write_text("#!/bin/sh\nexit 0\n")
            for selected in (
                None,
                "nginx",
                "./nginx",
                str(root),
                str(root / "missing"),
                str(binary),
            ):
                with self.subTest(selected=selected):
                    with self.assertRaisesRegex(RuntimeError, "absolute executable"):
                        fixture_binary(selected)
            binary.chmod(0o700)
            with patch.dict("os.environ", {"PATH": str(root)}):
                self.assertEqual(fixture_binary(str(binary)), str(binary.resolve()))
            alias = root / "alias"
            alias.symlink_to(binary)
            self.assertEqual(fixture_binary(str(alias)), str(binary.resolve()))

    def test_invalid_binary_fails_before_resource_allocation(self):
        """Both suites reject PATH-selected executables before starting local servers."""
        for module, parent in (
            (assets, assets.StaticAssetsRuntimeTest),
            (media, media.MediaCacheRuntimeTest),
        ):
            with (
                self.subTest(suite=parent.__name__),
                patch.object(module, "BINARY", "nginx"),
                patch.object(assets, "fixture_source", return_value=Path.cwd()),
                patch.object(module.tempfile, "TemporaryDirectory") as temp,
                patch.object(module.subprocess, "Popen") as process,
            ):
                with self.assertRaisesRegex(RuntimeError, "absolute executable"):
                    parent.setUpClass()
                temp.assert_not_called()
                process.assert_not_called()

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


class RuntimeResourceCleanupTests(unittest.TestCase):
    """Clean partial setup without launching servers, subprocesses or cluster commands."""

    def test_runtime_teardown_reaps_processes_and_closes_logs(self):
        """Both runtime suites close logs after normal exit or the bounded kill fallback."""
        for parent in (assets.StaticAssetsRuntimeTest, media.MediaCacheRuntimeTest):
            for times_out in (False, True):
                with self.subTest(suite=parent.__name__, timeout=times_out):
                    runtime = type("DisposableTeardown", (parent,), {})
                    process = MagicMock()
                    if times_out:
                        process.wait.side_effect = [subprocess.TimeoutExpired("fixture", 5), None]
                    log = io.StringIO()
                    runtime.processes = [process]
                    runtime.logs = [log]
                    runtime.tearDownClass()
                    process.terminate.assert_called_once()
                    self.assertEqual(process.wait.call_args_list[0].kwargs, {"timeout": 5})
                    self.assertTrue(log.closed)
                    if times_out:
                        process.kill.assert_called_once()
                        self.assertEqual(process.wait.call_count, 2)
                        self.assertEqual(process.wait.call_args.args, ())
                    else:
                        process.kill.assert_not_called()
                        self.assertEqual(process.wait.call_count, 1)

    def test_bind_failure_releases_private_directory(self):
        """Server construction failures cannot leak either runtime suite's temporary tree."""
        allocate = tempfile.TemporaryDirectory
        for module, parent, owner, attribute in (
            (assets, assets.StaticAssetsRuntimeTest, assets, "PHPServer"),
            (media, media.MediaCacheRuntimeTest, media.http.server, "ThreadingHTTPServer"),
        ):
            with self.subTest(module=module.__name__):
                runtime = type("DisposableRuntime", (parent,), {})
                directories = []

                with (
                    patch.object(assets, "fixture_source", return_value=Path.cwd()),
                    patch.object(module, "fixture_binary", return_value="/fixture/nginx"),
                    patch.object(
                        module.tempfile,
                        "TemporaryDirectory",
                        side_effect=partial(tracked_directory, allocate, directories),
                    ),
                    patch.object(owner, attribute, side_effect=OSError("synthetic bind failure")),
                ):
                    try:
                        with self.assertRaisesRegex(OSError, "bind failure"):
                            runtime.setUpClass()
                    finally:
                        runtime.doClassCleanups()
                self.assertEqual(len(directories), 1)
                self.assertFalse(directories[0].exists())

    def test_nginx_check_timeout_closes_resources_without_starting_workers(self):
        """Both configuration-check timeouts release logs, directories and local servers."""
        for module, parent, owner, attribute in (
            (assets, assets.StaticAssetsRuntimeTest, assets, "PHPServer"),
            (media, media.MediaCacheRuntimeTest, media.http.server, "ThreadingHTTPServer"),
        ):
            with self.subTest(suite=parent.__name__):
                runtime = type("DisposableCheckTimeout", (parent,), {})
                server = MagicMock()
                server.__enter__.return_value = server
                server.server_address = ("127.0.0.1", 12345)
                server.server_port = 12345
                sock = MagicMock()
                sock.__enter__.return_value = sock
                sock.getsockname.return_value = ("127.0.0.1", 12346)
                with (
                    patch.object(module, "fixture_binary", return_value="/fixture/nginx"),
                    patch.object(assets, "fixture_source", return_value=Path.cwd()),
                    patch.object(assets.shutil, "copy"),
                    patch.object(owner, attribute, return_value=server),
                    patch.object(module.threading, "Thread"),
                    patch.object(module.socket, "socket", return_value=sock),
                    patch.object(
                        module.subprocess, "run", side_effect=subprocess.TimeoutExpired("nginx", 15)
                    ) as check,
                    patch.object(module.subprocess, "Popen") as workers,
                ):
                    try:
                        with self.assertRaises(subprocess.TimeoutExpired):
                            runtime.setUpClass()
                    finally:
                        runtime.doClassCleanups()
                self.assertEqual(check.call_args.args[0][0], "/fixture/nginx")
                self.assertIn("-t", check.call_args.args[0])
                self.assertEqual(check.call_args.kwargs["timeout"], 15)
                self.assertIs(check.call_args.kwargs["shell"], False)
                workers.assert_not_called()
                self.assertTrue(all(log.closed for log in runtime.logs))
                directory = runtime.__dict__["base" if module is assets else "directory"]
                self.assertFalse(directory.exists())
                server.shutdown.assert_called_once()
                server.__exit__.assert_called_once()

    def test_config_failure_stops_and_closes_origin(self):
        """A config parse failure before the startup loop still shuts down the origin."""
        runtime = type("DisposableMedia", (media.MediaCacheRuntimeTest,), {})
        server = MagicMock()
        server.__enter__.return_value = server
        with (
            patch.object(media, "fixture_binary", return_value="/fixture/nginx"),
            patch.object(media.http.server, "ThreadingHTTPServer", return_value=server),
            patch.object(media.threading, "Thread") as thread,
            patch.object(media.yaml, "safe_load_all", side_effect=ValueError("synthetic config")),
        ):
            try:
                with self.assertRaisesRegex(ValueError, "synthetic config"):
                    runtime.setUpClass()
            finally:
                runtime.doClassCleanups()
        thread.return_value.start.assert_called_once()
        server.shutdown.assert_called_once()
        server.__exit__.assert_called_once()
        self.assertFalse(runtime.directory.exists())

    def test_inventory_timeout_prevents_port_forward(self):
        """A stalled inventory fails before a tunnel or fixture request starts."""
        spec = importlib.util.spec_from_file_location(
            "media_inventory_timeout", assets.ROOT / "tools/check_mastodon_media_cache.py"
        )
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        with (
            patch("sys.argv", ["media-probe"]),
            patch.object(
                probe.subprocess, "run", side_effect=subprocess.TimeoutExpired("kubectl", 30)
            ) as command,
            patch.object(probe.subprocess, "Popen") as forward,
            patch.object(probe, "fetch") as fetch,
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                probe.main()
        command.assert_called_once_with(
            (
                "kubectl get pods -n seaweedfs -l app=mastodon-media-cache "
                "-o json --request-timeout=15s"
            ).split(),
            check=True,
            capture_output=True,
            shell=False,
            timeout=30,
        )
        forward.assert_not_called()
        fetch.assert_not_called()

    def test_port_forward_failure_terminates_and_exits_context(self):
        """A malformed forwarding announcement still reaps the child and closes its context."""
        spec = importlib.util.spec_from_file_location(
            "media_probe", assets.ROOT / "tools/check_mastodon_media_cache.py"
        )
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        process = MagicMock()
        process.__enter__.return_value = process
        pods = {
            "items": [
                {"metadata": {"name": name}, "status": {"phase": "Running"}}
                for name in ("first", "second")
            ]
        }
        response = MagicMock(stdout=json.dumps(pods).encode())
        with (
            patch.object(probe.subprocess, "run", return_value=response),
            patch.object(probe.subprocess, "Popen", return_value=process),
            patch.object(probe, "forwarding_announcement", return_value=b"malformed"),
            patch("sys.argv", ["media-probe"]),
        ):
            with self.assertRaisesRegex(RuntimeError, "loopback port-forward"):
                probe.main()
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)
        process.__exit__.assert_called_once()


class MediaFixtureVerificationTests(unittest.TestCase):
    """Reject cache success when revocation, integrity or bypass checks disagree."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "media_verification", assets.ROOT / "tools/check_mastodon_media_cache.py"
        )
        self.probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.probe)
        self.args = SimpleNamespace(
            path="/mastodon/cache-pilot/fixture.txt",
            expect_missing=False,
            expect_private=False,
            expect_body_sha256=None,
        )

    def test_revocation_requires_exact_expected_status(self):
        """A cached success cannot substitute for origin missing/private status."""
        for option, status in (("expect_missing", 404), ("expect_private", 403)):
            with self.subTest(option=option):
                setattr(self.args, option, True)
                with patch.object(self.probe, "fetch", return_value=(200, "HIT", "body")):
                    with self.assertRaisesRegex(RuntimeError, f"expected {status}"):
                        self.probe.check_fixture("fixture", 1234, self.args)
                setattr(self.args, option, False)

    def test_hit_and_body_integrity_are_both_required(self):
        """A repeat response must be a cache hit with matching content and expected digest."""
        for second in ((200, "MISS", "body"), (200, "HIT", "changed"), (500, "HIT", "body")):
            with (
                self.subTest(second=second),
                patch.object(self.probe, "fetch", side_effect=[(200, "MISS", "body"), second]),
            ):
                with self.assertRaisesRegex(RuntimeError, "identical body not verified"):
                    self.probe.check_fixture("fixture", 1234, self.args)
        self.args.expect_body_sha256 = "expected"
        with patch.object(
            self.probe, "fetch", side_effect=[(200, "MISS", "body"), (200, "HIT", "body")]
        ):
            with self.assertRaisesRegex(RuntimeError, "current object"):
                self.probe.check_fixture("fixture", 1234, self.args)

    def test_every_bypass_variant_is_checked(self):
        """Query, Range and Cookie requests must each bypass the cache."""
        for failing_index in range(3):
            responses = [(200, "MISS", "body"), (200, "HIT", "body")]
            responses.extend((206, "BYPASS", "partial") for _ in range(3))
            responses[2 + failing_index] = (200, "HIT", "body")
            with (
                self.subTest(index=failing_index),
                patch.object(self.probe, "fetch", side_effect=responses) as fetch,
            ):
                with self.assertRaisesRegex(RuntimeError, "bypass not verified"):
                    self.probe.check_fixture("fixture", 1234, self.args)
            self.assertEqual(fetch.call_count, 3 + failing_index)
