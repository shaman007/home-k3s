"""Check the build request cannot silently widen approved publication scope."""

import ast
import base64
import fnmatch
import hashlib
import importlib.util
import io
import tarfile
import unittest

import yaml
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "aiy_build", Path(__file__).resolve().parents[1] / "aiy-voice/prepare_build.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildRequestTests(unittest.TestCase):
    """Keep one-off build requests within the approved publication scope."""

    def test_retry_retains_approved_destination_and_records_actual_source(self):
        """Verify retry retains approved destination and records actual source."""
        request = builder.render("src-89e4e483f7496011")
        config, job = request["items"]
        source = base64.b64decode(config["binaryData"]["context.tgz"])
        self.assertEqual(
            job["metadata"]["annotations"]["aiy-source-sha256"], hashlib.sha256(source).hexdigest()
        )
        container = job["spec"]["template"]["spec"]["containers"][0]
        env = {entry["name"]: entry.get("value") for entry in container["env"]}
        self.assertEqual(
            env["AIY_IMAGE"], "harbor.andreybondarenko.com/library/aiy-voice:src-89e4e483f7496011"
        )
        self.assertEqual(request, builder.render("src-89e4e483f7496011"))
        with tarfile.open(fileobj=io.BytesIO(source), mode="r:gz") as archive:
            self.assertEqual(set(archive.getnames()), set(builder.FILES))
            self.assertNotIn("auth.json", archive.getnames())
        self.assertNotIn(":latest", container["args"][0])
        self.assertEqual(job["spec"]["backoffLimit"], 0)

    def test_local_imports_reach_both_build_context_and_image(self):
        """Every local Python dependency must survive archive, ignore and COPY filters."""
        root = Path(__file__).resolve().parents[1] / "aiy-voice"
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        allowed = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
        for name in builder.FILES:
            if not name.endswith(".py"):
                continue
            for node in ast.walk(ast.parse((root / name).read_text(encoding="utf-8"))):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                dependency = node.module + ".py"
                if (root / dependency).exists():
                    with self.subTest(source=name, dependency=dependency):
                        self.assertIn(dependency, builder.FILES)
                        self.assertIn(dependency, dockerfile)
                        self.assertIn("!" + dependency, allowed)

    def test_orphan_exceptions_only_match_generated_job_and_configmap_names(self):
        """Retain orphan warnings for unrelated names, groups and resource kinds."""
        project = yaml.safe_load((Path(__file__).resolve().parents[1] /
            "argocd/application-project-applications.yaml").read_text())
        orphaned = project["spec"]["orphanedResources"]
        self.assertIs(orphaned["warn"], True)
        exceptions = [item for item in orphaned["ignore"]
                      if item["name"].startswith("aiy-voice-build-")]
        self.assertEqual({(item["group"], item["kind"]) for item in exceptions},
                         {("batch", "Job"), ("", "ConfigMap")})
        self.assertEqual(len(exceptions), 2)

        def ignored(group, kind, name):
            return any(item["group"] == group and item["kind"] == kind
                       and fnmatch.fnmatchcase(name, item["name"]) for item in exceptions)

        for item in builder.render()["items"]:
            group = item["apiVersion"].split("/")[0] if "/" in item["apiVersion"] else ""
            self.assertTrue(ignored(group, item["kind"], item["metadata"]["name"]))
        for name in ("aiy-voice-build-", "aiy-voice-build-debug", "unrelated-build-0123456789abcdef",
                     "aiy-voice-build-0123456789abcde", "aiy-voice-build-0123456789abcdef0",
                     "aiy-voice-build-0123456789abcdeg", "aiy-voice-build-0123456789ABCDEF"):
            with self.subTest(name=name):
                self.assertFalse(ignored("batch", "Job", name))
                self.assertFalse(ignored("", "ConfigMap", name))
        name = "aiy-voice-build-0123456789abcdef"
        for group, kind in (("", "Secret"), ("", "PersistentVolumeClaim"),
                            ("apps", "Deployment"), ("other.example", "Job")):
            with self.subTest(group=group, kind=kind):
                self.assertFalse(ignored(group, kind, name))

    def test_invalid_destination_tag_is_rejected(self):
        """Verify invalid destination tag is rejected."""
        for tag in ("../other", "bad tag", "tag;command", ""):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                builder.render(tag)


if __name__ == "__main__":
    unittest.main()
