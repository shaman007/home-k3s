#!/usr/bin/env python3
"""Keep queue collector ConfigMaps identical to the reviewed source files."""
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
for namespace, name, source in [
    ('mail', 'postfix-queue-exporter', 'postfix-queue-exporter.pl'),
    ('mastodon', 'mastodon-queue-metrics', 'mastodon-queues.lua'),
    ('immich', 'immich-queue-metrics', 'immich-queues.lua'),
]:
    path = ROOT / namespace / f'config-map-{name}.yaml'
    doc = {'apiVersion': 'v1', 'kind': 'ConfigMap',
           'metadata': {'name': name, 'namespace': namespace},
           'data': {source: (ROOT / 'tools/monitoring' / source).read_text()}}
    text = yaml.safe_dump(doc, sort_keys=False, width=120)
    if '--check' in sys.argv:
        if not path.exists() or path.read_text() != text:
            raise SystemExit(f'{path} is stale')
    else:
        path.write_text(text)
