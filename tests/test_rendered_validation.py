"""Exercise rendered-resource schema validation and custom-resource handling."""

import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest
import subprocess
import stat
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/ci"))


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/ci" / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


render = module("render", "render-applications.py")
validate = module("validate", "validate-rendered.py")


class RenderValidationTest(unittest.TestCase):
    """Exercise safe rendering, source retrieval, schema checks, and custom-resource validation."""
    def test_rendered_secret_output_is_owner_only(self):
        (self.root / "tools/ci").mkdir(parents=True)
        (self.root / "tools/ci/validation-config.yaml").write_text("kubernetesVersion: 1.37.2\n")
        applications = self.root / "argocd"
        applications.mkdir()
        (applications / "application-test.yaml").write_text(
            yaml.safe_dump(
                {
                    "kind": "Application",
                    "metadata": {"name": "test"},
                    "spec": {"source": {"path": "fixture"}},
                }
            )
        )
        output = self.root / "rendered"
        output.mkdir(mode=0o755)
        output.chmod(0o755)
        manifest = "apiVersion: v1\nkind: Secret\nmetadata:\n  name: synthetic\n"
        with (
            patch.object(render, "ROOT", self.root),
            patch.object(render, "render_source", return_value=manifest),
            patch.object(sys, "argv", ["render", "--output", str(output)]),
            patch("builtins.print"),
        ):
            render.main()
        self.assertEqual(0o700, stat.S_IMODE(output.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE((output / "test.yaml").stat().st_mode))

    def test_git_hosted_chart_uses_checkout_and_helm_values_without_remote_version(self):
        chart = self.root / "chart"
        chart.mkdir()
        (chart / "Chart.yaml").write_text("apiVersion: v2\nname: test\nversion: 0.1.0\n")
        source = {
            "repoURL": render.REPO,
            "path": "chart",
            "targetRevision": "main",
            "helm": {"releaseName": "solver", "values": "productionEnabled: true\n"},
        }
        with patch.object(render, "run", return_value="rendered") as run:
            self.assertEqual(
                "rendered",
                render.render_source(self.app, source, [source], self.root, self.root, "1.36.0"),
            )
        args = run.call_args.args[0]
        self.assertEqual(args[2:4], ["solver", str(chart)])
        self.assertNotIn("--version", args)
        self.assertIn("--values", args)
        self.assertEqual("productionEnabled: true\n", (self.root / "values.yaml").read_text())

    def test_remote_kustomize_fetch_retries_without_printing_diagnostics(self):
        failed = subprocess.CompletedProcess(
            [], 1, "private manifest", "git fetch failed: private diagnostic"
        )
        success = subprocess.CompletedProcess([], 0, "rendered", "")
        with (
            patch.object(render.subprocess, "run", side_effect=[failed, success]) as call,
            patch.object(render.time, "sleep") as sleep,
            patch("builtins.print") as output,
        ):
            self.assertEqual("rendered", render.run(["kubectl", "kustomize", "argocd-install"]))
            self.assertEqual(2, call.call_count)
            sleep.assert_called_once_with(2)
            self.assertNotIn("private", str(output.call_args_list))

    def test_remote_fetch_retries_are_bounded(self):
        failed = subprocess.CompletedProcess(
            [], 1, "private manifest", "git fetch failed: private diagnostic"
        )
        with (
            patch.object(render.subprocess, "run", return_value=failed) as call,
            patch.object(render.time, "sleep"),
            patch("builtins.print"),
            self.assertRaises(RuntimeError) as error,
        ):
            render.run(["kubectl", "kustomize", "argocd-install"])
        self.assertEqual(3, call.call_count)
        self.assertNotIn("private", str(error.exception))

    def test_local_kustomize_and_helm_errors_are_not_retried(self):
        for args, diagnostic in [
            (["kubectl", "kustomize", "local"], "invalid YAML"),
            (["helm", "template", "chart"], "git fetch failed"),
        ]:
            with (
                self.subTest(args=args),
                patch.object(
                    render.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 1, "", diagnostic),
                ) as call,
                self.assertRaises(RuntimeError),
            ):
                render.run(args)
            self.assertEqual(1, call.call_count)

    def test_github_download_failure_is_classified_without_leaking_diagnostics(self):
        for binary in ["helm", "/tmp/helm"]:
            failed = subprocess.CompletedProcess(
                [],
                1,
                "private manifest",
                "Error: failed to fetch https://github.com/org/repo/releases/download/"
                "v1/chart.tgz : 504 Gateway Time-out private",
            )
            with (
                patch.object(render.subprocess, "run", return_value=failed),
                self.assertRaises(render.HelmDownloadError) as error,
            ):
                render.run([binary, "template", "release", "chart"])
            self.assertNotIn("private", str(error.exception))

    def test_template_and_permanent_download_errors_do_not_use_fallback(self):
        for diagnostic in [
            "Error: template: chart: invalid value 504",
            "Error: failed to fetch https://github.com/org/repo/chart.tgz : 404 Not Found",
            "Error: failed to fetch https://other.invalid/chart.tgz : 504 Gateway Time-out",
        ]:
            with (
                self.subTest(diagnostic=diagnostic),
                patch.object(
                    render.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 1, "", diagnostic),
                ),
                self.assertRaises(RuntimeError) as error,
            ):
                render.run(["helm", "template", "release", "chart"])
            self.assertNotIsInstance(error.exception, render.HelmDownloadError)

    def test_github_chart_fallback_verifies_digest_before_using_archive(self):
        import hashlib
        import io
        import json

        archive = b"chart archive"
        source = {"repoURL": "https://charts.invalid/", "chart": "test", "targetRevision": "1.2.3"}
        url = "https://github.com/org/repo/releases/download/v1.2.3/test-1.2.3.tgz"
        for digest in [hashlib.sha256(archive).hexdigest(), "0" * 64, None]:
            entry = {"version": "1.2.3", "digest": digest, "urls": [url]}
            index = yaml.safe_dump({"entries": {"test": [{"version": "9.9.9"}, entry]}}).encode()
            responses = [
                io.BytesIO(index),
                io.BytesIO(json.dumps({"assets": [{"name": "test-1.2.3.tgz", "id": 42}]}).encode()),
                io.BytesIO(archive),
            ]
            destination = self.root / "verified-chart.tgz"
            destination.unlink(missing_ok=True)
            with (
                self.subTest(digest=digest),
                patch.object(render.urllib.request, "urlopen", side_effect=responses) as fetch,
            ):
                if digest == hashlib.sha256(archive).hexdigest():
                    self.assertEqual(destination, render.github_chart_fallback(source, self.root))
                    self.assertEqual(archive, destination.read_bytes())
                    self.assertEqual(
                        "https://api.github.com/repos/org/repo/releases/assets/42",
                        fetch.call_args.args[0].full_url,
                    )
                    self.assertEqual(
                        "application/octet-stream", fetch.call_args.args[0].get_header("Accept")
                    )
                else:
                    with self.assertRaises(ValueError):
                        render.github_chart_fallback(source, self.root)
                    self.assertFalse(destination.exists())

    def test_download_fallback_preserves_helm_render_options(self):
        source = {
            "repoURL": "https://charts.invalid",
            "chart": "test",
            "targetRevision": "1.2.3",
            "helm": {"values": "replicas: 2", "parameters": [{"name": "replicas", "value": "3"}]},
        }
        archive = self.root / "verified-chart.tgz"
        with (
            patch.object(
                render, "run", side_effect=[render.HelmDownloadError("private"), "rendered"]
            ) as run,
            patch.object(render, "github_chart_fallback", return_value=archive),
            patch("builtins.print"),
        ):
            self.assertEqual(
                "rendered",
                render.render_source(self.app, source, [source], self.root, self.root, "1.37.1"),
            )
        original, fallback = [call.args[0] for call in run.call_args_list]
        expected = original.copy()
        expected[3] = str(archive)
        for flag in ["--repo", "--version"]:
            position = expected.index(flag)
            del expected[position : position + 2]
        self.assertEqual(expected, fallback)

    def test_download_fallback_errors_hide_signed_urls(self):
        source = {"repoURL": "https://charts.invalid", "chart": "test", "targetRevision": "1.2.3"}
        with (
            patch.object(render, "run", side_effect=render.HelmDownloadError("private")),
            patch.object(
                render, "github_chart_fallback", side_effect=ValueError("signed-secret-url")
            ),
            patch("builtins.print"),
            self.assertRaises(RuntimeError) as error,
        ):
            render.render_source(self.app, source, [source], self.root, self.root, "1.37.1")
        self.assertNotIn("signed-secret", str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    def test_additional_crd_url_supports_pinned_runtime_controller_release(self):
        source = {"version": "v1.14.2", "url": "https://example.invalid/v{version}/crd.yaml"}
        self.assertEqual(
            "https://example.invalid/v1.14.2/crd.yaml", validate.additional_crd_url(source)
        )

    def test_additional_crd_url_uses_helm_controller_release(self):
        app = {"spec": {"source": {"chart": "controller", "targetRevision": "v1.2.3"}}}
        with patch.object(validate, "load", return_value=app):
            with patch.object(Path, "read_text", return_value="unused"):
                self.assertEqual(
                    "https://example.invalid/v1.2.3/crd.yaml",
                    validate.additional_crd_url(
                        {
                            "application": "controller",
                            "url": "https://example.invalid/v{version}/crd.yaml",
                        }
                    ),
                )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = {"metadata": {"name": "test"}, "spec": {"destination": {"namespace": "target"}}}

    def test_values_reference_inline_and_parameters_follow_argo_precedence(self):
        (self.root / "values.yaml").write_text("replicas: 1\n")
        source = {
            "repoURL": "https://example.invalid/charts",
            "chart": "test",
            "targetRevision": "1.2.3",
            "helm": {
                "releaseName": "release",
                "valueFiles": ["$values/values.yaml"],
                "values": "replicas: 2\n",
                "valuesObject": {"replicas": 3},
                "parameters": [
                    {"name": "replicas", "value": "4"},
                    {"name": "code", "value": "001", "forceString": True},
                ],
            },
        }
        refs = [source, {"repoURL": render.REPO, "ref": "values"}]
        scratch = self.root / "scratch"
        scratch.mkdir()
        args = render.helm_args(self.app, source, refs, self.root, scratch, "1.36.4")
        self.assertEqual("release", args[2])
        self.assertEqual("target", args[args.index("--namespace") + 1])
        self.assertEqual("1.36.4", args[args.index("--kube-version") + 1])
        values = [args[i + 1] for i, a in enumerate(args) if a == "--values"]
        self.assertEqual([str(self.root / "values.yaml"), str(scratch / "values.yaml")], values)
        self.assertEqual({"replicas": 3}, yaml.safe_load((scratch / "values.yaml").read_text()))
        self.assertEqual(["--set", "replicas=4", "--set-string", "code=001"], args[-4:])

    def test_oci_chart_uses_registry_path(self):
        source = {
            "repoURL": "ghcr.io/openbao/charts",
            "chart": "openbao",
            "targetRevision": "0.29.4",
        }
        args = render.helm_args(self.app, source, [source], self.root, self.root, "1.36.4")
        self.assertIn("oci://ghcr.io/openbao/charts/openbao", args)
        self.assertNotIn("--repo", args)

    def test_unknown_options_and_values_outside_repo_fail(self):
        source = {
            "repoURL": "https://example.invalid",
            "chart": "test",
            "targetRevision": "1",
            "helm": {"fileParameters": []},
        }
        with self.assertRaises(ValueError):
            render.helm_args(self.app, source, [], self.root, self.root, "1.36.4")
        with self.assertRaises(ValueError):
            render.local_path(self.root, "../escape")

    def test_oci_pull_metadata_is_removed_without_changing_manifests(self):
        source = {
            "repoURL": "ghcr.io/openbao/charts",
            "chart": "openbao",
            "targetRevision": "0.29.4",
        }
        manifest = (
            "---\napiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\n"
            "data:\n  Pulled: keep\n  Digest: keep\n"
        )
        preamble = (
            "Pulled: ghcr.io/openbao/charts/openbao:0.29.4\nDigest: sha256:" + "a" * 64 + "\n"
        )
        for prefix in ["", preamble, preamble.replace("\n", "\r\n")]:
            with (
                self.subTest(prefix=prefix),
                patch.object(render, "run", return_value=prefix + manifest),
            ):
                output = render.render_source(
                    self.app, source, [source], self.root, self.root, "1.36.4"
                )
                self.assertEqual(manifest, output)
                self.assertEqual(["ConfigMap"], [doc["kind"] for doc in validate.documents(output)])
        unexpected = "unexpected: output\n" + manifest
        with patch.object(render, "run", return_value=unexpected):
            self.assertEqual(
                unexpected,
                render.render_source(self.app, source, [source], self.root, self.root, "1.36.4"),
            )

    def test_directory_include_exclude_and_recursion(self):
        appdir = self.root / "app"
        appdir.mkdir()
        (appdir / "nested").mkdir()
        for name in ["keep.yaml", "drop.yaml", "nested/nested.yaml"]:
            (appdir / name).write_text(
                "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: " + Path(name).stem + "\n"
            )
        source = {
            "repoURL": render.REPO,
            "path": "app",
            "directory": {"include": "{keep.yaml,drop.yaml}", "exclude": "drop.yaml"},
        }
        output = render.render_source(self.app, source, [source], self.root, self.root, "1.36.4")
        self.assertEqual(["keep"], [d["metadata"]["name"] for d in yaml.safe_load_all(output)])

    def test_kustomize_source_is_built(self):
        appdir = self.root / "app"
        appdir.mkdir()
        (appdir / "kustomization.yaml").write_text("resources: []")
        source = {"repoURL": render.REPO, "path": "app"}
        with patch.object(render, "run", return_value="rendered") as run:
            self.assertEqual(
                "rendered",
                render.render_source(self.app, source, [source], self.root, self.root, "1.36.4"),
            )
            run.assert_called_once_with(["kubectl", "kustomize", str(appdir)])

    def test_schema_rejects_unknown_fields_wrong_types_and_missing_schema(self):
        schema = validate.convert_schema(
            {
                "type": "object",
                "properties": {
                    "spec": {"type": "object", "properties": {"count": {"type": "integer"}}}
                },
            }
        )
        # Test conversion directly, avoiding implicit Kubernetes metadata fields.
        validator = validate.jsonschema.Draft7Validator(schema)
        self.assertFalse(list(validator.iter_errors({"spec": {"count": 1}})))
        self.assertTrue(list(validator.iter_errors({"spec": {"count": "wrong"}})))
        self.assertTrue(list(validator.iter_errors({"spec": {"typo": 1}})))
        self.assertEqual(
            ["missing schema"],
            validate.custom_errors({"apiVersion": "unknown/v1", "kind": "Thing"}, {}),
        )

    def test_nullable_int_or_string_and_preserved_unknown_fields(self):
        schema = validate.convert_schema(
            {
                "type": "object",
                "properties": {
                    "port": {"x-kubernetes-int-or-string": True},
                    "nullable": {"type": "string", "nullable": True},
                    "plugin": {"type": "object", "x-kubernetes-preserve-unknown-fields": True},
                },
            }
        )
        validator = validate.jsonschema.Draft7Validator(schema)
        for port in [80, "http"]:
            self.assertFalse(
                list(
                    validator.iter_errors(
                        {"port": port, "nullable": None, "plugin": {"custom": True}}
                    )
                )
            )
        self.assertTrue(list(validator.iter_errors({"port": False})))

    def test_custom_validation_uses_served_version_and_constraints(self):
        crd = {
            "kind": "CustomResourceDefinition",
            "spec": {
                "group": "example.io",
                "names": {"kind": "Thing"},
                "versions": [
                    {
                        "name": "v1",
                        "served": True,
                        "schema": {
                            "openAPIV3Schema": {
                                "type": "object",
                                "properties": {
                                    "spec": {
                                        "type": "object",
                                        "required": ["count"],
                                        "properties": {"count": {"type": "integer"}},
                                    }
                                },
                            }
                        },
                    }
                ],
            },
        }
        schemas = validate.collect_schemas([crd])
        doc = {
            "apiVersion": "example.io/v1",
            "kind": "Thing",
            "metadata": {"name": "test"},
            "spec": {"count": 1},
        }
        self.assertEqual([], validate.custom_errors(doc, schemas))
        doc["spec"]["count"] = "wrong"
        self.assertTrue(validate.custom_errors(doc, schemas))
        doc["apiVersion"] = "example.io/v2"
        self.assertEqual(["missing schema"], validate.custom_errors(doc, schemas))

    def test_duplicate_yaml_keys_fail_before_normalization(self):
        with self.assertRaises(ValueError):
            list(
                validate.documents(
                    "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: first\n  name: second\n"
                )
            )

    def test_custom_yaml_loader_rejects_python_object_constructors(self):
        from ci_yaml import load, load_all

        payload = '!!python/object/apply:builtins.str ["synthetic-payload"]'
        for parse in (load, lambda text: list(load_all(text))):
            with self.subTest(parse=parse), self.assertRaises(yaml.constructor.ConstructorError):
                parse(payload)

    def test_crd_checks_reject_missing_storage_version(self):
        self.assertTrue(
            validate.crd_errors(
                {
                    "apiVersion": "apiextensions.k8s.io/v1",
                    "kind": "CustomResourceDefinition",
                    "spec": {},
                }
            )
        )

    def test_remote_chart_is_rendered_outside_colliding_repo_directory(self):
        source = {
            "repoURL": "https://example.invalid/charts",
            "chart": "test",
            "targetRevision": "1",
        }
        with patch.object(render, "run", return_value="rendered") as run:
            render.render_source(self.app, source, [source], self.root, self.root, "1.36.4")
            self.assertEqual(self.root, run.call_args.kwargs["cwd"])

    def test_kubernetes_unicode_regex_categories_are_enforced(self):
        validator = validate.CRDValidator(
            validate.convert_schema({"type": "string", "pattern": r"^\PC*$"})
        )
        self.assertFalse(list(validator.iter_errors("readable text")))
        self.assertTrue(list(validator.iter_errors("contains\x00control")))

    def test_discovery_excludes_raw_webhook_templates_but_keeps_manifests(self):
        discovery = module("discovery_webhook_test", "list-k8s-manifest-files.py")
        paths = {str(p.relative_to(ROOT)) for p in discovery.tracked_yaml_files(ROOT)}
        self.assertNotIn("tools/godaddy-webhook/chart/templates/credentials.yaml", paths)
        self.assertNotIn("tools/godaddy-webhook/chart/templates/solver.yaml", paths)
        self.assertIn("argocd/application-godaddy-webhook.yaml", paths)
        # The chart is still part of the required application render inventory.
        app = yaml.safe_load((ROOT / "argocd/application-godaddy-webhook.yaml").read_text())
        self.assertEqual("tools/godaddy-webhook/chart", app["spec"]["source"]["path"])

    def test_discovery_excludes_talos_machine_configurations(self):
        discovery = module("discovery_test", "list-k8s-manifest-files.py")
        files = discovery.tracked_yaml_files(ROOT)
        self.assertNotIn(ROOT / "talos-existing-storage-volume.yaml", files)
        self.assertFalse(any(p.is_relative_to(ROOT / "talos") for p in files))
        migration = ROOT / "docs/migrations/infrastructure-vlan"
        hostname_patches = sorted(migration.glob("talos-*-hostname.patch.yaml"))
        self.assertEqual(3, len(hostname_patches))
        for path in hostname_patches:
            self.assertNotIn(path, files)
        self.assertIn(ROOT / "metrics/cluster-role-platform-health-report.yaml", files)
