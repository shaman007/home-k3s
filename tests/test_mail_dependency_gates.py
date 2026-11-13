"""Mail probes: real wire protocols, outages, preservation and fail-closed policy."""

import contextlib
import importlib.util
import json
import shutil
import socket
import struct
import subprocess  # nosec B404
import threading
import time
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/bootstrap/mail_dependency_gate.pl"
SPEC = importlib.util.spec_from_file_location(
    "mail_gates", ROOT / "tools/bootstrap/prepare_mail_gates.py"
)
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


@contextlib.contextmanager
def server(reply):
    """A local one-connection fixture; no real mail or credentials involved."""
    requests = []
    errors = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(3)

        def handle():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(2)
                    reply(connection, requests)
            except (OSError, AssertionError) as error:
                errors.append(type(error).__name__)

        thread = threading.Thread(target=handle, daemon=True)
        thread.start()
        yield listener.getsockname()[1], requests
        thread.join(4)
        if thread.is_alive():
            raise AssertionError("fixture thread leaked")
        # Broken pipes are expected when malformed/slow replies are rejected.
        if "AssertionError" in errors:
            raise AssertionError("unexpected probe request")


def exact(connection, size):
    """Read a complete request in the fixture despite TCP segmentation."""
    data = b""
    while len(data) < size:
        part = connection.recv(size - len(data))
        if not part:
            break
        data += part
    return data


