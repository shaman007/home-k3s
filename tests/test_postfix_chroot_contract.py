"""Keep Postfix master.cf compatible with its container capability boundary."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class PostfixChrootContractTest(unittest.TestCase):
    def test_chrooted_services_require_sys_chroot(self):
        deployment = yaml.safe_load((ROOT / 'mail/deployment-postfix.yaml').read_text())
        container = deployment['spec']['template']['spec']['containers'][0]
        caps = container['securityContext'].get('capabilities', {})
        available = 'SYS_CHROOT' in caps.get('add', []) or not (
            {'ALL', 'SYS_CHROOT'} & set(caps.get('drop', [])))
        if available:
            return
        master = yaml.safe_load((ROOT / 'mail/config-map-main-cf.yaml').read_text())['data']['master']
        services = [line.split() for line in master.splitlines()
                    if line.strip() and not line.lstrip().startswith(('#', '-'))]
        services = [row for row in services if len(row) >= 8 and row[1] in
                    {'inet', 'unix', 'unix-dgram', 'fifo', 'pass'}]
        self.assertTrue(services, 'No Postfix master services parsed')
        for row in services:
            with self.subTest(service=row[0]):
                self.assertEqual(row[4], 'n', 'Restore SYS_CHROOT and revalidate before enabling service chroot')


if __name__ == '__main__':
    unittest.main()
