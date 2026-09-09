import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/ci"))


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/ci' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


render = module('render', 'render-applications.py')
validate = module('validate', 'validate-rendered.py')


class RenderValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = {'metadata': {'name': 'test'}, 'spec': {'destination': {'namespace': 'target'}}}

    def test_values_reference_inline_and_parameters_follow_argo_precedence(self):
        (self.root / 'values.yaml').write_text('replicas: 1\n')
        source = {'repoURL': 'https://example.invalid/charts', 'chart': 'test', 'targetRevision': '1.2.3',
                  'helm': {'releaseName': 'release', 'valueFiles': ['$values/values.yaml'], 'values': 'replicas: 2\n',
                           'valuesObject': {'replicas': 3}, 'parameters': [{'name': 'replicas', 'value': '4'}, {'name': 'code', 'value': '001', 'forceString': True}]}}
        refs = [source, {'repoURL': render.REPO, 'ref': 'values'}]
        scratch = self.root / 'scratch'
        scratch.mkdir()
        args = render.helm_args(self.app, source, refs, self.root, scratch, '1.36.4')
        self.assertEqual('release', args[2])
        self.assertEqual('target', args[args.index('--namespace')+1])
        self.assertEqual('1.36.4', args[args.index('--kube-version')+1])
        values = [args[i+1] for i, a in enumerate(args) if a == '--values']
        self.assertEqual([str(self.root/'values.yaml'), str(scratch/'values.yaml')], values)
        self.assertEqual({'replicas': 3}, yaml.safe_load((scratch/'values.yaml').read_text()))
        self.assertEqual(['--set', 'replicas=4', '--set-string', 'code=001'], args[-4:])

    def test_oci_chart_uses_registry_path(self):
        source = {'repoURL': 'ghcr.io/openbao/charts', 'chart': 'openbao', 'targetRevision': '0.29.4'}
        args = render.helm_args(self.app, source, [source], self.root, self.root, '1.36.4')
        self.assertIn('oci://ghcr.io/openbao/charts/openbao', args)
        self.assertNotIn('--repo', args)

    def test_unknown_options_and_values_outside_repo_fail(self):
        source = {'repoURL': 'https://example.invalid', 'chart': 'test', 'targetRevision': '1', 'helm': {'fileParameters': []}}
        with self.assertRaises(ValueError):
            render.helm_args(self.app, source, [], self.root, self.root, '1.36.4')
        with self.assertRaises(ValueError):
            render.local_path(self.root, '../escape')

    def test_oci_pull_metadata_is_removed_without_changing_manifests(self):
        source = {'repoURL': 'ghcr.io/openbao/charts', 'chart': 'openbao', 'targetRevision': '0.29.4'}
        manifest = '---\napiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\ndata:\n  Pulled: keep\n  Digest: keep\n'
        preamble = 'Pulled: ghcr.io/openbao/charts/openbao:0.29.4\nDigest: sha256:' + 'a' * 64 + '\n'
        for prefix in ['', preamble, preamble.replace('\n', '\r\n')]:
            with self.subTest(prefix=prefix), patch.object(render, 'run', return_value=prefix + manifest):
                output = render.render_source(self.app, source, [source], self.root, self.root, '1.36.4')
                self.assertEqual(manifest, output)
                self.assertEqual(['ConfigMap'], [doc['kind'] for doc in validate.documents(output)])
        unexpected = 'unexpected: output\n' + manifest
        with patch.object(render, 'run', return_value=unexpected):
            self.assertEqual(unexpected, render.render_source(self.app, source, [source], self.root, self.root, '1.36.4'))

    def test_directory_include_exclude_and_recursion(self):
        appdir = self.root / 'app'
        appdir.mkdir()
        (appdir/'nested').mkdir()
        for name in ['keep.yaml', 'drop.yaml', 'nested/nested.yaml']:
            (appdir/name).write_text('apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: '+Path(name).stem+'\n')
        source = {'repoURL': render.REPO, 'path': 'app', 'directory': {'include': '{keep.yaml,drop.yaml}', 'exclude': 'drop.yaml'}}
        output = render.render_source(self.app, source, [source], self.root, self.root, '1.36.4')
        self.assertEqual(['keep'], [d['metadata']['name'] for d in yaml.safe_load_all(output)])

    def test_kustomize_source_is_built(self):
        appdir = self.root/'app'
        appdir.mkdir()
        (appdir/'kustomization.yaml').write_text('resources: []')
        source = {'repoURL': render.REPO, 'path': 'app'}
        with patch.object(render, 'run', return_value='rendered') as run:
            self.assertEqual('rendered', render.render_source(self.app, source, [source], self.root, self.root, '1.36.4'))
            run.assert_called_once_with(['kubectl', 'kustomize', str(appdir)])

    def test_schema_rejects_unknown_fields_wrong_types_and_missing_schema(self):
        schema = validate.convert_schema({'type': 'object', 'properties': {'spec': {'type': 'object', 'properties': {'count': {'type': 'integer'}}}}})
        # Test conversion directly, avoiding implicit Kubernetes metadata fields.
        validator = validate.jsonschema.Draft7Validator(schema)
        self.assertFalse(list(validator.iter_errors({'spec': {'count': 1}})))
        self.assertTrue(list(validator.iter_errors({'spec': {'count': 'wrong'}})))
        self.assertTrue(list(validator.iter_errors({'spec': {'typo': 1}})))
        self.assertEqual(['missing schema'], validate.custom_errors({'apiVersion': 'unknown/v1', 'kind': 'Thing'}, {}))

    def test_nullable_int_or_string_and_preserved_unknown_fields(self):
        schema = validate.convert_schema({'type': 'object', 'properties': {
            'port': {'x-kubernetes-int-or-string': True},
            'nullable': {'type': 'string', 'nullable': True},
            'plugin': {'type': 'object', 'x-kubernetes-preserve-unknown-fields': True}}})
        validator = validate.jsonschema.Draft7Validator(schema)
        for port in [80, 'http']:
            self.assertFalse(list(validator.iter_errors({'port': port, 'nullable': None, 'plugin': {'custom': True}})))
        self.assertTrue(list(validator.iter_errors({'port': False})))

    def test_custom_validation_uses_served_version_and_constraints(self):
        crd = {'kind': 'CustomResourceDefinition', 'spec': {'group': 'example.io', 'names': {'kind': 'Thing'}, 'versions': [
            {'name': 'v1', 'served': True, 'schema': {'openAPIV3Schema': {'type': 'object', 'properties': {'spec': {'type': 'object', 'required': ['count'], 'properties': {'count': {'type': 'integer'}}}}}}}]}}
        schemas = validate.collect_schemas([crd])
        doc = {'apiVersion': 'example.io/v1', 'kind': 'Thing', 'metadata': {'name': 'test'}, 'spec': {'count': 1}}
        self.assertEqual([], validate.custom_errors(doc, schemas))
        doc['spec']['count'] = 'wrong'
        self.assertTrue(validate.custom_errors(doc, schemas))
        doc['apiVersion'] = 'example.io/v2'
        self.assertEqual(['missing schema'], validate.custom_errors(doc, schemas))

    def test_duplicate_yaml_keys_fail_before_normalization(self):
        with self.assertRaises(ValueError):
            list(validate.documents('apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: first\n  name: second\n'))

    def test_crd_checks_reject_missing_storage_version(self):
        self.assertTrue(validate.crd_errors({'apiVersion': 'apiextensions.k8s.io/v1', 'kind': 'CustomResourceDefinition', 'spec': {}}))

    def test_remote_chart_is_rendered_outside_colliding_repo_directory(self):
        source = {'repoURL': 'https://example.invalid/charts', 'chart': 'test', 'targetRevision': '1'}
        with patch.object(render, 'run', return_value='rendered') as run:
            render.render_source(self.app, source, [source], self.root, self.root, '1.36.4')
            self.assertEqual(self.root, run.call_args.kwargs['cwd'])

    def test_kubernetes_unicode_regex_categories_are_enforced(self):
        validator = validate.CRDValidator(validate.convert_schema({'type': 'string', 'pattern': r'^\PC*$'}))
        self.assertFalse(list(validator.iter_errors('readable text')))
        self.assertTrue(list(validator.iter_errors('contains\x00control')))

    def test_discovery_excludes_talos_machine_configurations(self):
        discovery = module('discovery_test', 'list-k8s-manifest-files.py')
        files = discovery.tracked_yaml_files(ROOT)
        self.assertNotIn(ROOT / 'talos-existing-storage-volume.yaml', files)
        self.assertFalse(any(p.is_relative_to(ROOT / 'talos') for p in files))
        self.assertIn(ROOT / 'metrics/cluster-role-platform-health-report.yaml', files)
