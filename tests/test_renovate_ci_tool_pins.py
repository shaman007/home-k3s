"""Keep CI archive versions, digests and Kyverno version gates synchronized."""

import copy
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIN_FILE = "tools/ci/tool-versions.json"


def load_module(name, relative):
    """Load the actual CLI source so version-gate behavior is exercised directly."""
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CiToolPinTests(unittest.TestCase):
    """Require version and digest extraction as one dependency and one source of truth."""

    def test_each_archive_is_extracted_with_its_version_and_digest(self):
        """All discovered manual CI download pins must carry immutable archive digests."""
        config = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
        managers = [
            m
            for m in config["customManagers"]
            if m.get("datasourceTemplate") == "github-release-attachments"
        ]
        self.assertEqual(len(managers), 1)
        manager = managers[0]
        self.assertTrue(any(re.search(p[1:-1], PIN_FILE) for p in manager["managerFilePatterns"]))
        pattern = re.compile(re.sub(r"\(\?<([A-Za-z]+)>", r"(?P<\1>", manager["matchStrings"][0]))
        source = (ROOT / PIN_FILE).read_text(encoding="utf-8")
        pins = json.loads(source)
        found = [match.groupdict() for match in pattern.finditer(source)]
        self.assertEqual(len(found), 3)
        self.assertEqual(
            {(m["depName"], m["currentValue"], m["currentDigest"]) for m in found},
            {(p["depName"], p["version"], p["sha256"]) for p in pins.values()},
        )
        self.assertEqual(set(pins), {"kyverno", "ripgrep", "kubeconform"})

    def test_shell_consumers_read_pins_and_verify_digests(self):
        """Every archive installer must read the managed manifest and retain SHA verification."""
        workflow = (ROOT / ".github/workflows/validate-k8s.yml").read_text(encoding="utf-8")
        action = (ROOT / ".github/actions/setup-kyverno/action.yml").read_text(encoding="utf-8")
        for tool, source, variable in (
            ("kyverno", action, "KYVERNO_CLI"),
            ("ripgrep", workflow, "RIPGREP"),
            ("kubeconform", workflow, "KUBECONFORM"),
        ):
            with self.subTest(tool=tool):
                self.assertIn(
                    'tool_pins.py" ' + tool if tool == "kyverno" else "tool_pins.py " + tool, source
                )
                self.assertIn(variable + "_SHA256", source)
                self.assertIn("sha256sum --check --strict", source)

    def test_pin_loader_rejects_shell_fragments_and_unpinned_archives(self):
        """Bad automated replacements cannot become shell commands or unchecked downloads."""
        loader = load_module("ci_tool_pins", "tools/ci/tool_pins.py")
        pins = json.loads((ROOT / PIN_FILE).read_text(encoding="utf-8"))
        for field, value in (
            ("version", "v1.2.3;id"),
            ("sha256", ""),
            ("depName", "unreviewed/repository"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                changed = copy.deepcopy(pins)
                changed["kyverno"][field] = value
                path = Path(directory) / "pins.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(ValueError):
                    loader.load_pin("kyverno", path)

    def test_future_manifest_version_controls_both_real_kyverno_gates(self):
        """A Renovate-only manifest edit updates both guards, which still reject other binaries."""
        for script, stage, arguments in (
            ("test_audit_policies.py", "load_inputs", ["--rendered", "unused"]),
            (
                "benchmark_audit_policies.py",
                "read_tests",
                ["--baseline", "unused", "--optimized", "unused", "--output", "unused"],
            ),
        ):
            module = load_module("pin_gate_" + stage, "tools/kyverno/" + script)
            self.assertEqual(module.CLI_PINS, ROOT / PIN_FILE)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "tools/ci").mkdir(parents=True)
                (root / PIN_FILE).write_text(json.dumps({"kyverno": {"version": "v9.8.7"}}))
                for actual, accepted in (("v9.8.7", True), ("v9.8.70", False), ("v1.20.0", False)):
                    with self.subTest(script=script, actual=actual), patch.object(
                        module, "CLI_PINS", root / PIN_FILE
                    ), patch.object(sys, "argv", [script, *arguments]), patch.object(
                        module.subprocess, "check_output", return_value="Version: " + actual + "\n"
                    ), patch.object(
                        module, stage, side_effect=RuntimeError("gate accepted")
                    ) as next_stage:
                        with self.assertRaises(RuntimeError if accepted else SystemExit):
                            module.main()
                        self.assertEqual(next_stage.called, accepted)
