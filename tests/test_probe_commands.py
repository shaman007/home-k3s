"""Probe process execution must ignore hostile PATH entries and preserve command contracts."""

import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

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
            patch.object(probe.http.client, "HTTPConnection", side_effect=OSError("not ready")),
            patch.object(probe.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Collabora discovery failed"):
                probe.check_collabora()
        self.assertEqual(run.call_args.args[0], ["podman", "rm", "-f", "collabora-fixture"])

    def test_collabora_redirect_is_rejected_without_following_or_leaking(self):
        """A redirect cannot satisfy discovery even with a plausible body."""
        probe = load_probe("test_backup_collabora_guards.py")
        connection = MagicMock()
        response = connection.getresponse.return_value.__enter__.return_value
        response.status = 302
        response.read.return_value = b"wopi-discovery"
        with (
            patch.object(probe, "run", side_effect=["fixture", "127.0.0.1:12345", "logs", ""]),
            patch.object(probe.http.client, "HTTPConnection", return_value=connection) as connect,
            patch.object(probe.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Collabora discovery failed"):
                probe.check_collabora()
        self.assertEqual(connect.call_count, 60)
        self.assertTrue(all(call.args == ("127.0.0.1", 12345) for call in connect.call_args_list))
        self.assertEqual(connection.close.call_count, 60)
        self.assertEqual(connection.getresponse.return_value.__exit__.call_count, 60)
        response.read.assert_not_called()
        self.assertTrue(
            all(
                call.args == ("GET", "/hosting/discovery")
                for call in connection.request.call_args_list
            )
        )

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


class GpuAndMailProbeTests(unittest.TestCase):
    """Keep GPU security boundaries and disposable mail protocol cleanup intact."""

    def test_gpu_rejections_always_remove_mock(self):
        """Incorrect permissions or missing process guards still remove the node fixture."""
        probe = load_probe("test_gpu_config_init_guards.py")
        for expected, output in (
            (None, "unexpected success"),
            ("/available-configs/default", "/available-configs/default"),
        ):
            with self.subTest(expected=expected):
                result = subprocess.CompletedProcess([], 0, output, "")
                with (
                    patch.object(probe, "run", side_effect=["mock-fixture", result, ""]) as run,
                    patch.object(probe.time, "sleep"),
                ):
                    with self.assertRaises(AssertionError):
                        probe.check_oneshot(
                            Path("fixture"),
                            Path("fixture/source"),
                            ("default", expected, "1000:1000", "default", "0777"),
                        )
                self.assertEqual(run.call_args.args, ("rm", "-f", "mock-fixture"))

    def test_smtp_transcript_never_submits_mail(self):
        """Keep STARTTLS before AUTH and restrict the transcript to handshake/probe commands."""
        probe = load_probe("test_mail_capability_guards.py")
        plain, tls, context = MagicMock(), MagicMock(), MagicMock()
        before = io.BytesIO(b"220 hello\r\n250 hello\r\n220 upgrade\r\n")
        after = io.BytesIO(b"250 hello\r\n235 authenticated\r\n250 okay\r\n221 bye\r\n")
        plain.makefile.return_value = before
        tls.makefile.return_value = after
        context.wrap_socket.return_value = tls
        with (
            patch.object(probe.socket, "create_connection", return_value=plain),
            patch.object(probe, "port", return_value=12345),
        ):
            probe.check_smtp("dovecot-fixture", context)
        self.assertEqual(
            [call.args[0].split(b" ", 1)[0] for call in plain.sendall.call_args_list],
            [b"PROXY", b"EHLO", b"STARTTLS\r\n"],
        )
        self.assertEqual(
            [call.args[0].split(b" ", 1)[0] for call in tls.sendall.call_args_list],
            [b"EHLO", b"AUTH", b"NOOP\r\n", b"QUIT\r\n"],
        )
        context.wrap_socket.assert_called_once_with(plain, server_hostname="guard.invalid")
        self.assertTrue(before.closed)
        self.assertTrue(after.closed)
        plain.close.assert_called_once()
        tls.close.assert_called_once()

    def test_smtp_failure_closes_buffered_streams(self):
        """Reject bad greetings or authentication and close both file wrappers on failure."""
        probe = load_probe("test_mail_capability_guards.py")
        for phase in ("greeting", "authentication"):
            with self.subTest(phase=phase):
                plain, tls, context = MagicMock(), MagicMock(), MagicMock()
                before = io.BytesIO(
                    b"500 denied\r\n"
                    if phase == "greeting"
                    else b"220 hello\r\n250 hello\r\n220 upgrade\r\n"
                )
                after = io.BytesIO(b"250 hello\r\n535 rejected\r\n")
                plain.makefile.return_value = before
                tls.makefile.return_value = after
                context.wrap_socket.return_value = tls
                with (
                    patch.object(probe.socket, "create_connection", return_value=plain),
                    patch.object(probe, "port", return_value=12345),
                ):
                    with self.assertRaises(AssertionError):
                        probe.check_smtp("dovecot-fixture", context)
                self.assertTrue(before.closed)
                plain.close.assert_called_once()
                if phase == "greeting":
                    context.wrap_socket.assert_not_called()
                    self.assertFalse(after.closed)
                    after.close()
                else:
                    self.assertTrue(after.closed)
                    tls.close.assert_called_once()

    def test_partial_postfix_setup_cleans_dovecot_and_volume(self):
        """A failed Postfix setup cannot leave its allocated volume or the first daemon."""
        probe = load_probe("test_mail_capability_guards.py")

        def fail_postfix(_directory, _dovecot, volumes):
            volumes.append("postfix-state-fixture")
            raise RuntimeError("synthetic postfix failure")

        with (
            patch.object(probe, "create_certificate"),
            patch.object(probe, "start_dovecot", return_value="dovecot-fixture"),
            patch.object(probe.ssl, "create_default_context"),
            patch.object(probe, "check_imap"),
            patch.object(probe, "start_postfix", side_effect=fail_postfix),
            patch.object(probe, "run", side_effect=["1777", "", ""]) as run,
            patch.object(
                probe, "run_command", return_value=subprocess.CompletedProcess([], 0, "", "")
            ),
            patch("builtins.print"),
        ):
            with self.assertRaisesRegex(RuntimeError, "postfix failure"):
                probe.main()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list][-2:],
            [
                ["podman", "rm", "-f", "dovecot-fixture"],
                ["podman", "volume", "rm", "postfix-state-fixture"],
            ],
        )


class PermissionAndPlexProbeTests(unittest.TestCase):
    """Retain reviewed grants, nonempty transcodes and disposable-resource cleanup."""

    def permission_case(self, probe, caps):
        """Build a synthetic permission-check contract for the existing Hister init helper."""
        return probe.PermissionCase(
            path="hister/deployment-hister.yaml",
            name="fix-data-permissions",
            caps=caps,
            mount="/data",
            setup="true",
            checks="true",
            expected_mask="0000000000000003",
        )

    def test_unreviewed_permission_grants_fail_before_execution(self):
        """A case asking for unreviewed capabilities cannot launch its helper."""
        probe = load_probe("test_permission_helper_guards.py")
        case = self.permission_case(probe, ["SYS_ADMIN"])
        with patch.object(probe, "run") as run:
            with self.assertRaises(AssertionError):
                probe.helper(case)
        run.assert_not_called()

    def test_missing_permission_process_guards_fail(self):
        """A successful helper exit cannot compensate for missing capability/security flags."""
        probe = load_probe("test_permission_helper_guards.py")
        case = self.permission_case(probe, ["CHOWN", "DAC_OVERRIDE"])
        with patch.object(probe, "run", return_value="NoNewPrivs:\t1\nSeccomp:\t2"):
            with self.assertRaises(AssertionError):
                probe.helper(case)

    def test_zero_length_plex_transcode_fails(self):
        """Require actual nonempty media output after a successful transcoder exit."""
        probe = load_probe("test_plex_capability_guards.py")
        status = "CapBnd:\t00000000000000fb\nNoNewPrivs:\t1\nSeccomp:\t2"
        with patch.object(probe, "run", side_effect=[status, "", "0"]):
            with self.assertRaises(AssertionError):
                probe.check_transcode("plex-fixture")

    def test_plex_fixture_preparation_failure_removes_volume(self):
        """Media generation failures cannot strand the already allocated config volume."""
        probe = load_probe("test_plex_capability_guards.py")
        with (
            patch.object(probe, "run", side_effect=["plex-volume", ""]) as run,
            patch.object(
                probe, "prepare_fixture", side_effect=RuntimeError("synthetic media failure")
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic media failure"):
                probe.main()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [["podman", "volume", "create"], ["podman", "volume", "rm", "plex-volume"]],
        )


class FrrProbeSafetyTests(unittest.TestCase):
    """Preserve FRR fixture cleanup, exporter identity and authenticated API checks."""

    def test_failed_helper_copy_removes_created_image_container(self):
        """A copy failure must retain the temporary image container in cleanup ownership."""
        probe = load_probe("test_frr_helper_guards.py")
        with (
            patch.object(probe, "prepare_fixture", return_value=Path("synthetic-config")),
            patch.object(
                probe, "run", side_effect=["helper-image", OSError("copy failed"), ""]
            ) as run,
        ):
            with self.assertRaisesRegex(OSError, "copy failed"):
                probe.main()
        self.assertEqual(run.call_args.args, ("rm", "-f", "helper-image"))

    def test_exporter_guards_reject_wrong_uid_or_capabilities(self):
        """Exporter readiness cannot override UID, capability and no-new-privileges requirements."""
        probe = load_probe("test_frr_helper_guards.py")
        good = (
            "CapEff:\t0000000000000000\nCapBnd:\t0000000000000000\n"
            "NoNewPrivs:\t1\nSeccomp:\t2\nUid:\t100 100 100 100"
        )
        for output in (
            good.replace("Uid:\t100 100 100 100", "Uid:\t0 0 0 0"),
            good.replace("CapEff:\t0000000000000000", "CapEff:\t0000000000000002"),
            good.replace("NoNewPrivs:\t1", "NoNewPrivs:\t0"),
        ):
            with self.subTest(output=output), patch.object(probe, "run", return_value=output):
                with self.assertRaises(AssertionError):
                    probe.check_exporter_guards(["exporter-fixture"])

    def test_status_cache_requires_token_and_access_reviews(self):
        """Successful resource reads alone cannot satisfy authenticated status-cache checks."""
        probe = load_probe("test_frr_helper_guards.py")
        with (
            patch.object(
                probe,
                "run",
                side_effect=["pod-read resource-read", "true", "pod-read resource-read"],
            ),
            patch.object(probe.time, "sleep"),
        ):
            with self.assertRaises(AssertionError):
                probe.check_status_exporter("status-fixture", "api-fixture")


class LenkaMysqlGuardTests(unittest.TestCase):
    """Keep database guard failures ahead of allocation and independent of SQL readiness."""

    def test_invalid_configuration_fails_before_volume_allocation(self):
        """An unexpected capability grant cannot reach any container command."""
        probe = load_probe("test_lenka_mysql_guards.py")
        configuration = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "securityContext": {
                                    "runAsUser": 999,
                                    "runAsGroup": 999,
                                    "runAsNonRoot": True,
                                    "capabilities": {"drop": ["ALL"], "add": ["SYS_ADMIN"]},
                                }
                            }
                        ]
                    }
                }
            }
        }
        with (
            patch.object(probe.yaml, "safe_load", return_value=configuration),
            patch.object(probe, "run") as run,
        ):
            with self.assertRaises(AssertionError):
                probe.main()
        run.assert_not_called()

    def test_process_guards_reject_each_unsafe_field(self):
        """Healthy SQL cannot substitute for process identity and kernel security guards."""
        probe = load_probe("test_lenka_mysql_guards.py")
        fields = {
            "Uid": "999 999 999 999",
            "Gid": "999 999 999 999",
            "CapEff": "0",
            "CapPrm": "0",
            "CapBnd": "0",
            "NoNewPrivs": "1",
            "Seccomp": "2",
        }
        for name, value in (
            ("Uid", "0 0 0 0"),
            ("Gid", "0 0 0 0"),
            ("CapEff", "2"),
            ("CapPrm", "2"),
            ("CapBnd", "2"),
            ("NoNewPrivs", "0"),
            ("Seccomp", "0"),
        ):
            status = "\n".join(f"{key}: {item}" for key, item in {**fields, name: value}.items())
            with self.subTest(field=name), patch.object(probe, "run", return_value=status):
                with self.assertRaises(AssertionError):
                    probe.check_process_guards("fixture")


