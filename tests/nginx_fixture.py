"""Validate explicitly selected local Nginx binaries before fixture allocation."""

import os
from pathlib import Path


def fixture_binary(selected):
    """Require an absolute executable file; never resolve an opt-in binary through PATH."""
    try:
        candidate = Path(selected) if selected else Path()
        if not candidate.is_absolute():
            raise ValueError
        binary = candidate.resolve(strict=True)
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError
    except (OSError, ValueError):
        raise RuntimeError("Select an absolute executable Nginx binary path") from None
    return str(binary)
