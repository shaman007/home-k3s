#!/usr/bin/env python3
"""Read-only SSO inventory; export only URL settings, never tokens or client secrets."""

import argparse
import json
from pathlib import Path
import runpy
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SSO = "https://sso.andreybondarenko.com"
BAO = "https://openbao.int.andreybondarenko.com"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(
        (ROOT / "docs/migrations/letsencrypt-internal/inventory.json").read_text()
    )
    replacements = {
        old: new
        for c in inventory["certificates"]
        if not c["canary"]
        for old, new in zip(c["old_names"], c["new_names"])
    }

    def mapped(value):
        for old, new in replacements.items():
            value = re.sub(r"://" + re.escape(old) + r"(?=[:/?#]|$)", "://" + new, value)
        return value

    helper = runpy.run_path(str(ROOT / "tools/provision-traefik-security.py"))
    token = helper["keycloak_token"]()

    def get(url, headers):
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=25
        ) as response:
            return json.load(response)

    headers = {"Authorization": "Bearer " + token}
    clients = []
    for realm in get(SSO + "/admin/realms", headers):
        name = realm["realm"]
        # Request pages explicitly so larger realms are not silently truncated.
        offset = 0
        while True:
            batch = get(
                SSO + "/admin/realms/" + name + "/clients?first=" + str(offset) + "&max=100",
                headers,
            )
            for client in batch:
                settings = {
                    k: client[k]
                    for k in ["rootUrl", "baseUrl", "adminUrl", "redirectUris", "webOrigins"]
                    if k in client
                }
                logout = client.get("attributes", {}).get("post.logout.redirect.uris")
                if logout is not None:
                    settings["post.logout.redirect.uris"] = logout
                encoded = json.dumps(settings)
                if ".k8s.my.lan" not in encoded:
                    continue
                proposed = {
                    k: [mapped(x) for x in value] if isinstance(value, list) else mapped(value)
                    for k, value in settings.items()
                }
                clients.append(
                    {
                        "realm": name,
                        "clientId": client["clientId"],
                        "enabled": client.get("enabled"),
                        "current": settings,
                        "proposed_public_names": proposed,
                        "retired_vault_alias_review": "vault.w386.k8s.my.lan" in encoded,
                    }
                )
            if len(batch) < 100:
                break
            offset += 100
    root = (Path.home() / ".codex/skills/vault-operator/root-token.txt").read_text().splitlines()[0]
    bh = {"X-Vault-Token": root}
    config = get(BAO + "/v1/auth/oidc/config", bh)["data"]
    names = get(BAO + "/v1/auth/oidc/role?list=true", bh)["data"]["keys"]
    roles = []
    for name in names:
        role = get(BAO + "/v1/auth/oidc/role/" + name, bh)["data"]
        redirects = role.get("allowed_redirect_uris", [])
        roles.append(
            {
                "role": name,
                "current_allowed_redirect_uris": redirects,
                "proposed_allowed_redirect_uris": [mapped(x) for x in redirects],
            }
        )
    result = {
        "keycloak_clients": clients,
        "openbao_oidc": {
            "client_id": config.get("oidc_client_id"),
            "default_role": config.get("default_role"),
            "roles": roles,
        },
        "cutover_rule": "Add exact new redirects/origins while retaining old callbacks; switch base/root/admin URLs only after new DNS, certificates and routes work; remove legacy callbacks after login/logout verification.",
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Inventoried",
        len(clients),
        "Keycloak clients and",
        len(roles),
        "OpenBao OIDC roles; secret values excluded",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("SSO inventory failed; credential and response details suppressed")