class HisterFixtureGuardTests(unittest.TestCase):
    """Retain allocation cleanup and read-only startup contracts in the Hister probe."""

    def test_fixture_preparation_failure_removes_volume(self):
        """A PDF/configuration failure must release the already allocated disposable volume."""
        probe = load_probe("test_hister_readonly_root.py")
        with (
            patch.object(probe, "load_configuration", return_value={}),
            patch.object(probe, "prepare_fixture", side_effect=OSError("fixture failed")),
            patch.object(probe, "run", side_effect=["hister-volume", "", ""]) as run,
        ):
            with self.assertRaisesRegex(OSError, "fixture failed"):
                probe.main()
        self.assertEqual(run.call_args.args[0], ["podman", "volume", "rm", "hister-volume"])

    def test_server_preserves_guards_and_replaces_only_local_base_url(self):
        """The isolated server keeps read-only identity guards and its synthetic URL override."""
        probe = load_probe("test_hister_readonly_root.py")
        server = {
            "image": "fixture-image",
            "env": [
                {"name": "HISTER__SERVER__BASE_URL", "value": "https://production.invalid/"},
                {"name": "HISTER_DATA_DIR", "value": "/data"},
            ],
        }
        with patch.object(probe, "run", return_value="fixture-container") as run:
            base, container = probe.start_server(server, "volume", Path("config"), Path("pdf"))
        argv = run.call_args.args[0]
        self.assertEqual(container, "fixture-container")
        for guard in (
            "--read-only",
            "--read-only-tmpfs=false",
            "--user=65532:65532",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
        ):
            self.assertIn(guard, base)
            self.assertIn(guard, argv)
        self.assertIn("HISTER__SERVER__BASE_URL=http://127.0.0.1:8080/", argv)
        self.assertIn("HISTER_DATA_DIR=/data", argv)
        self.assertNotIn("HISTER__SERVER__BASE_URL=https://production.invalid/", argv)


