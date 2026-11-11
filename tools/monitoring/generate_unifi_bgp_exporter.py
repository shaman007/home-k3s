#!/usr/bin/env python3
"""Generate the UniFi BGP collector ConfigMap from its reviewed Python source."""

from pathlib import Path
import sys
import yaml

root = Path(__file__).resolve().parents[2]
path = root / "unifi/poller/config-map-unifi-bgp-exporter.yaml"
doc = {
    "apiVersion": "v1",
    "kind": "ConfigMap",
    "metadata": {"name": "unifi-bgp-exporter", "namespace": "unifi"},
    "data": {"exporter.py": (root / "tools/monitoring/unifi_bgp_exporter.py").read_text()},
}
text = yaml.safe_dump(doc, sort_keys=False, width=120)
if "--check" in sys.argv:
    if path.read_text() != text:
        raise SystemExit("UniFi BGP exporter ConfigMap is stale")
else:
    path.write_text(text)
