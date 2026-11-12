"""Run isolated probe commands without implicit shells or environment PATH lookup."""

import math
import os
import shutil

# Audited boundary: bounded argv execution, never an implicit shell.
import subprocess  # nosec B404

SYSTEM_PATH = "/usr/bin:/bin"
CommandTimeout = subprocess.TimeoutExpired


def run_command(arguments, *, timeout=90, **options):
    """Resolve system executables explicitly and preserve subprocess result/error semantics."""
    if not isinstance(arguments, (list, tuple)) or not arguments:
        raise TypeError("Probe commands require a nonempty argument sequence")
    if not all(isinstance(value, (str, os.PathLike)) for value in arguments):
        raise TypeError("Probe command arguments must be text or filesystem paths")
    arguments = [os.fspath(value) for value in arguments]
    if not all(isinstance(value, str) for value in arguments):
        raise TypeError("Probe command arguments must resolve to text")
    if options.keys() - {"check", "capture_output", "text", "input"}:
        raise TypeError("Unsupported probe subprocess option")
    if (
        not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("Probe subprocess timeout must be finite and positive")
    program = arguments[0]
    if os.path.dirname(program) and not os.path.isabs(program):
        raise ValueError(
            "Probe executables must be system names or explicit absolute paths"
        )
    executable = (
        program if os.path.isabs(program) else shutil.which(program, path=SYSTEM_PATH)
    )
    if not executable or not os.path.isabs(executable):
        raise FileNotFoundError("Probe executable unavailable in trusted system paths")
    check = options.pop("check", False)
    # Executable is absolute, argv/options validated and the shell is always disabled.
    return subprocess.run(  # nosec B603
        [executable, *arguments[1:]],
        shell=False,
        timeout=timeout,
        check=check,
        **options,
    )


def user_executable(name):
    """Find explicitly trusted user/system CLI installs, ignoring environment PATH."""
    if not isinstance(name, str) or not name or os.path.basename(name) != name:
        raise ValueError("Expected an executable basename")
    paths = [
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/bin"),
        "/usr/bin",
        "/bin",
    ]
    executable = shutil.which(name, path=os.pathsep.join(paths))
    if not executable or not os.path.isabs(executable):
        raise FileNotFoundError("CLI unavailable in trusted install directories")
    return executable


def checked_stdout(result, *, strip=False):
    """Preserve isolated probe failures and optionally strip successful output."""
    if result.returncode != 0:
        raise AssertionError(result.stdout[-2000:] + result.stderr[-2000:])
    return result.stdout.strip() if strip else result.stdout


def fixture_chown_prefix():
    """Build the shared offline, disposable-volume ownership initializer policy."""
    return [
        "podman",
        "run",
        "--rm",
        "--network=none",
        "--cap-drop=ALL",
        "--cap-add=CHOWN",
    ]


def require_restricted_status(status):
    """Require the fixture process to have no capabilities and active privilege guards."""
    for expected in (
        "CapEff:\t0000000000000000",
        "CapBnd:\t0000000000000000",
        "NoNewPrivs:\t1",
        "Seccomp:\t2",
    ):
        if expected not in status:
            raise AssertionError(status)


def cleanup_fixture_volume(runner, container, volume):
    """Remove a disposable container before its volume, preserving cleanup failures."""
    if container:
        runner(["podman", "rm", "-f", container])
    runner(["podman", "volume", "rm", volume])
