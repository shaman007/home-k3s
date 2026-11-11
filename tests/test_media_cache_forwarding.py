"""A media-cache port-forward must announce a bounded local endpoint and become usable."""

from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


@contextmanager
def announced_pipe(data):
    """Expose a real pipe, retaining the writer to model a live but quiet child."""
    reader, writer = os.pipe()
    try:
        if data:
            os.write(writer, data)
        with os.fdopen(reader, "rb") as stream:
            yield SimpleNamespace(stdout=stream, poll=MagicMock(return_value=None))
    finally:
        os.close(writer)


class MediaCacheForwardingTests(unittest.TestCase):
    """Exercise real pipe readiness without starting processes, servers or network clients."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "forwarding_probe",
            Path(__file__).resolve().parents[1] / "tools/check_mastodon_media_cache.py",
        )
        self.probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.probe)

    def test_quiet_and_partial_announcements_expire_without_connecting(self):
        """A child keeping stdout open cannot hang an empty or unterminated announcement."""
        for data in (b"", b"Forwarding from 127.0.0.1:1234"):
            with (
                self.subTest(data=data),
                announced_pipe(data) as process,
                patch.object(self.probe.socket, "create_connection") as connect,
            ):
                with self.assertRaisesRegex(RuntimeError, "announcement timed out"):
                    self.probe.forwarded_port(process, timeout=0.03)
                connect.assert_not_called()

    def test_invalid_announcements_are_rejected_before_connecting(self):
        """Reject malformed, remote, invalid-port, wrong-target and oversized announcements."""
        for line in (
            b"private diagnostic\n",
            b"Forwarding from 0.0.0.0:1234 -> 8080\n",
            b"Forwarding from 127.0.0.1:0 -> 8080\n",
            b"Forwarding from 127.0.0.1:65536 -> 8080\n",
            b"Forwarding from 127.0.0.1:1234 -> 9000\n",
        ):
            with (
                self.subTest(length=len(line)),
                announced_pipe(line) as process,
                patch.object(self.probe.socket, "create_connection") as connect,
            ):
                with self.assertRaisesRegex(RuntimeError, "loopback port-forward"):
                    self.probe.forwarded_port(process, timeout=0.1)
                connect.assert_not_called()

        with (
            announced_pipe(b"ready") as process,
            patch.object(self.probe.os, "read", side_effect=[b"x" * 3000, b"x" * 2000]),
            patch.object(self.probe.socket, "create_connection") as connect,
        ):
            with self.assertRaisesRegex(RuntimeError, "loopback port-forward"):
                self.probe.forwarded_port(process, timeout=0.1)
            connect.assert_not_called()

    def test_valid_announcement_requires_connection_and_live_child(self):
        """Only successful bounded connection readiness may return the announced port."""
        line = b"Forwarding from 127.0.0.1:12345 -> 8080\n"
        with announced_pipe(line) as process:
            with patch.object(self.probe.socket, "create_connection") as connect:
                self.assertEqual(self.probe.forwarded_port(process, timeout=0.1), 12345)
            self.assertEqual(connect.call_args.args, (("127.0.0.1", 12345),))
            self.assertGreater(connect.call_args.kwargs["timeout"], 0)
            self.assertLessEqual(connect.call_args.kwargs["timeout"], 0.1)
        with announced_pipe(line) as process:
            process.poll.return_value = 1
            with patch.object(self.probe.socket, "create_connection") as connect:
                with self.assertRaisesRegex(RuntimeError, "port-forward exited"):
                    self.probe.forwarded_port(process, timeout=0.1)
                connect.assert_not_called()

    def test_unreachable_forward_never_returns_a_usable_port(self):
        """An announcement alone cannot make repeated failed connections look ready."""
        with (
            announced_pipe(b"Forwarding from 127.0.0.1:12345 -> 8080\n") as process,
            patch.object(self.probe.socket, "create_connection", side_effect=OSError) as connect,
        ):
            with self.assertRaisesRegex(RuntimeError, "readiness timed out"):
                self.probe.forwarded_port(process, timeout=0.03)
            connect.assert_called()
