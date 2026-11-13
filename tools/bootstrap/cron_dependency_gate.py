#!/usr/bin/env python3
"""Bounded per-Job HTTP readiness gate; exec work only after all providers are ready."""

import argparse
import json
import math
import os
import re
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Readiness must not silently follow a login or public ingress redirect."""

    # urllib's extension API fixes this signature.
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate(config):
    """Allow credential-free internal HTTP endpoints and bounded timing only."""
    if set(config) != {
        "mode",
        "budget_seconds",
        "interval_seconds",
        "probe_seconds",
        "checks",
    }:
        raise ValueError("Invalid dependency configuration fields")
    if config["mode"] not in ("skip", "fail"):
        raise ValueError("Invalid timeout policy")
    for key, maximum in (
        ("budget_seconds", 300),
        ("interval_seconds", 30),
        ("probe_seconds", 5),
    ):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Invalid timing")
        if not math.isfinite(value) or not 0 < value <= maximum:
            raise ValueError("Invalid timing")
    if not isinstance(config["checks"], list) or not 1 <= len(config["checks"]) <= 8:
        raise ValueError("Expected one to eight readiness checks")
    names = set()
    for check in config["checks"]:
        if set(check) != {"name", "url"} or not re.fullmatch(
            r"[a-z][a-z0-9-]{0,62}", check["name"]
        ):
            raise ValueError("Invalid readiness check")
        if check["name"] in names:
            raise ValueError("Duplicate readiness check")
        names.add(check["name"])
        url = urllib.parse.urlsplit(check["url"])
        if any(
            (
                url.scheme not in ("http", "https"),
                url.username,
                url.password,
                url.query,
                url.fragment,
            )
        ):
            raise ValueError("Only credential-free HTTP(S) URLs are allowed")
        if not re.fullmatch(
            r"[a-z0-9-]+\.[a-z0-9-]+\.svc\.cluster\.local", url.hostname or ""
        ):
            raise ValueError("Only credential-free cluster Service URLs are allowed")
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError("Invalid readiness port")
    return config


def http_ready(url, timeout):
    """Require HTTP 200, verified HTTPS, no environment proxy and no redirects."""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        return False
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(url, timeout=timeout) as response:  # nosec B310
            return response.status == 200
    except urllib.error.HTTPError as error:
        error.close()
        return False
    except (OSError, ValueError, urllib.error.URLError):
        return False


def probe(check, timeout):
    """A child deadline also bounds DNS resolution, unlike socket timeout alone."""
    try:
        # Fixed interpreter/script, validated URL, no shell; timeout includes DNS.
        result = subprocess.run(  # nosec B603
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--probe",
                check["url"],
                str(timeout),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def wait(
    config, *, check_ready=probe, clock=time.monotonic, sleep=time.sleep, emit=print
):
    """Return ready/skip/fail; no work command runs here and no URL is logged."""
    validate(config)
    started = clock()
    deadline = started + config["budget_seconds"]
    while True:
        all_ready = True
        for check in config["checks"]:
            remaining = deadline - clock()
            if remaining <= 0:
                all_ready = False
                break
            if not check_ready(check, min(config["probe_seconds"], remaining)):
                all_ready = False
        if all_ready and clock() <= deadline:
            result = "ready"
            break
        remaining = deadline - clock()
        if remaining <= 0:
            result = "skipped" if config["mode"] == "skip" else "unavailable"
            break
        sleep(min(config["interval_seconds"], remaining))
    emit(
        json.dumps(
            {
                "event": "cron_dependencies",
                "result": result,
                "duration_seconds": round(clock() - started, 3),
            }
        )
    )
    return result


def main():
    """Replace this process with the original command; preserve its exit status."""
    if len(sys.argv) == 4 and sys.argv[1] == "--probe":
        return 0 if http_ready(sys.argv[2], float(sys.argv[3])) else 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Original work command is required")
    try:
        result = wait(
            json.loads(Path(args.config).read_text(encoding="utf-8")),
            emit=lambda line: print(line, flush=True),
        )
    except (OSError, ValueError, TypeError, KeyError):
        print('{"event":"cron_dependencies","result":"invalid-config"}', flush=True)
        return 2
    if result == "skipped":
        return 0
    if result != "ready":
        return 75
    try:
        # Preserve the original reviewed manifest argv; never invoke a shell.
        os.execvp(command[0], command)  # nosec B606
    except OSError:
        print('{"event":"cron_dependencies","result":"exec-failed"}', flush=True)
    return 127


if __name__ == "__main__":
    sys.exit(main())
