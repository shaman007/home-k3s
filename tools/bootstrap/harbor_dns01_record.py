#!/usr/bin/env python3
"""Check/create only the Harbor ACME CNAME; never replace an existing DNS record."""

import argparse
import base64
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.security.probe_commands import run_command, user_executable  # pylint: disable=wrong-import-position

RECORD = (
    Path(__file__).resolve().parents[2] / "docs/migrations/harbor-dns01/dns-record.json"
)


def matches(records, desired):
    """Only the exact expected challenge CNAME is idempotent."""
    return (
        len(records) == 1
        and records[0].get("type") == "CNAME"
        and records[0].get("name") == desired["name"]
        and records[0].get("data", "").rstrip(".") == desired["data"]
    )


def main():
    """Default is read-only; creation never overwrites TXT/CNAME or routing records."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    desired = json.loads(RECORD.read_text())
    if desired != {
        "zone": "andreybondarenko.com",
        "type": "CNAME",
        "name": "_acme-challenge.harbor",
        "data": "_acme-challenge.harbor.int.andreybondarenko.com",
        "ttl": 600,
    }:
        raise ValueError("Unexpected DNS delegation specification")
    result = run_command(
        [
            user_executable("kubectl"),
            "get",
            "secret",
            "godaddy-dns-token",
            "-n",
            "cert-manager",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode:
        raise RuntimeError("Cannot read the existing DNS solver credential")
    token = (
        base64.b64decode(json.loads(result.stdout)["data"]["token"]).decode().strip()
    )
    if not token:
        raise RuntimeError("Empty DNS credential")
    session = requests.Session()
    session.trust_env = False
    session.headers["Authorization"] = "Bearer " + token
    url = "https://api.godaddy.com/v3/domains/zones/andreybondarenko.com/dns-records"

    def call(method, **kwargs):
        response = session.request(
            method, url, timeout=30, allow_redirects=False, **kwargs
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(
                "GoDaddy request failed with HTTP " + str(response.status_code)
            )
        return response.json() if response.content else None

    def current():
        values = []
        for page in range(1, 101):
            data = call(
                "GET", params={"name": desired["name"], "page": page, "pageSize": 100}
            )
            values.extend(r for r in data["items"] if r["name"] == desired["name"])
            if len(data["items"]) < 100:
                return values
        raise RuntimeError("DNS pagination exceeded bounded inventory")

    existing = current()
    if matches(existing, desired):
        print(
            json.dumps(
                {"result": "already-present", "recordId": existing[0].get("recordId")}
            )
        )
        return 0
    if existing:
        raise RuntimeError(
            "Challenge name already has conflicting records; nothing changed"
        )
    if not args.create:
        print(json.dumps({"result": "missing", "desired": desired}))
        return 1
    call("POST", json={k: v for k, v in desired.items() if k != "zone"})
    existing = current()
    if not matches(existing, desired):
        raise RuntimeError(
            "CNAME creation requires manual inspection; no other writes attempted"
        )
    print(
        json.dumps(
            {
                "result": "created",
                "recordId": existing[0].get("recordId"),
                "record": desired,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, requests.RequestException, ValueError, KeyError):
        # Do not print provider response bodies, credentials or Secret manifests.
        print(
            "DNS delegation check/create failed; no record replacement attempted",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
