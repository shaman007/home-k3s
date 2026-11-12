"""Keep the experimental proxy's IPv6 and client-only security boundaries."""
import configparser
import ipaddress
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return yaml.safe_load((ROOT / name).read_text())


class I2pdIsolationTest(unittest.TestCase):
    def test_client_only_configuration(self):
        config = configparser.ConfigParser()
        config.read_string('[router]\n' + load('i2pd/config-map-i2pd.yaml')['data']['i2pd.conf'])
        for section, key, expected in (
            ('router', 'ipv4', False), ('router', 'ipv6', True),
            ('router', 'notransit', True), ('router', 'floodfill', False),
            ('ntcp2', 'published', False), ('ssu2', 'enabled', False),
            ('socksproxy', 'outproxy.enabled', False),
            ('upnp', 'enabled', False), ('sam', 'enabled', False),
            ('http', 'enabled', False), ('i2cp', 'enabled', False),
        ):
            self.assertEqual(config.getboolean(section, key), expected, (section, key))
        self.assertFalse(config.get('httpproxy', 'outproxy').strip())
        data = load('i2pd/config-map-i2pd.yaml')['data']
        self.assertFalse(data['tunnels.conf'].strip())
        self.assertIn('--httpproxy.address="$ipv6"', data['start.sh'])
        self.assertIn('--socksproxy.address="$ipv6"', data['start.sh'])
        self.assertIn('test -n "$ipv6"', data['start.sh'])

    def test_ipv4_denied_and_only_global_ipv6_allowed_out(self):
        spec = load('i2pd/cilium-network-policy-i2pd.yaml')['spec']
        self.assertEqual(spec['endpointSelector'], {})
        self.assertIn({'fromCIDR': ['0.0.0.0/0']}, spec['ingressDeny'])
        self.assertIn({'toCIDR': ['0.0.0.0/0']}, spec['egressDeny'])
        self.assertEqual(spec['ingress'][0]['fromCIDR'], ['2a02:e98:c0:181e::/64'])
        for rule in spec['egress']:
            self.assertLessEqual(set(rule), {'toCIDR', 'toCIDRSet', 'toPorts'})
            networks = rule.get('toCIDR', []) + [x['cidr'] for x in rule.get('toCIDRSet', [])]
            for cidr in networks:
                self.assertTrue(ipaddress.ip_network(cidr).subnet_of(ipaddress.ip_network('2000::/3')))
        self.assertIn('2a02:e98:c0:181e::/64', spec['egress'][0]['toCIDRSet'][0]['except'])

    def test_ipv6_service_without_node_ports(self):
        svc = load('i2pd/service-i2pd.yaml')['spec']
        self.assertEqual(svc['ipFamilies'], ['IPv6'])
        self.assertEqual(svc['ipFamilyPolicy'], 'SingleStack')
        self.assertFalse(svc['allocateLoadBalancerNodePorts'])
        self.assertEqual(svc['externalTrafficPolicy'], 'Local')
        self.assertEqual(svc['loadBalancerSourceRanges'], ['2a02:e98:c0:181e::/64'])
        self.assertEqual({p['port'] for p in svc['ports']}, {4444, 4447})
        self.assertTrue(all('nodePort' not in p for p in svc['ports']))

    def test_no_ipv4_dns_or_probe_fallback(self):
        pod = load('i2pd/deployment-i2pd.yaml')['spec']['template']['spec']
        self.assertEqual(pod['dnsPolicy'], 'None')
        self.assertTrue(all(ipaddress.ip_address(ip).version == 6 for ip in pod['dnsConfig']['nameservers']))
        self.assertFalse(pod.get('hostNetwork', False))
        self.assertFalse(pod['automountServiceAccountToken'])
        for container in pod['containers']:
            self.assertIn('@sha256:', container['image'])
            for probe in ('startupProbe', 'readinessProbe'):
                self.assertIn('/proc/net/tcp6', container[probe]['exec']['command'][-1])
        app = load('argocd/application-i2pd.yaml')
        self.assertNotIn('automated', app['spec']['syncPolicy'])
