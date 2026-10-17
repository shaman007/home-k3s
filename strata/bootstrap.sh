#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
umask 077
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git unzip libgomp1 libatomic1 python3 python3-venv build-essential
source_dir="/data/source-${STRATA_REVISION}"
if [ ! -f "${source_dir}/setup.py" ]; then
  mkdir -p "${source_dir}"
  curl --retry 5 -fsSL "https://github.com/Niko1221/Strata/archive/${STRATA_REVISION}.tar.gz" -o /data/source.tar.gz
  tar -xzf /data/source.tar.gz --strip-components=1 -C "${source_dir}"
fi
cd "${source_dir}"
if [ ! -x .venv/bin/python ]; then
  # A persisted venv may point to Python from an earlier container image.
  if [ -d .venv/bin ]; then
    for interpreter in python python3 python3.12; do
      ln -sfn "$(command -v python3)" ".venv/bin/${interpreter}"
    done
  fi
  python3 -m venv .venv
fi
if [ ! -f strata-iq2_xs.json ]; then
  .venv/bin/python setup.py --yes --family qwen --model IQ2_XS \
    --backend cuda --gpu 0 --context 32768 --vision no \
    --low-ram mmap --vram-reserve-mib 3072 \
    --data-dir /data/model --host 127.0.0.1 --no-start
fi
# The key is supplied by Kubernetes, never passed on a command line or printed.
# Only a private, ephemeral runtime config contains it; model config stays keyless.
mkdir -p /run/strata
.venv/bin/python - <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path('strata-iq2_xs.json').read_text())
# Apply the current reserve even when setup reuses its persisted model config.
args = cfg['args']
args[args.index('--vram-reserve-mib') + 1] = '3072'
cfg['host'] = '0.0.0.0'
cfg['api_key'] = Path('/run/strata-secret/key').read_text().strip()
cfg['open_browser'] = False
Path('/run/strata/config.json').write_text(json.dumps(cfg))
PY
exec .venv/bin/python serve/server.py --engine strata --config /run/strata/config.json --port 8080