class MetallbSpeakerGuardTests(unittest.TestCase):
    """Keep responder initialization and projected-file denial checks fail-closed."""

    def test_positive_case_requires_both_responders_and_no_creation_failure(self):
        """NDP readiness cannot hide missing ARP or either responder's creation failure."""
        probe = load_probe("test_metallb_speaker_runtime.py")
        good = (
            "created ARP responder for interface fixture0; "
            "created NDP responder for interface fixture0"
        )
        for logs in (
            "created NDP responder for interface fixture0",
            good + "; failed to create ARP responder",
            good + "; failed to create NDP responder",
        ):
            with self.subTest(logs=logs), patch.object(probe, "run", return_value=logs):
                with self.assertRaises(AssertionError):
                    probe.check_speaker("fixture", True)
        with patch.object(probe, "run", return_value=good):
            probe.check_speaker("fixture", True)

    def test_negative_case_requires_the_projected_configuration_denial(self):
        """An unrelated permission error cannot satisfy the root-only configuration control."""
        probe = load_probe("test_metallb_speaker_runtime.py")
        with patch.object(probe, "run", return_value="unrelated: permission denied"):
            with self.assertRaises(AssertionError):
                probe.check_speaker("fixture", False)
        with patch.object(probe, "run", return_value="excludel2.yaml: permission denied"):
            probe.check_speaker("fixture", False)
