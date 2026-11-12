"""Keep the Codacy Django-plugin exception confined to a non-Django repository."""

import ast
from configparser import ConfigParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def django_usage(source):
    """Detect framework imports and its explicit settings-module configuration."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "django" for alias in node.names):
                return True
        if (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").split(".")[0] == "django"
        ):
            return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {
                    "DJANGO_SETTINGS_MODULE",
                    "INSTALLED_APPS",
                }:
                    return True
                if isinstance(target, ast.Subscript) and isinstance(
                    target.slice, ast.Constant
                ):
                    if target.slice.value == "DJANGO_SETTINGS_MODULE":
                        return True
    return False


class DjangoPluginBoundaryTest(unittest.TestCase):
    """Revisit the sole configuration exception if Django is introduced."""

    def test_plugin_exception_does_not_disable_any_other_rule(self):
        """The adapter-specific false positive must not hide general lint/security errors."""
        config = ConfigParser()
        config.read(ROOT / ".pylintrc", encoding="utf-8")
        self.assertEqual(
            config["MESSAGES CONTROL"]["disable"].strip(), "django-not-configured"
        )

    def test_analyzed_repository_is_not_a_django_project(self):
        """Framework source or settings invalidate the non-Django assumption."""
        for path in ROOT.rglob("*.py"):
            relative = path.relative_to(ROOT)
            if path.is_symlink() or any(
                part.startswith(".") or part == "__pycache__" for part in relative.parts
            ):
                continue
            with self.subTest(path=relative.as_posix()):
                self.assertFalse(
                    django_usage(path.read_text(encoding="utf-8")),
                    "Django introduced: remove/review the plugin exception",
                )

    def test_guard_detects_real_imports_and_settings_but_not_quoted_fixtures(self):
        """Test the audit assumption rather than a textual match for framework names."""
        for source in [
            "import django.db",
            "from django import forms",
            'DJANGO_SETTINGS_MODULE = "app.settings"',
            'environ["DJANGO_SETTINGS_MODULE"] = "app.settings"',
        ]:
            self.assertTrue(django_usage(source))
        self.assertFalse(django_usage('example = "import django"'))
