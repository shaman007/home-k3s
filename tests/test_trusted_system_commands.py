"""Verify system-tool calls cannot be replaced through an untrusted PATH entry."""

from contextlib import chdir
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    """Load one helper without invoking its CLI entry point."""
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TrustedSystemCommandTests(unittest.TestCase):
    """Exercise real read-only system commands with hostile names earlier in PATH."""

    def test_ci_git_inventory_ignores_hostile_path(self):
        """Both CI inventories still use the actual checkout rather than a replacement Git."""
        listing = load("manifest_listing", "tools/ci/list_k8s_manifest_files.py")
        contracts = load("contract_inventory", "tools/ci/validate_runtime_contracts.py")
        with tempfile.TemporaryDirectory(prefix="hostile-tool-path-") as directory:
            replacement = Path(directory) / "git"
            replacement.write_text("#!/bin/sh\nexit 91\n")
            replacement.chmod(0o755)
            with patch.dict("os.environ", {"PATH": directory}), chdir(ROOT):
                self.assertEqual(contracts.repo_root(), ROOT)
                for module in (listing, contracts):
                    with self.subTest(module=module.__name__):
                        paths = module.tracked_yaml_files(ROOT)
                        self.assertTrue(paths)
                        self.assertTrue(all(path.is_relative_to(ROOT) for path in paths))
                        self.assertTrue(all(path.is_file() for path in paths))

    def test_invalid_signing_key_cannot_bypass_openssl_through_path(self):
        """A fake successful OpenSSL cannot turn an invalid public key into an accepted key."""
        signing = load("harbor_key_validation", "tools/supply-chain/prepare_harbor_signing.py")
        with tempfile.TemporaryDirectory(prefix="hostile-tool-path-") as directory:
            replacement = Path(directory) / "openssl"
            replacement.write_text("#!/bin/sh\nexit 0\n")
            replacement.chmod(0o755)
            with patch.dict("os.environ", {"PATH": directory}):
                with self.assertRaises(signing.subprocess.CalledProcessError):
                    signing.prepare("not a public key")
