#!/usr/bin/env python3
"""Build inactive cold-start candidates. Never calls Kubernetes or edits sources."""
import argparse
import base64
import ipaddress
import json
from pathlib import Path
import ssl
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]
OLD = 'https://openbao-api.int.andreybondarenko.com:8200'
NEW = 'https://openbao-active.openbao.svc.cluster.local:8200'
CERT_DIR = '/openbao/userconfig/openbao-server-letsencrypt-tls'


def load(path):
    return list(yaml.safe_load_all(path.read_text()))


def convert_stores(value, namespaces, ca_bundle, namespace=None):
    """Convert only Vault SecretStores, including Helm values extraObjects."""
    count = 0
    if isinstance(value, dict):
        namespace = value.get('metadata', {}).get('namespace', namespace)
        if value.get('kind') in ('SecretStore', 'ClusterSecretStore'):
            vault = value.get('spec', {}).get('provider', {}).get('vault', {})
            if vault.get('server') in (OLD, NEW):
                if value['kind'] == 'ClusterSecretStore':
                    namespace = '(cluster-scoped)'
                if not namespace:
                    raise ValueError('Explicit namespace handling required for store: ' +
                                     str(value.get('metadata')))
                vault['server'] = NEW
                vault.pop('caProvider', None)
                vault['caBundle'] = ca_bundle
                namespaces.add(namespace)
                count += 1
        for child in value.values():
            count += convert_stores(child, namespaces, ca_bundle, namespace)
    elif isinstance(value, list):
        for child in value:
            count += convert_stores(child, namespaces, ca_bundle, namespace)
    return count


def openbao_values(values):
    server = values['server']
    # Keep existing projected Secret paths for restart-free certificate reload.
    server['extraEnvironmentVars']['BAO_CACERT'] = CERT_DIR + '/ca.crt'
    config = server['ha']['raft']['config']
    # No mandatory ACME Secret may remain on either backend listener.
    config = config.replace(OLD, NEW)
    config = config.replace('leader_tls_servername = "openbao-api.int.andreybondarenko.com"',
                            'leader_tls_servername = "openbao-active.openbao.svc.cluster.local"\n'
                            '    leader_ca_cert_file = "' + CERT_DIR + '/ca.crt"')
    server['ha']['raft']['config'] = config


def harbor_application(vip):
    source = yaml.safe_load((ROOT / 'argocd/application-traefik-private.yaml').read_text())
    app = {'apiVersion': source['apiVersion'], 'kind': 'Application',
           'metadata': {'name': 'traefik-registry', 'namespace': 'argocd'},
           'spec': {'project': 'platform', 'source': {
               'repoURL': source['spec']['source']['repoURL'], 'chart': 'traefik',
               'targetRevision': source['spec']['source']['targetRevision'],
               'helm': {'releaseName': 'traefik-registry'}},
               'destination': {'server': 'https://kubernetes.default.svc', 'namespace': 'traefik'}}}
    values = {
        'image': {'registry': 'docker.io', 'repository': 'traefik', 'tag': 'v3.7.18'},
        'deployment': {'replicas': 2},
        'ingressClass': {'enabled': True, 'name': 'traefik-registry', 'isDefaultClass': False},
        'providers': {'kubernetesIngress': {'enabled': True, 'ingressClass': 'traefik-registry',
                      'namespaces': ['harbor'], 'publishedService': {'enabled': True,
                      'pathOverride': 'traefik/traefik-registry'}},
                      'kubernetesCRD': {'enabled': False}},
        'service': {'annotations': {'metallb.io/loadBalancerIPs': vip,
                                  'metallb.io/address-pool': 'registry-bootstrap'},
                    'spec': {'type': 'LoadBalancer', 'loadBalancerClass': 'metallb-l2',
                             'externalTrafficPolicy': 'Local', 'ipFamilyPolicy': 'SingleStack',
                             'ipFamilies': ['IPv4'],
                             'loadBalancerSourceRanges': ['192.168.30.0/24', '192.168.1.0/24',
                                                         '192.168.4.0/24', '10.42.0.0/16']}},
        'ports': {'web': {'expose': {'default': False}},
                  'websecure': {'http': {'tls': {'enabled': True}}}},
        'persistence': {'enabled': False}, 'priorityClassName': 'homelab-critical',
        'tolerations': [{'key': 'node-role.kubernetes.io/control-plane', 'operator': 'Exists',
                         'effect': 'NoSchedule'}],
        'affinity': {'podAntiAffinity': {'requiredDuringSchedulingIgnoredDuringExecution': [{
            'labelSelector': {'matchLabels': {'app.kubernetes.io/instance': 'traefik-registry-traefik'}},
            'topologyKey': 'kubernetes.io/hostname'}]}},
        'resources': {'requests': {'cpu': '50m', 'memory': '128Mi'}, 'limits': {'memory': '512Mi'}}}
    app['spec']['source']['helm']['values'] = yaml.safe_dump(values, sort_keys=False)
    return app


