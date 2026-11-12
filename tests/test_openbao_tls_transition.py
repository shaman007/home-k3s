"""Safety contracts for the explicit OpenBao TLS recovery stages; no live API."""

import importlib.util
import builtins
import json
import os
from pathlib import Path
import ssl
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "transition", ROOT / "tools/bootstrap/openbao_tls_transition.py"
)
transition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transition)


class OpenBaoTLSRecoverySafety(unittest.TestCase):
    """Protect command, recovery and credential-handling boundaries."""

    def test_import_does_not_require_cryptography(self):
        """Minimal CI dependencies must suffice to import the operational stages."""
        original_import = builtins.__import__

        def without_cryptography(name, *args, **kwargs):
            if name == "cryptography" or name.startswith("cryptography."):
                raise ModuleNotFoundError("cryptography intentionally unavailable")
            return original_import(name, *args, **kwargs)

        module_spec = importlib.util.spec_from_file_location(
            "transition_without_crypto", ROOT / "tools/bootstrap/openbao_tls_transition.py"
        )
        isolated = importlib.util.module_from_spec(module_spec)
        with mock.patch("builtins.__import__", side_effect=without_cryptography):
            module_spec.loader.exec_module(isolated)
        self.assertTrue(callable(isolated.rollback))

    def test_probe_rejects_legacy_tls_and_keeps_peer_verification(self):
        """Require TLS 1.2 or newer without relaxing chain or DNS validation."""
        context = transition.probe.__globals__["create_ssl_context"](
            ROOT / "docs/migrations/openbao-internal-tls/root-ca.pem"
        )
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)
        self.assertTrue(context.check_hostname)

    def test_executable_resolution_rejects_ambient_path_and_unknown_programs(self):
        """Hostile PATH entries cannot replace administrative binaries."""
        with (
            mock.patch.dict(os.environ, {"PATH": "/untrusted"}),
            mock.patch.object(
                transition.shutil, "which", return_value="/usr/bin/kubectl"
            ) as resolver,
        ):
            self.assertEqual("/usr/bin/kubectl", transition.executable("kubectl"))
        self.assertNotIn("/untrusted", resolver.call_args.kwargs["path"])
        with self.assertRaises(ValueError):
            transition.executable("/untrusted/kubectl")

    def test_rollback_restores_exact_spec_and_never_puts_key_in_argv(self):
        """Restore key bytes through stdin and replace the exact previous spec."""
        old_key = "TEST-ONLY-SENSITIVE-MARKER"
        old = {"metadata": {"annotations": {"issuer": "old"}}, "data": {"tls.key": old_key}}
        original = {"kind": "Certificate", "spec": {"issuerRef": {"name": "old-issuer"}}}
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            (state / "baseline.json").write_text(json.dumps({"objects": [original]}))
            with (
                mock.patch.object(transition, "run", return_value=json.dumps([old]).encode()),
                mock.patch.object(transition, "kube") as kube,
            ):
                transition.rollback(state)
        self.assertEqual(2, kube.call_count)
        cert_args = kube.call_args_list[0].args
        cert_patch = json.loads(cert_args[-1])
        self.assertEqual("replace", cert_patch[0]["op"])
        self.assertEqual("/spec", cert_patch[0]["path"])
        key_call = kube.call_args_list[1]
        self.assertIn("--patch-file=/dev/stdin", key_call.args)
        self.assertNotIn(old_key, " ".join(str(x) for x in key_call.args))
        self.assertIn(old_key, key_call.kwargs["payload"].decode())
        data_patch = json.loads(key_call.kwargs["payload"])
        self.assertEqual({"op": "replace", "path": "/data", "value": old["data"]}, data_patch[0])

    def test_command_failure_does_not_echo_stderr_secrets(self):
        """Suppress arbitrary potentially sensitive command diagnostics."""
        result = types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"SENSITIVE-EXCEPTION-DATA")
        with mock.patch.object(transition.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as caught:
                transition.run(["kubectl", "get", "secret"])
        self.assertNotIn("SENSITIVE-EXCEPTION-DATA", str(caught.exception))

    def test_all_kubernetes_calls_pin_the_cluster_and_timeout(self):
        """Never infer the target cluster or omit request bounds."""
        with mock.patch.object(transition, "run", return_value=b"{}") as runner:
            transition.kube("get", "pods", "-n", "openbao")
        argv = runner.call_args.args[0]
        self.assertIn("--context=admin@home-k8s", argv)
        self.assertIn("--request-timeout=20s", argv)
        self.assertNotIn("apply", argv)

    def test_clean_snapshot_excludes_status_and_client_side_apply_payload(self):
        """Snapshot only restorable desired state and useful metadata."""
        obj = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "test",
                "uid": "not-restorable",
                "annotations": {
                    "kubectl.kubernetes.io/last-applied-configuration": "OLD-DATA",
                    "keep": "yes",
                },
            },
            "data": {"key": "public"},
            "status": {"not": "desired"},
        }
        clean = transition.clean(obj)
        self.assertNotIn("status", clean)
        self.assertNotIn("uid", clean["metadata"])
        self.assertEqual({"keep": "yes"}, clean["metadata"]["annotations"])


if __name__ == "__main__":
    unittest.main()
