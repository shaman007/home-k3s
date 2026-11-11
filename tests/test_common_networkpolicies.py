"""Preserve namespace isolation and explicit destinations in generated policies."""

import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "common_networkpolicies",
    Path(__file__).resolve().parents[1] / "tools/networkpolicy/generate_common_networkpolicies.py",
)
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class CommonNetworkPolicyTests(unittest.TestCase):
    """Check security boundaries without applying policies to a cluster."""

    def test_default_deny_isolates_unlabelled_pods(self):
        """Workload-specific allow selectors cannot narrow the namespace safety net."""
        spec = {"namePrefix": "fixture", "namespace": "fixture", "podSelector": {"app": "web"}}
        result = generator.build_policy(spec, {"type": "default-deny"})
        self.assertEqual(result["spec"], {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]})
        self.assertEqual(spec["podSelector"], {"app": "web"})

    def test_web_egress_preserves_explicit_destinations(self):
        """A selected web destination must not become unrestricted internet access."""
        spec = {"namePrefix": "fixture", "namespace": "fixture"}
        result = generator.build_policy(spec, {"type": "web-egress", "cidrs": ["192.0.2.0/24"]})
        self.assertEqual(
            result["spec"]["egress"],
            [
                {
                    "to": [{"ipBlock": {"cidr": "192.0.2.0/24"}}],
                    "ports": [{"protocol": "TCP", "port": 80}, {"protocol": "TCP", "port": 443}],
                }
            ],
        )

    def test_unknown_type_fails_closed(self):
        """Misspelled policy types cannot silently produce an allow policy."""
        with self.assertRaisesRegex(ValueError, "Unsupported common policy type: typo"):
            generator.build_policy({}, {"type": "typo"})
