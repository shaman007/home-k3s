"""Meaningful failure cases for recovering KV from retained Kubernetes Secrets."""

import base64
import importlib.util
import pathlib
import unittest

SPEC = importlib.util.spec_from_file_location("recovery", pathlib.Path(__file__).parents[1] / "tools/openbao/recovery.py")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def test_literal_template_roundtrip_and_repeated_field(self):
        self.assertEqual(recovery.reverse_template('a={{ .key }}\nb={{ .key }}\n', 'a=test-value\nb=test-value\n'), {"key": "test-value"})
        with self.assertRaises(recovery.RecoveryError):
            recovery.reverse_template('a={{ .key }}\nb={{ .key }}', 'a=one\nb=two')

    def test_refuses_unreviewed_template_expression(self):
        with self.assertRaises(recovery.RecoveryError):
            recovery.reverse_template('{{ .key | b64enc }}', 'anything')

    def test_conflicting_mirrors_stop_without_values_in_error(self):
        items = []
        for namespace, value in [("one", "fixture-password-one"), ("two", "fixture-password-two")]:
            items += [
                {"kind": "Secret", "metadata": {"namespace": namespace, "name": "target"}, "data": {"password": base64.b64encode(value.encode()).decode()}},
                {"kind": "ExternalSecret", "metadata": {"namespace": namespace, "name": "target"}, "spec": {"data": [{"secretKey": "password", "remoteRef": {"key": "db", "property": "password"}}]}},
            ]
        with self.assertRaises(recovery.RecoveryError) as error:
            recovery.recover_kv({"items": items})
        self.assertNotIn("fixture-password", str(error.exception))

    def test_missing_target_is_not_silently_skipped(self):
        with self.assertRaises(recovery.RecoveryError):
            recovery.recover_kv({"items": [{"kind": "ExternalSecret", "metadata": {"namespace": "test", "name": "missing"}, "spec": {}}]})

    def test_supplemental_excludes_mirrors_system_and_tls(self):
        items = [
            {"kind": "Secret", "type": kind, "metadata": {"namespace": namespace, "name": name}, "data": {"field": "Zml4dHVyZQ=="}}
            for namespace, name, kind in [
                ("harbor", "core", "Opaque"), ("harbor", "mirrored", "Opaque"),
                ("harbor", "tls", "kubernetes.io/tls"), ("kube-system", "bootstrap", "Opaque")
            ]
        ]
        items.append({"kind": "ExternalSecret", "metadata": {"namespace": "harbor", "name": "mirrored"}, "spec": {}})
        recovered = recovery.supplemental_secrets({"items": items})
        self.assertEqual(list(recovered), ["recovery/kubernetes/harbor/core"])
        self.assertEqual(recovered["recovery/kubernetes/harbor/core"]["data"], {"field": "Zml4dHVyZQ=="})

    def test_credential_scan_handles_json_escaped_values(self):
        with self.assertRaises(recovery.RecoveryError):
            recovery.assert_secret_free_text(r'{"value":"fixture\npassword-value"}', {"kv": {"key": "fixture\npassword-value"}})


if __name__ == "__main__":
    unittest.main()
