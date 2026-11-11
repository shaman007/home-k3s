"""Probe process execution must ignore hostile PATH entries and preserve command contracts."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/security"))
SPEC = importlib.util.spec_from_file_location(
    "probe_runner", ROOT / "tools/security/probe_commands.py"
)
commands = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(commands)

# Timeout, subprocess check, wrapper call style, expected exception on failure.
PROBES = {
    "test_backup_collabora_guards.py": (120, True, "list", subprocess.CalledProcessError),
    "test_frr_helper_guards.py": (90, False, "splat", AssertionError),
    "test_gpu_config_init_guards.py": (90, False, "splat", AssertionError),
    "test_hister_readonly_root.py": (90, False, "list", AssertionError),
    "test_infra_guard_runtime.py": (120, False, "splat", AssertionError),
    "test_lenka_mysql_guards.py": (180, False, "splat", RuntimeError),
    "test_longhorn_prepull_guards.py": (90, False, "splat", AssertionError),
    "test_mail_capability_guards.py": (90, True, "list", subprocess.CalledProcessError),
    "test_metallb_speaker_runtime.py": (90, False, "splat", AssertionError),
    "test_nextcloud_alloy_readonly.py": (60, False, "list", AssertionError),
    "test_nginx_readonly_content.py": (90, False, "list", AssertionError),
    "test_permission_helper_guards.py": (60, False, "label", AssertionError),
    "test_plex_capability_guards.py": (90, False, "list", AssertionError),
}


def load_probe(filename):
    """Import one guarded probe entry point without executing its main function."""
    spec = importlib.util.spec_from_file_location(
        "fixture_" + Path(filename).stem, ROOT / "tools/security" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke(module, style):
    """Call the wrapper using its existing list, positional, or labeled interface."""
    if style == "splat":
        return module.run("fixture")
    if style == "label":
        return module.run(["podman", "fixture"], "fixture label")
    return module.run(["podman", "fixture"])


class ProbeCommandTests(unittest.TestCase):
    """Require explicit argv, trusted executable resolution, bounded waits and no implicit shell."""

    def test_invalid_arguments_fail_before_process_creation(self):
        """Reject shell strings, byte strings, empty sequences and non-text arguments."""
        for arguments in ["podman run fixture", b"podman", [], ["podman", 1]]:
            with self.subTest(arguments=arguments), patch.object(commands.subprocess, "run") as run:
                with self.assertRaises(TypeError):
                    commands.run_command(arguments)
                run.assert_not_called()

    def test_resolution_ignores_environment_path_and_preserves_arguments(self):
        """Use system directories while retaining shell metacharacters as literal arguments."""
        expected = subprocess.CompletedProcess([], 0, "fixture", "")
        payload = "literal; $(printf accidental-shell)"
        with (
            patch.dict(os.environ, {"PATH": "/untrusted/fixture"}),
            patch.object(commands.shutil, "which", return_value="/usr/bin/podman") as resolve,
            patch.object(commands.subprocess, "run", return_value=expected) as run,
        ):
            actual = commands.run_command(
                ["podman", payload], timeout=7, check=True, capture_output=True, text=True
            )
        self.assertIs(actual, expected)
        resolve.assert_called_once_with("podman", path="/usr/bin:/bin")
        run.assert_called_once_with(
            ["/usr/bin/podman", payload],
            shell=False,
            timeout=7,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_relative_executables_and_process_overrides_are_rejected(self):
        """Do not accept working-directory executables or overrides of the execution boundary."""
        for executable in ["./podman", "fixture/podman"]:
            with (
                self.subTest(executable=executable),
                patch.object(commands.subprocess, "run") as run,
            ):
                with self.assertRaises(ValueError):
                    commands.run_command([executable])
                run.assert_not_called()
        for option in ["shell", "executable", "env"]:
            with self.subTest(option=option), self.assertRaises(TypeError):
                commands.run_command(["podman"], **{option: True})

    def test_missing_executable_and_invalid_timeout_fail_before_execution(self):
        """Require an available system command and a finite positive timeout."""
        with (
            patch.object(commands.shutil, "which", return_value=None),
            patch.object(commands.subprocess, "run") as run,
        ):
            with self.assertRaises(FileNotFoundError):
                commands.run_command(["fixture"])
            run.assert_not_called()
        for timeout in [None, 0, -1, float("inf"), float("nan")]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                commands.run_command(["fixture"], timeout=timeout)

    def test_explicit_absolute_executable_and_paths_are_supported(self):
        """Allow an intentionally supplied binary path without consulting any search path."""
        with (
            patch.object(commands.shutil, "which") as resolve,
            patch.object(commands.subprocess, "run") as run,
        ):
            commands.run_command([Path("/usr/bin/fixture"), Path("/fixture/input")])
        resolve.assert_not_called()
        run.assert_called_once_with(
            ["/usr/bin/fixture", "/fixture/input"], shell=False, timeout=90, check=False
        )

    def test_process_errors_and_timeouts_are_not_swallowed(self):
        """Propagate subprocess failures so callers retain their established cleanup behavior."""
        failures = [
            subprocess.CalledProcessError(3, ["fixture"], output="out", stderr="err"),
            subprocess.TimeoutExpired(["fixture"], 7),
        ]
        for failure in failures:
            with (
                self.subTest(kind=type(failure).__name__),
                patch.object(commands.subprocess, "run", side_effect=failure),
                self.assertRaises(type(failure)) as caught,
            ):
                commands.run_command(["/usr/bin/fixture"], check=True)
            self.assertIs(caught.exception, failure)

    def test_literal_arguments_round_trip_through_a_real_process(self):
        """Verify the real child receives metacharacters without host-shell interpretation."""
        payload = "literal; $(printf unexpected)"
        result = commands.run_command(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", payload],
            timeout=7,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), payload)


class ProbeWrapperCompatibilityTests(unittest.TestCase):
    """Retain each probe's existing return values, failure classes and explicit timeouts."""

    def test_all_wrappers_preserve_success_contracts(self):
        """Keep capture/check flags and distinguish raw versus stripped stdout."""
        process = subprocess.CompletedProcess(["fixture"], 0, "  output\n", "")
        for filename, (timeout, check, style, _) in PROBES.items():
            module = load_probe(filename)
            with (
                self.subTest(filename=filename),
                patch.object(module, "run_command", return_value=process) as run,
            ):
                result = invoke(module, style)
            self.assertEqual(result, process.stdout if style == "label" else process.stdout.strip())
            run.assert_called_once_with(
                ["podman", "fixture"], capture_output=True, text=True, timeout=timeout, check=check
            )

    def test_all_wrappers_preserve_failure_classes(self):
        """Keep explicit error checks and subprocess check=True behavior intact."""
        process = subprocess.CompletedProcess(["fixture"], 3, "out fixture", "err fixture")
        for filename, (_, check, style, failure) in PROBES.items():
            module = load_probe(filename)
            outcome = subprocess.CalledProcessError(3, process.args, process.stdout, process.stderr)
            with (
                self.subTest(filename=filename),
                patch.object(
                    module,
                    "run_command",
                    side_effect=outcome if check else None,
                    return_value=process,
                ),
            ):
                with self.assertRaises(failure):
                    invoke(module, style)

    def test_nonchecking_wrappers_return_the_failed_process(self):
        """Retain intentionally inspected failures instead of converting them to exceptions."""
        process = subprocess.CompletedProcess(["fixture"], 3, "out fixture", "err fixture")
        for filename in [
            "test_frr_helper_guards.py",
            "test_gpu_config_init_guards.py",
            "test_metallb_speaker_runtime.py",
        ]:
            module = load_probe(filename)
            with (
                self.subTest(filename=filename),
                patch.object(module, "run_command", return_value=process),
            ):
                self.assertIs(module.run("fixture", check=False), process)


