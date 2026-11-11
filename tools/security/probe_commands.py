"""Run isolated probe commands without implicit shells or environment PATH lookup."""

import math
import os
import shutil
import subprocess

SYSTEM_PATH = "/usr/bin:/bin"


def run_command(arguments, *, timeout=90, **options):
    """Resolve system executables explicitly and preserve subprocess result/error semantics."""
    if not isinstance(arguments, (list, tuple)) or not arguments:
        raise TypeError("Probe commands require a nonempty argument sequence")
    if not all(isinstance(value, (str, os.PathLike)) for value in arguments):
        raise TypeError("Probe command arguments must be text or filesystem paths")
    arguments = [os.fspath(value) for value in arguments]
    if not all(isinstance(value, str) for value in arguments):
        raise TypeError("Probe command arguments must resolve to text")
    if options.keys() - {"check", "capture_output", "text"}:
        raise TypeError("Unsupported probe subprocess option")
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Probe subprocess timeout must be finite and positive")
    program = arguments[0]
    if os.path.dirname(program) and not os.path.isabs(program):
        raise ValueError("Probe executables must be system names or explicit absolute paths")
    executable = program if os.path.isabs(program) else shutil.which(program, path=SYSTEM_PATH)
    if not executable or not os.path.isabs(executable):
        raise FileNotFoundError("Probe executable unavailable in trusted system paths")
    check = options.pop("check", False)
    return subprocess.run(
        [executable, *arguments[1:]], shell=False, timeout=timeout, check=check, **options
    )