def prepare(root, out, ca_pem, vip):
    # Only public X.509 CA certificates may enter the generated repository diff.
    if 'PRIVATE KEY' in ca_pem:
        raise ValueError('Private key input is forbidden')
    subprocess.run(['openssl', 'x509', '-noout', '-checkend', '0'], input=ca_pem,
                   text=True, check=True, capture_output=True)
    details = subprocess.run(['openssl', 'x509', '-noout', '-text'], input=ca_pem,
                             text=True, check=True, capture_output=True).stdout
    if 'CA:TRUE' not in details:
        raise ValueError('Input certificate is not a CA')
    ssl.PEM_cert_to_DER_cert(ca_pem)
    ip = ipaddress.ip_address(vip)
    if ip.version != 4 or ip not in ipaddress.ip_network('192.168.30.0/24'):
        raise ValueError('Choose an independently verified free infrastructure IPv4 VIP')
    if out.exists():
        raise ValueError('Output must be a new directory')
    out.mkdir(parents=True)
    namespaces = {'cert-manager'}
    ca_bundle = base64.b64encode(ca_pem.encode()).decode()
    changes = {}
    stores = 0
    destinations = {}
    for path in (root / 'argocd').glob('application-*.yaml'):
        app = yaml.safe_load(path.read_text())
        if app.get('kind') != 'Application':
            continue
        spec = app['spec']
        for source in spec.get('sources', [spec.get('source', {})]):
            if 'path' in source:
                destinations[source['path']] = spec.get('destination', {}).get('namespace')
    for path in sorted(root.rglob('*.yaml')):
        rel = path.relative_to(root)
        if rel.parts[0] in ('docs', 'DEPRECATED', 'tests', 'tools', '.git'):
            continue
        text = path.read_text()
        if OLD not in text and NEW not in text and rel.as_posix() != 'argocd/application-openbao.yaml':
            continue
        docs = load(path)
        changed = False
        for doc in docs:
            n = convert_stores(doc, namespaces, ca_bundle,
                               destinations.get(rel.parent.as_posix()))
            stores += n
            changed |= bool(n)
            if not isinstance(doc, dict) or doc.get('kind') != 'Application':
                continue
            spec = doc['spec']
            sources = spec.get('sources', [spec.get('source', {})])
            for source in sources:
                helm = source.get('helm', {})
                if 'values' not in helm:
                    continue
                values = yaml.safe_load(helm['values'])
                n = convert_stores(values, namespaces, ca_bundle,
                                   spec.get('destination', {}).get('namespace'))
                stores += n
                if doc['metadata']['name'] == 'openbao':
                    openbao_values(values)
                    n += 1
                if doc['metadata']['name'] == 'godaddy-webhook':
                    values['openbao'].update(server=NEW, useSystemTrust=False,
                                              caBundle=base64.b64encode(ca_pem.encode()).decode())
                    n += 1
                if n:
                    helm['values'] = yaml.safe_dump(values, sort_keys=False)
                    changed = True
        if changed:
            changes[rel.as_posix()] = yaml.safe_dump_all(docs, sort_keys=False)
    changes['argocd/application-traefik-registry.yaml'] = yaml.safe_dump(harbor_application(vip), sort_keys=False)
    ingress = yaml.safe_load((root / 'harbor/ingress-andreybondarenko-ingress.yaml').read_text())
    ingress['metadata']['name'] = 'harbor-internal-registry'
    ingress['metadata']['annotations'] = {
        'traefik.ingress.kubernetes.io/router.entrypoints': 'websecure',
        'traefik.ingress.kubernetes.io/router.tls': 'true'}
    ingress['spec']['ingressClassName'] = 'traefik-registry'
    changes['harbor/ingress-harbor-internal-registry.yaml'] = yaml.safe_dump(ingress, sort_keys=False)
    pool = {'apiVersion': 'metallb.io/v1beta1', 'kind': 'IPAddressPool',
            'metadata': {'name': 'registry-bootstrap', 'namespace': 'metallb-system'},
            'spec': {'autoAssign': False, 'addresses': [vip + '/32']}}
    advertisement = {'apiVersion': 'metallb.io/v1beta1', 'kind': 'BGPAdvertisement',
                     'metadata': {'name': 'registry-bootstrap', 'namespace': 'metallb-system'},
                     'spec': {'ipAddressPools': ['registry-bootstrap'], 'peers': ['udm-bgp-trial'],
                              'aggregationLength': 32}}
    l2 = {'apiVersion': 'metallb.io/v1beta1', 'kind': 'L2Advertisement',
          'metadata': {'name': 'registry-bootstrap', 'namespace': 'metallb-system'},
          'spec': {'ipAddressPools': ['registry-bootstrap']}}
    changes['metallb/ip-address-pool-registry-bootstrap.yaml'] = yaml.safe_dump(pool, sort_keys=False)
    changes['metallb/bgp-advertisement-registry-bootstrap.yaml'] = yaml.safe_dump(advertisement, sort_keys=False)
    changes['metallb/l2-advertisement-registry-bootstrap.yaml'] = yaml.safe_dump(l2, sort_keys=False)
    changes['openbao/internal-pki.yaml'] = (root / 'docs/migrations/openbao-internal-tls/pki.yaml').read_text()
    transport = yaml.safe_load((root / 'openbao/servers-transport-openbao-server.yaml').read_text())
    transport['spec']['rootCAsSecrets'] = ['openbao-backend-trust']
    changes['openbao/servers-transport-openbao-server.yaml'] = yaml.safe_dump(transport, sort_keys=False)
    trust = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {
        'name': 'openbao-backend-trust', 'namespace': 'openbao'}, 'type': 'Opaque',
        'data': {'ca.crt': ca_bundle}}
    changes['openbao/secret-openbao-backend-trust.yaml'] = yaml.safe_dump(trust, sort_keys=False)
    ca_cm = yaml.safe_load((root / 'metrics/kubernetes-prometheus/config-map-vault-ca.yaml').read_text())
    ca_cm['data']['ca.crt'] = ca_pem
    changes['metrics/kubernetes-prometheus/config-map-vault-ca.yaml'] = yaml.safe_dump(ca_cm, sort_keys=False)
    prom_path = root / 'metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml'
    prom = yaml.safe_load(prom_path.read_text())
    for key, content in prom['data'].items():
        if 'job_name: openbao' not in content:
            continue
        config = yaml.safe_load(content)
        job = next(j for j in config['scrape_configs'] if j.get('job_name') == 'openbao')
        job['tls_config'] = {'server_name': 'openbao-active.openbao.svc.cluster.local',
                             'ca_file': '/etc/openbao-ca/ca.crt'}
        job['static_configs'] = [{'targets': ['openbao-active.openbao.svc.cluster.local:8200']}]
        prom['data'][key] = yaml.safe_dump(config, sort_keys=False)
    changes[prom_path.relative_to(root).as_posix()] = yaml.safe_dump(prom, sort_keys=False)
    deployment_path = root / 'metrics/kubernetes-prometheus/deployment-prometheus-deployment.yaml'
    deployment = yaml.safe_load(deployment_path.read_text())
    pod = deployment['spec']['template']['spec']
    pod['volumes'] = [v for v in pod['volumes'] if v['name'] != 'openbao-internal-ca']
    pod['volumes'].append({'name': 'openbao-internal-ca', 'configMap': {'name': 'vault-ca'}})
    for container in pod['containers']:
        if 'prometheus' in container['name']:
            container['volumeMounts'] = [m for m in container.get('volumeMounts', [])
                                         if m['name'] != 'openbao-internal-ca']
            container.setdefault('volumeMounts', []).append({'name': 'openbao-internal-ca',
                'mountPath': '/etc/openbao-ca', 'readOnly': True})
    changes[deployment_path.relative_to(root).as_posix()] = yaml.safe_dump(deployment, sort_keys=False)
    for rel, content in changes.items():
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
    summary = {'secret_stores': stores, 'trust_namespaces': sorted(namespaces),
               'files': sorted(changes), 'harbor_vip': vip, 'active': False,
               'ca_sha256': subprocess.run(['openssl', 'x509', '-noout', '-fingerprint', '-sha256'],
                                           input=ca_pem, text=True, check=True,
                                           capture_output=True).stdout.strip()}
    (out / 'inventory.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ca-cert', required=True, type=Path, help='Public CA certificate only')
    parser.add_argument('--harbor-vip', required=True, help='Verified free infrastructure IPv4 VIP')
    parser.add_argument('--output', required=True, type=Path, help='New directory outside source tree')
    args = parser.parse_args()
    out = args.output.resolve()
    if out == ROOT or ROOT in out.parents:
        parser.error('Output must be outside the source repository')
    print(json.dumps(prepare(ROOT, out, args.ca_cert.read_text(), args.harbor_vip), indent=2))


if __name__ == '__main__':
    main()