class NginxContentProbeTests(unittest.TestCase):
    """Retain content and runtime security checks while keeping regression tests offline."""

    def test_failed_nginx_start_removes_backend(self):
        """A partial startup must remove the already-created isolated backend."""
        probe = load_probe("test_nginx_readonly_content.py")
        target = probe.NginxTarget("fixture", "deployment", "config", "/content", "nginx", "php")
        with (
            patch.object(probe, "load_configuration", return_value=("image", "config")),
            patch.object(probe, "prepare_fixtures", return_value=("content", "config", "mock")),
            patch.object(probe, "start_backend", return_value="backend"),
            patch.object(probe, "start_nginx", side_effect=RuntimeError("startup failed")),
            patch.object(
                probe, "run_command", return_value=subprocess.CompletedProcess([], 0, "", "")
            ),
            patch.object(probe, "run") as run,
            patch("builtins.print"),
        ):
            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                probe.check(target)
        run.assert_called_once_with(["podman", "rm", "-f", "backend"])

    def test_guard_checks_reject_writable_mount_and_missing_process_guards(self):
        """Every required process guard remains mandatory alongside read-only content."""
        probe = load_probe("test_nginx_readonly_content.py")
        guards = [
            "CapEff:\t0000000000000000",
            "CapBnd:\t0000000000000000",
            "NoNewPrivs:\t1",
            "Seccomp:\t2",
        ]
        with patch.object(probe, "run", return_value="1 2 3 4 /content rw") as run:
            with self.assertRaises(AssertionError):
                probe.check_runtime_guards("nginx", "/content")
            self.assertEqual(run.call_count, 1)
        for missing in guards:
            with self.subTest(missing=missing):
                status = "\n".join(value for value in guards if value != missing)
                with patch.object(probe, "run", side_effect=["1 2 3 4 /content ro", "", status]):
                    with self.assertRaises(AssertionError):
                        probe.check_runtime_guards("nginx", "/content")

    def test_forwarded_body_size_must_match(self):
        """A successful HTTP status cannot hide a truncated FastCGI upload."""
        probe = load_probe("test_nginx_readonly_content.py")
        responses = [
            {"status": 200, "body": "body {color:blue;}\n"},
            {"status": 200, "body": '{"fastcgi":true,"received_bytes":0}'},
            {"status": 200, "body": '{"fastcgi":true,"received_bytes":1}'},
        ]
        with patch.object(probe, "request", side_effect=responses) as request:
            with self.assertRaises(AssertionError):
                probe.check_responses("nextcloud", "backend")
        self.assertEqual(request.call_args.args, ("backend", "POST", "/index.php", 2 * 1024 * 1024))


