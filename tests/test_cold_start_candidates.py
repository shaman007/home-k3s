"""Cold-start candidate safety and separation of public/internal dependencies."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cold_start', ROOT / 'tools/bootstrap/prepare_cold_start.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ColdStartCandidates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt',
                        'ec_paramgen_curve:prime256v1', '-nodes', '-days', '2',
                        '-subj', '/CN=TEST ONLY bootstrap root', '-addext',
                        'basicConstraints=critical,CA:TRUE', '-keyout', str(cls.base / 'key.pem'),
                        '-out', str(cls.base / 'ca.pem')], check=True, capture_output=True)
        cls.pem = (cls.base / 'ca.pem').read_text()
        cls.out = cls.base / 'candidate'
        cls.summary = module.prepare(ROOT, cls.out, cls.pem, '192.168.30.250')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_both_backends_and_raft_use_internal_trust(self):
        app = yaml.safe_load((self.out / 'argocd/application-openbao.yaml').read_text())
        values = yaml.safe_load(app['spec']['source']['helm']['values'])
        config = values['server']['ha']['raft']['config']
        internal, public = config.split('listener "tcp" {')[1:]
        self.assertIn(module.CERT_DIR + '/tls.crt', internal)
        self.assertIn(module.CERT_DIR + '/tls.crt', public)
        self.assertIn({'type': 'secret', 'name': 'openbao-server-letsencrypt-tls'},
                      values['server']['extraVolumes'])
        self.assertIn('leader_ca_cert_file', config)
        self.assertNotIn(module.OLD, config)
        self.assertEqual(module.OLD, values['server']['ha']['apiAddr'])

    def test_ingress_and_metrics_verify_internal_ca(self):
        transport = yaml.safe_load((self.out / 'openbao/servers-transport-openbao-server.yaml').read_text())
        self.assertEqual(['openbao-backend-trust'], transport['spec']['rootCAsSecrets'])
        self.assertNotIn('insecureSkipVerify', transport['spec'])
        cm = yaml.safe_load((self.out / 'metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml').read_text())
        config = yaml.safe_load(next(v for v in cm['data'].values() if 'job_name: openbao' in v))
        job = next(j for j in config['scrape_configs'] if j.get('job_name') == 'openbao')
        self.assertEqual('/etc/openbao-ca/ca.crt', job['tls_config']['ca_file'])
        deployment = yaml.safe_load((self.out / 'metrics/kubernetes-prometheus/deployment-prometheus-deployment.yaml').read_text())
        self.assertTrue(any(m['mountPath'] == '/etc/openbao-ca'
                            for c in deployment['spec']['template']['spec']['containers']
                            for m in c.get('volumeMounts', [])))

    def test_all_inventory_stores_use_pinned_internal_ca(self):
        self.assertGreater(self.summary['secret_stores'], 30)
        self.assertIn('cert-manager', self.summary['trust_namespaces'])
        store = yaml.safe_load_all((self.out / 'firefox-sync/secret-store-vault-secret-store.yaml').read_text())
        vault = next(store)['spec']['provider']['vault']
        self.assertEqual(module.NEW, vault['server'])
        self.assertTrue(vault['caBundle'])
        app = yaml.safe_load((self.out / 'argocd/application-godaddy-webhook.yaml').read_text())
        values = yaml.safe_load(app['spec']['source']['helm']['values'])
        self.assertFalse(values['openbao']['useSystemTrust'])
        self.assertEqual(module.NEW, values['openbao']['server'])

    def test_harbor_controller_has_no_optional_bootstrap_dependencies(self):
        app = yaml.safe_load((self.out / 'argocd/application-traefik-registry.yaml').read_text())
        values = yaml.safe_load(app['spec']['source']['helm']['values'])
        for key in ('experimental', 'volumes', 'additionalArguments'):
            self.assertNotIn(key, values)
        self.assertFalse(values['persistence']['enabled'])
        self.assertFalse(values['providers']['kubernetesCRD']['enabled'])
        self.assertEqual(['harbor'], values['providers']['kubernetesIngress']['namespaces'])
        ingress = yaml.safe_load((self.out / 'harbor/ingress-harbor-internal-registry.yaml').read_text())
        self.assertEqual('traefik-registry', ingress['spec']['ingressClassName'])
        self.assertEqual('harbor-tls', ingress['spec']['tls'][0]['secretName'])
        self.assertNotIn('traefik.ingress.kubernetes.io/router.middlewares', ingress['metadata']['annotations'])
        self.assertFalse((self.out / 'harbor/ingress-andreybondarenko-ingress.yaml').exists())

    def test_new_files_match_existing_argocd_source_filters(self):
        import fnmatch
        from collections import defaultdict
        files = defaultdict(list)
        for path in self.summary['files']:
            files[Path(path).parent.as_posix()].append(Path(path).name)
        for appname, directory in [('metallb-config', 'metallb'), ('openbao-custom', 'openbao'),
                                    ('harbor-custom', 'harbor')]:
            app = yaml.safe_load((ROOT / f'argocd/application-{appname}.yaml').read_text())
            pattern = app['spec']['source']['directory']['include']
            patterns = pattern.strip('{}').split(',')
            for name in files[directory]:
                self.assertTrue(any(fnmatch.fnmatch(name, p) for p in patterns), name)

    def test_private_key_input_and_invalid_vip_are_rejected(self):
        with self.assertRaises(ValueError):
            module.prepare(ROOT, self.base / 'bad-key', '-----BEGIN ' + 'PRIVATE KEY-----', '192.168.30.250')
        with self.assertRaises(ValueError):
            module.prepare(ROOT, self.base / 'bad-vip', self.pem, '8.8.8.8')

    def test_no_generated_private_key_or_plaintext_credential(self):
        for path in self.out.rglob('*.yaml'):
            self.assertNotIn('PRIVATE KEY', path.read_text())
        self.assertFalse(self.summary['active'])


if __name__ == '__main__':
    unittest.main()
