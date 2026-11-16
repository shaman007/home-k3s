"""Read validated CI release pins without evaluating file contents as shell code."""

import argparse
import json
from pathlib import Path
import re

PINS = Path(__file__).with_name("tool-versions.json")
REPOSITORIES = {
    "kyverno": "kyverno/kyverno",
    "ripgrep": "BurntSushi/ripgrep",
    "kubeconform": "yannh/kubeconform",
}


def load_pin(name, path=PINS):
    """Require a known repository, release version and immutable SHA256 archive pin."""
    pin = json.loads(path.read_text(encoding="utf-8"))[name]
    if pin["depName"] != REPOSITORIES[name]:
        raise ValueError("Unexpected CI tool repository")
    if not re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", pin["version"]):
        raise ValueError("Invalid CI tool version")
    if not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]):
        raise ValueError("Invalid CI tool SHA256")
    return pin


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=sorted(REPOSITORIES))
    args = parser.parse_args()
    selected = load_pin(args.tool)
    print(selected["version"], selected["sha256"])