class SplitRuntimeProbeTests(unittest.TestCase):
    """Retain cleanup and runtime rejection behavior in the split startup probes."""

    def test_backup_roundtrip_failure_removes_container(self):
        """An SSH/rsync verification failure cannot strand the backup fixture."""
        probe = load_probe("test_backup_collabora_guards.py")
        with (
            patch.object(probe, "start_backup", return_value="backup-fixture"),
            patch.object(probe, "check_backup_roundtrip", side_effect=AssertionError("roundtrip")),
            patch.object(probe, "run") as run,
        ):
            with self.assertRaisesRegex(AssertionError, "roundtrip"):
                probe.check_backup()
        run.assert_called_once_with(["podman", "rm", "-f", "backup-fixture"])

    def test_collabora_discovery_failure_removes_container(self):
        """Failed readiness still removes the document-server fixture."""
        probe = load_probe("test_backup_collabora_guards.py")
        with (
            patch.object(
                probe, "run", side_effect=["collabora-fixture", "127.0.0.1:12345", "logs", ""]
            ) as run,
            patch.object(probe.urllib.request, "urlopen", side_effect=OSError("not ready")),
            patch.object(probe.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Collabora discovery failed"):
                probe.check_collabora()
        self.assertEqual(run.call_args.args[0], ["podman", "rm", "-f", "collabora-fixture"])

    def test_alloy_partial_volume_setup_removes_allocated_volumes(self):
        """Preparation failures retain cleanup ownership for every created state volume."""
        probe = load_probe("test_nextcloud_alloy_readonly.py")

        def prepare(volumes):
            volumes.extend(["state-fixture", "run-fixture"])
            raise RuntimeError("synthetic volume setup failure")

        with (
            patch.object(probe, "prepare_volumes", side_effect=prepare),
            patch.object(probe, "run") as run,
        ):
            with self.assertRaisesRegex(RuntimeError, "volume setup failure"):
                probe.main()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [["podman", "volume", "rm", name] for name in ("state-fixture", "run-fixture")],
        )

    def test_alloy_rejects_writable_root_before_checkpoint_checks(self):
        """A writable root filesystem must fail even when the content mount is read-only."""
        probe = load_probe("test_nextcloud_alloy_readonly.py")
        with patch.object(probe, "run", return_value="1 2 3 4 / rw\n1 2 3 4 /nextcloud ro") as run:
            with self.assertRaises(AssertionError):
                probe.check_runtime("alloy-fixture", ["state-fixture", "run-fixture"])
        run.assert_called_once_with(["podman", "exec", "alloy-fixture", "cat", "/proc/1/mountinfo"])