@unittest.skipUnless(shutil.which("perl"), "Perl is required")
class MailGateTests(unittest.TestCase):
    """Exercise the real Perl implementation using only loopback fake services."""

    def perl(self, code, *args):
        """Load reviewed probe functions without invoking production CLI targets."""
        result = subprocess.run(  # nosec B603
            [
                shutil.which("perl"),
                "-e",
                'do $ARGV[0] or die "load"; ' + code,
                str(SCRIPT),
                *map(str, args),
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result

    def probe(self, kind, port):
        """Only tests supply loopback endpoint overrides; production CLI cannot."""
        return self.perl(
            'exit(MailDependencies::probe($ARGV[1],"127.0.0.1",$ARGV[2],1)?0:1)',
            kind,
            port,
        )

    def test_partial_valid_protocols_and_no_mail_work(self):
        """Handshake/PING probes accept correct fragmented replies, never AUTH/DATA."""
        fixtures = {
            "valkey": (b"*1\r\n$4\r\nPING\r\n", b"+PONG\r\n"),
            "clamav": (b"zPING\0", b"PONG\0"),
            "http": (
                b"GET /ping HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n",
                b"HTTP/1.0 200 OK\r\n",
            ),
            "milter": (
                struct.pack("!I", 13) + b"O" + struct.pack("!III", 6, 0, 0),
                struct.pack("!I", 13) + b"O" + struct.pack("!III", 6, 0, 0),
            ),
        }
        for kind, (request, response) in fixtures.items():

            def handler(
                connection, requests, request=request, response=response, kind=kind
            ):
                incoming = exact(connection, len(request))
                requests.append(incoming)
                assert incoming == request
                for byte in response:
                    connection.sendall(bytes([byte]))
                if kind == "milter":
                    assert exact(connection, 5) == struct.pack("!I", 1) + b"Q"

            with self.subTest(kind=kind), server(handler) as (port, requests):
                result = self.probe(kind, port)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(requests, [request])

    def test_lmtp_and_sasl_never_send_auth_or_a_message(self):
        """Dovecot readiness is anonymous protocol negotiation only."""

        def lmtp(connection, requests):
            connection.sendall(b"220 fixture LMTP\r\n")
            incoming = exact(connection, 6)
            requests.append(incoming)
            assert incoming == b"QUIT\r\n"
            connection.sendall(b"221 goodbye\r\n")

        def sasl(connection, requests):
            incoming = connection.recv(256)
            requests.append(incoming)
            assert incoming.startswith(b"VERSION\t1\t2\nCPID\t")
            assert b"AUTH" not in incoming
            connection.sendall(
                b"VERSION\t1\t2\nMECH\tPLAIN\tplaintext\nCOOKIE\tfixture-not-a-real-cookie\nDONE\n"
            )

        for kind, handler in (("lmtp", lmtp), ("sasl", sasl)):
            with self.subTest(kind=kind), server(handler) as (port, _):
                result = self.probe(kind, port)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(
                    b"fixture-not-a-real-cookie", result.stdout + result.stderr
                )

    def test_dns_checks_question_response_id_and_rcode(self):
        """A listening socket, SERVFAIL or unrelated answer cannot pass DNS readiness."""
        for valid in (True, False):

            def dns(connection, requests, valid=valid):
                size = struct.unpack("!H", exact(connection, 2))[0]
                query = exact(connection, size)
                requests.append(query)
                assert query[12:] == b"\x09localhost\0\0\1\0\1"
                answer = (
                    struct.pack(
                        "!HHHHHH", 0x7139, 0x8180 if valid else 0x8182, 1, 1, 0, 0
                    )
                    + query[12:]
                    + b"\xc0\x0c"
                    + struct.pack("!HHIH", 1, 1, 60, 4)
                    + b"\x7f\0\0\1"
                )
                connection.sendall(struct.pack("!H", len(answer)) + answer)

            with self.subTest(valid=valid), server(dns) as (port, _):
                self.assertEqual(self.probe("dns", port).returncode, 0 if valid else 1)

    def test_wrong_service_denial_and_stalled_reads_are_not_ready(self):
        """Never accept NOAUTH, HTTP503, invalid frames or an open silent socket."""
        for kind, response in (
            ("valkey", b"-NOAUTH auth required\r\n"),
            ("valkey", b"+PONG\r"),
            ("clamav", b"ERROR"),
            ("http", b"HTTP/1.0 503 unavailable\r\n"),
            ("milter", struct.pack("!I", 0xFFFFFFFF)),
        ):

            def bad(connection, _requests, response=response):
                connection.recv(4096)
                connection.sendall(response)

            with self.subTest(kind=kind), server(bad) as (port, _):
                self.assertEqual(self.probe(kind, port).returncode, 1)

        def slow(connection, _requests):
            connection.recv(4096)
            time.sleep(2)

        for kind in ("clamav", "valkey"):
            with self.subTest(kind=kind), server(slow) as (port, _):
                started = time.monotonic()
                self.assertEqual(self.probe(kind, port).returncode, 1)
                self.assertLess(time.monotonic() - started, 1.75)

    def test_global_budget_recovery_and_known_profiles_only(self):
        """No late probe/release past the monotonic budget, and no arbitrary targets."""
        code = 'my $t=0; my $n=0; my $c=sub {$n++;$t+=1;return 1;}; exit(MailDependencies::check_group("rspamd-ready",2,$c,sub{$t}) || $n!=2 ? 1:0);'
        result = self.perl(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.perl(
            'exit(MailDependencies::main("--check","unknown") == 2 ? 0:1)'
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_waiting_recovers_without_unrelated_work_or_socket_output(self):
        """Exercise the real retry controller with a deterministic test-only clock."""
        code = (
            'my $time=0; no warnings "redefine"; '
            "local *MailDependencies::now=sub{return $time}; "
            "local *MailDependencies::pause=sub{$time+=$_[0]}; "
            "local *MailDependencies::probe=sub{return $time>=5}; "
            'exit MailDependencies::main("--wait","rspamd-dependencies");'
        )
        result = self.perl(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([e["result"] for e in events], ["unavailable", "ready"])

    def test_canonical_graph_policy_and_data_preservation(self):
        """Dovecot stays independent; startup/readiness must not alter local liveness."""
        docs = GEN.documents()
        self.assertNotIn("mail/deployment-dovecot.yaml", docs)
        self.assertEqual(
            docs["mail/deployment-postfix.yaml"]["metadata"]["annotations"][
                "argocd.argoproj.io/sync-wave"
            ],
            "1",
        )
        for path, doc in docs.items():
            expected = doc if isinstance(doc, list) else [doc]
            self.assertEqual(
                list(yaml.safe_load_all((ROOT / path).read_text())), expected
            )
        for app in ("rspamd", "postfix"):
            pod = docs[f"mail/deployment-{app}.yaml"]["spec"]["template"]["spec"]
            work = next(
                c
                for c in pod["containers"]
                if c["name"] == ("rspamd" if app == "rspamd" else "postfix-mail")
            )
            init = pod["initContainers"][-1]
            self.assertEqual(init["image"], work["image"])
            self.assertEqual(
                [m["name"] for m in init["volumeMounts"]], ["mail-startup"]
            )
            self.assertIn("timeout", init["command"])
            self.assertEqual(work["readinessProbe"]["failureThreshold"], 1)
            self.assertNotIn("mail_dependency_gate", json.dumps(work["livenessProbe"]))
            self.assertTrue(any("persistentVolumeClaim" in v for v in pod["volumes"]))
        self.assertIn(
            "milter_default_action = tempfail",
            docs["mail/config-map-main-cf.yaml"]["data"]["config"],
        )
        force = docs["mail/config-map-rspamd-cf.yaml"]["data"]["force_actions"]
        self.assertIn('action = "soft reject"', force)
        self.assertIn('expression = "CLAM_VIRUS_FAIL"', force)
        self.assertIn('honor_action = ["reject", "soft reject"]', force)


if __name__ == "__main__":
    unittest.main()
