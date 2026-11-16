"""Secret-backed prompt loading without production texts, credentials or paid requests."""

import copy
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiy_gateway_fixture import prompt_environment

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aiy-voice"))
prompts = importlib.import_module("prompts")
server = importlib.import_module("server")


class PromptTests(unittest.TestCase):
    """Require a valid projection and constrain secret edits to text slots."""

    def setUp(self):
        """Use only a synthetic schema-compatible bundle."""
        self.enterContext(prompt_environment())
        self.bundle = prompts.load_prompts()

    def test_missing_secret_prevents_startup_without_creating_ledger(self):
        """A missing prompt mount cannot silently fall back to baked-in texts."""
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory, "ledger.sqlite3")
            with patch.dict(os.environ, {"AIY_PROMPTS_FILE": str(Path(directory, "missing"))}):
                with self.assertRaisesRegex(RuntimeError, "prompt secret"):
                    server.create_app(str(ledger))
            self.assertFalse(ledger.exists())

    def test_invalid_secret_is_rejected_without_disclosing_its_contents(self):
        """Malformed, incomplete, oversized and wrong-type projections fail closed."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "bundle.json")
            with patch.dict(os.environ, {"AIY_PROMPTS_FILE": str(path)}):
                for bad in (
                    'private-marker{', '{}', '[]',
                    json.dumps(dict(self.bundle, voice="")),
                    json.dumps(dict(self.bundle, version=2)),
                    json.dumps(dict(self.bundle, web_search="no time placeholder")),
                    json.dumps(dict(self.bundle, tools={"x": []})),
                    'private-marker' * prompts.MAX_BYTES,
                ):
                    path.write_text(bad, encoding="utf-8")
                    with self.assertRaises(RuntimeError) as error:
                        prompts.load_prompts()
                    self.assertNotIn("private-marker", str(error.exception))

    def test_projection_updates_are_read_without_rebuilding(self):
        """Read the latest file on each new session instead of caching prompt content."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "bundle.json")
            with patch.dict(os.environ, {"AIY_PROMPTS_FILE": str(path)}):
                for voice in ("Synthetic version A", "Synthetic version B"):
                    path.write_text(json.dumps(dict(self.bundle, voice=voice)), encoding="utf-8")
                    instructions = server.session_config()["session"]["instructions"]
                    self.assertTrue(instructions.startswith(voice))

    def test_secret_cannot_modify_tool_names_parameters_or_constraints(self):
        """Only known text slots are mutable, never enums, permissions or arguments."""
        tools = [{"name": "example", "description": "", "parameters": {
            "type": "object", "properties": {"color": {"enum": ["red", "blue"]}},
            "required": ["color"], "additionalProperties": False,
        }}]
        bundle = {"tools": {"example": {"/description": "Synthetic tool text"}}}
        result = prompts.describe_tools(tools, bundle)
        self.assertEqual(result[0]["parameters"], tools[0]["parameters"])
        self.assertEqual(tools[0]["description"], "")
        for bad in ({}, {"admin": {}}, {"example": {}},
                    {"example": {"/description": "text",
                                 "/parameters/properties/color/enum": "all"}}):
            with self.assertRaises(RuntimeError):
                prompts.describe_tools(tools, {"tools": bad})
        changed = copy.deepcopy(bundle)
        changed["tools"]["example"]["/description"] = "New synthetic wording"
        self.assertEqual(
            prompts.describe_tools(tools, changed)[0]["description"], "New synthetic wording"
        )
