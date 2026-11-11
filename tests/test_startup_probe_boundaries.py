"""Verify probe deadlines and cleanup without launching containers or local servers."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    """Load an opt-in probe without invoking its command-line entry point."""
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StartupProbeBoundaryTests(unittest.TestCase):
    """Keep diagnostic waits bounded and cleanup active after runtime failures."""

    def test_global_manager_log_timeout_still_stops_container_and_server(self):
        """A stalled log read cannot skip bounded stop and mock-server cleanup."""
        probe = load("tools/longhorn/test_global_manager_startup.py")
        server = MagicMock(server_port=12345)
        container = "c" * 64
        with (
            patch.object(probe.http.server, "ThreadingHTTPServer", return_value=server),
            patch.object(probe.threading, "Thread"),
            patch.object(
                probe.subprocess,
                "check_output",
                side_effect=[container + "\n", probe.subprocess.TimeoutExpired("podman logs", 10)],
            ) as command,
            patch.object(probe.subprocess, "run") as stop,
        ):
            with self.assertRaises(probe.subprocess.TimeoutExpired):
                probe.main()
        self.assertEqual([c.kwargs["timeout"] for c in command.call_args_list], [90, 10])
        self.assertTrue(all(c.kwargs["shell"] is False for c in command.call_args_list))
        self.assertEqual(command.call_args.args[0], ["/usr/bin/podman", "logs", container])
        stop.assert_called_once_with(
            ["/usr/bin/podman", "stop", "--time", "3", container],
            check=True,
            shell=False,
            timeout=10,
            stdout=probe.subprocess.DEVNULL,
        )
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()

    def test_global_manager_success_bounds_inspection_and_preserves_security_assertions(self):
        """A healthy synthetic startup still checks UID, capabilities and kernel guards."""
        probe = load("tools/longhorn/test_global_manager_startup.py")
        server = MagicMock(server_port=12345)
        connection = MagicMock()
        connection.getresponse.return_value.__enter__.return_value.status = 200
        state = "Uid:\t1000\nGid:\t1000\nCapEff:\t0000000000000000\nNoNewPrivs:\t1\nSeccomp:\t2"
        with (
            patch.object(probe.http.server, "ThreadingHTTPServer", return_value=server),
            patch.object(probe.threading, "Thread"),
            patch.object(probe.http.client, "HTTPConnection", return_value=connection),
            patch.object(
                probe.subprocess,
                "check_output",
                side_effect=["c" * 64, "Global controllers started; serving as leader", state],
            ) as command,
            patch.object(probe.subprocess, "run") as stop,
            redirect_stdout(io.StringIO()),
        ):
            probe.main()
        self.assertEqual([c.kwargs["timeout"] for c in command.call_args_list], [90, 10, 10])
        self.assertTrue(all(c.kwargs["shell"] is False for c in command.call_args_list))
        launch = command.call_args_list[0].args[0]
        self.assertEqual(launch[:2], ["/usr/bin/podman", "run"])
        for guard in ("--cap-drop=ALL", "--security-opt=no-new-privileges", "1000:1000"):
            self.assertIn(guard, launch)
        self.assertIn("/proc/1/status", command.call_args.args[0][-1])
        self.assertEqual(stop.call_args.kwargs["timeout"], 10)
        connection.close.assert_called_once()
        server.server_close.assert_called_once()

    def test_certificate_timeout_prevents_recurring_job_startup(self):
        """A failed synthetic certificate generation cannot start a server or container."""
        probe = load("tools/longhorn/test_recurring_job_startup.py")
        with (
            patch.object(
                probe.subprocess, "run", side_effect=probe.subprocess.TimeoutExpired("openssl", 30)
            ) as command,
            patch.object(probe.http.server, "ThreadingHTTPServer") as server,
        ):
            with self.assertRaises(probe.subprocess.TimeoutExpired):
                probe.main()
        self.assertEqual(command.call_args.args[0][:2], ["/usr/bin/openssl", "req"])
        self.assertEqual(command.call_args.kwargs["timeout"], 30)
        self.assertIs(command.call_args.kwargs["shell"], False)
        server.assert_not_called()

    def test_recurring_job_timeout_closes_both_mock_servers(self):
        """A bounded container failure must still close its synthetic API servers."""
        probe = load("tools/longhorn/test_recurring_job_startup.py")
        servers = [MagicMock(server_port=12345), MagicMock(server_port=12346)]
        with (
            patch.object(probe.http.server, "ThreadingHTTPServer", side_effect=servers),
            patch.object(probe.ssl, "SSLContext"),
            patch.object(probe.threading, "Thread"),
            patch.object(
                probe.subprocess,
                "run",
                side_effect=[
                    MagicMock(returncode=0),
                    probe.subprocess.TimeoutExpired("podman", 90),
                ],
            ) as command,
        ):
            with self.assertRaises(probe.subprocess.TimeoutExpired):
                probe.main()
        self.assertEqual([c.kwargs["timeout"] for c in command.call_args_list], [30, 90])
        self.assertTrue(all(c.kwargs["shell"] is False for c in command.call_args_list))
        self.assertEqual(command.call_args.args[0][:2], ["/usr/bin/podman", "run"])
        for server in servers:
            server.shutdown.assert_called_once()
            server.server_close.assert_called_once()

    def test_postgres_option_like_image_fails_before_runtime(self):
        """An image selector cannot become an extra Podman option."""
        probe = load("tools/postgres/test_permission_init_caps.py")
        for image in ("", "--privileged", "--volume=/etc:/host"):
            with (
                self.subTest(image=image),
                patch("sys.argv", ["probe", "--image=" + image]),
                patch.object(probe.subprocess, "run") as runtime,
                redirect_stderr(io.StringIO()),
            ):
                with self.assertRaises(SystemExit) as error:
                    probe.main()
                self.assertEqual(error.exception.code, 2)
                runtime.assert_not_called()
