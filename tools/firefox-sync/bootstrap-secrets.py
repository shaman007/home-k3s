#!/usr/bin/env python3
"""Initialize dedicated OpenBao secrets and ESO access; never emit secret values."""

import argparse
import json
from pathlib import Path
import secrets
import urllib.error
import urllib.request

from http_transport import Transport

ADDRESS = "https://openbao.int.andreybondarenko.com"
TOKEN_FILE = Path("/home/shaman007/.codex/skills/vault-operator/root-token.txt")
KEYS = (
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_PASSWORD",
    "SYNC_MASTER_SECRET",
    "SYNC_TOKENSERVER__FXA_METRICS_HASH_SECRET",
)


def main():
    """Initialize dedicated OpenBao secrets and ESO access; never emit secret values."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="write OpenBao after explicit approval"
    )
    args = parser.parse_args()
    if not args.execute:
        print(
            (
                "Plan: create missing kv/firefox-sync "
                "keys, scoped policy, and Kubernetes auth "
                "role. No writes performed."
            )
        )
        return
    transport = Transport(ADDRESS, {"openbao.int.andreybondarenko.com"})
    candidates = [
        line.strip()
        for line in TOKEN_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(("hvs.", "s."))
    ]
    if len(candidates) != 1:
        raise RuntimeError("Expected exactly one Vault token in token file")
    token = candidates[0]

    def api(method, path, data=None, missing_ok=False):
        request = urllib.request.Request(
            ADDRESS + "/v1/" + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={"X-Vault-Token": token, "Content-Type": "application/json"},
            method=method,
        )
        try:
            with transport.open(request) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as error:
            error.close()
            if missing_ok and error.code == 404:
                return None
            raise RuntimeError(
                f"OpenBao {method} {path} failed: HTTP {error.code}"
            ) from None
        except Exception:
            raise RuntimeError(
                f"OpenBao {method} {path} failed; details suppressed to protect credentials"
            ) from None

    current = api("GET", "kv/data/firefox-sync", missing_ok=True)
    if current is None:
        api(
            "POST",
            "kv/data/firefox-sync",
            {
                "options": {"cas": 0},
                "data": {key: secrets.token_hex(32) for key in KEYS},
            },
        )
        print("Created dedicated Sync secrets in OpenBao.")
    elif not set(KEYS).issubset(current["data"]["data"]):
        raise RuntimeError(
            "Existing secret is incomplete; refusing to overwrite or rotate credentials."
        )
    else:
        print("Preserved existing Sync secrets.")
    api(
        "PUT",
        "sys/policies/acl/firefox-sync",
        {
            "policy": 'path "kv/data/firefox-sync" { capabilities = ["read"] }\n'
            'path "kv/metadata/firefox-sync" { capabilities = ["read"] }\n'
        },
    )
    api(
        "POST",
        "auth/kubernetes/role/external-secrets-firefox-sync",
        {
            "bound_service_account_names": ["vault-auth"],
            "bound_service_account_namespaces": ["firefox-sync"],
            "audience": "vault",
            "token_policies": ["firefox-sync"],
            "token_ttl": "1h",
        },
    )
    print(
        "Configured namespace-scoped External Secrets access. No secret values printed."
    )


if __name__ == "__main__":
    main()
