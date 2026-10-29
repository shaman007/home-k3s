from pathlib import Path
import json
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def documents(path):
    return [d for d in yaml.safe_load_all((ROOT / path).read_text()) if d]


class TraefikSecurityPluginsTest(unittest.TestCase):
    def test_console_login_requires_admin_and_preserves_network_restrictions(self):
        app = documents('argocd/application-traefik-private.yaml')[0]
        values = yaml.safe_load(app['spec']['source']['helm']['values'])
        objects = values['extraObjects']
        middleware = next(d for d in objects if d['kind'] == 'Middleware')
        oidc = middleware['spec']['plugin']['oidc']
        self.assertEqual(['admin'], oidc['Authorization']['AssertClaims'][0]['AnyOf'])
        self.assertEqual('realm_roles', oidc['Authorization']['AssertClaims'][0]['Name'])
        self.assertEqual('true', oidc['Provider']['UsePkce'])
        self.assertEqual('true', oidc['Provider']['ValidateIssuer'])
        self.assertEqual('true', oidc['Provider']['ValidateAudience'])
        self.assertTrue(oidc['SessionCookie']['Secure'])
        self.assertTrue(oidc['SessionCookie']['HttpOnly'])
        self.assertNotIn('Domain', oidc['SessionCookie'])
        self.assertTrue(oidc['Secret'].startswith('${file:'))
        self.assertTrue(oidc['Provider']['ClientSecret'].startswith('${file:'))
        self.assertNotIn('BypassAuthenticationRule', oidc)
        client = json.loads((ROOT / 'keycloak/config/traefik-admin.client.json').read_text())
        self.assertFalse(client['directAccessGrantsEnabled'])
        self.assertFalse(client['implicitFlowEnabled'])
        self.assertFalse(client['serviceAccountsEnabled'])
        self.assertEqual('S256', client['attributes']['pkce.code.challenge.method'])
        callbacks = set()
        paths = ['metrics/ingress-prometheus-ingress.yaml', 'metrics/ingress-alerts-ingress.yaml',
                 'longhorn/ingress-longhorn-ingress.yaml', 'metrics/ingress-thanos.yaml',
                 'metrics/ingress-thanos-compactor.yaml', 'metrics/ingress-thanos-store.yaml']
        for path in paths:
            ingress = next(d for d in documents(path) if d['kind'] == 'Ingress')
            self.assertEqual('traefik-private', ingress['spec']['ingressClassName'])
            chain = ingress['metadata']['annotations']['traefik.ingress.kubernetes.io/router.middlewares']
            self.assertEqual('traefik-internal-clients-only@kubernetescrd,traefik-admin-oidc@kubernetescrd', chain)
            callbacks.update('https://' + r['host'] + '/oidc/callback' for r in ingress['spec']['rules'])
        self.assertEqual(callbacks, set(client['redirectUris']))
        self.assertTrue(all('*' not in uri for uri in callbacks))

    def test_crowdsec_observes_public_logs_without_remediation_or_host_access(self):
        values = documents('crowdsec/values.yaml')[0]
        simulation = yaml.safe_load(values['config']['simulation.yaml'])
        self.assertTrue(simulation['simulation'])
        self.assertEqual([], simulation['exclusions'])
        self.assertFalse(values['appsec']['enabled'])
        self.assertTrue(values['agent']['isDeployment'])
        self.assertEqual(1, values['agent']['replicas'])
        self.assertFalse(values['agent']['hostVarLog'])
        acquisition = yaml.safe_load(documents('crowdsec/config-map-acquisition.yaml')[0]['data']['acquis.yaml'])
        self.assertEqual('kubernetes', acquisition['source'])
        self.assertEqual('traefik', acquisition['namespace'])
        self.assertEqual('app.kubernetes.io/instance=traefik-traefik', acquisition['selector'])
        role = next(d for d in documents('crowdsec/rbac.yaml') if d['kind'] == 'Role')
        self.assertEqual('traefik', role['metadata']['namespace'])
        self.assertEqual({'pods', 'pods/log'}, {r for rule in role['rules'] for r in rule['resources']})
        self.assertEqual({'get', 'list', 'watch'}, {v for rule in role['rules'] for v in rule['verbs']})
        for path in ['argocd/application-traefik.yaml', 'argocd/application-traefik-private.yaml']:
            plugins = yaml.safe_load(documents(path)[0]['spec']['source']['helm']['values'])['experimental']['plugins']
            self.assertFalse(any('crowdsec' in p['moduleName'] for p in plugins.values()))

    def test_media_cache_covers_public_mastodon_reads_with_bounded_proxy(self):
        middleware, ingress = documents('seaweedfs/ingress-route-mastodon-cache-pilot.yaml')
        rule = ingress['spec']['routes'][0]['match']
        self.assertIn('PathPrefix(`/mastodon/`)', rule)
        self.assertNotIn('ClientIP(', rule)
        self.assertNotIn('X-Mastodon-Cache-Pilot', rule)
        self.assertIn('Method(`GET`)', rule)
        self.assertIn('Method(`HEAD`)', rule)
        self.assertEqual('mastodon-media-cache', ingress['spec']['routes'][0]['services'][0]['name'])
        self.assertEqual(64, middleware['spec']['inFlightReq']['amount'])
        objects = documents('seaweedfs/media-cache.yaml')
        config = next(d['data']['nginx.conf'] for d in objects if d['kind'] == 'ConfigMap')
        deployment = next(d for d in objects if d['kind'] == 'Deployment')
        self.assertEqual(2, deployment['spec']['replicas'])
        self.assertIn('max_size=512m', config)
        self.assertIn('auth_request /__origin_head', config)
        self.assertIn('$host$request_uri|$origin_validator', config)
        self.assertIn('proxy_cache_use_stale off', config)
        self.assertNotIn('proxy_ignore_headers', config)
        self.assertIn('private, no-cache', config)
        for header in ['$http_authorization', '$http_cookie', '$http_range', '$args']:
            self.assertIn(header, config)
        mastodon = documents('mastodon/mastodon-values.yaml')[0]
        self.assertEqual('s3.andreybondarenko.com/mastodon', mastodon['mastodon']['s3']['aliasHost'])


if __name__ == '__main__':
    unittest.main()
