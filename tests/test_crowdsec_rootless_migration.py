"""Prevent a SQLite cutover from silently starting against an empty database."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class CrowdSecRootlessMigrationTest(unittest.TestCase):
    def test_migration_and_runtime_share_the_same_persistent_database(self):
        values = yaml.safe_load((ROOT / 'crowdsec/values.yaml').read_text())
        lapi = values['lapi']
        # The source writer must stop before the backup snapshot is taken.
        self.assertEqual('Recreate', lapi['strategy']['type'])
        self.assertEqual(1, lapi['replicas'])
        migration = next(c for c in lapi['extraInitContainers']
                         if c['name'] == 'prepare-rootless-database')
        source, target = map(Path, migration['command'][1:])
        selected = Path(yaml.safe_load(values['config']['config.yaml.local'])
                        ['db_config']['db_path'])
        self.assertEqual(selected, target)
        self.assertNotEqual(source, target)
        mount = next(v for v in migration['volumeMounts'] if v['name'] == 'crowdsec-db')
        self.assertTrue(source.is_relative_to(mount['mountPath']))
        self.assertTrue(target.is_relative_to(mount['mountPath']))
        self.assertEqual(f"{values['image']['repository']}:{values['image']['tag']}",
                         migration['image'])


if __name__ == '__main__':
    unittest.main()
