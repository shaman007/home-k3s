#!/usr/bin/env python3
"""Check or provision the narrowly scoped Keycloak/OpenBao prerequisites.

Default is read-only apart from obtaining a short-lived Keycloak login token.
--write creates/updates the dedicated client, KV entries, ACLs and auth roles.
Secret values stay in memory and are never included in output or error bodies.
"""

import argparse
import base64
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SSO = "https://sso.andreybondarenko.com"
BAO = "https://openbao.int.andreybondarenko.com"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent administrative credentials from following any HTTP redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject the redirect before constructing a request to its destination."""
        raise urllib.error.HTTPError(req.full_url, code, "Redirect refused", headers, fp)


def open_request(req):
    """Open only the reviewed HTTPS services, with scoped headers and no redirects."""
    try:
        endpoint = urllib.parse.urlsplit(req.full_url)
        port = endpoint.port
    except ValueError:
        raise RuntimeError("Invalid administrative endpoint") from None
    sso_host = urllib.parse.urlsplit(SSO).hostname
    bao_host = urllib.parse.urlsplit(BAO).hostname
    if (
        endpoint.scheme != "https"
        or endpoint.hostname not in {sso_host, bao_host}
        or port not in (None, 443)
    ):
        raise RuntimeError("Administrative requests require a reviewed HTTPS origin")
    if endpoint.username is not None or endpoint.password is not None or endpoint.fragment:
        raise RuntimeError("Administrative requests require a reviewed HTTPS origin")
    for name, _ in req.header_items():
        name = name.lower()
        if (name == "authorization" and endpoint.hostname != sso_host) or (
            name == "x-vault-token" and endpoint.hostname != bao_host
        ):
            raise RuntimeError("Administrative credential header does not match its service")
    return urllib.request.build_opener(NoRedirect()).open(req, timeout=20)


def request(url, method="GET", data=None, headers=None, missing=False):
    """Send administrative JSON while suppressing sensitive HTTP error details."""
    encoded = None if data is None else json.dumps(data).encode()
    headers = dict(headers or {})
    if encoded is not None:
        headers["Content-Type"] = "application/json"
    try:
        with open_request(
            urllib.request.Request(url, data=encoded, headers=headers, method=method)
        ) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        exc.close()
        if missing and exc.code == 404:
            return None
        raise RuntimeError(f"{method} {urllib.parse.urlsplit(url).path}: HTTP {exc.code}") from None


def keycloak_token():
    """Obtain a short-lived admin token without printing credential material."""
    raw = subprocess.run(
        [
            "kubectl",
            "get",
            "secret",
            "keycloak-admin",
            "-n",
            "keycloak",
            "-o",
            "json",
            "--request-timeout=15s",
        ],
        check=True,
        capture_output=True,
        shell=False,
        timeout=30,
    ).stdout
    data = json.loads(raw)["data"]
    form = urllib.parse.urlencode(
        {
            "client_id": "admin-cli",
            "grant_type": "password",
            "username": base64.b64decode(data["username"]).decode(),
            "password": base64.b64decode(data["password"]).decode(),
        }
    ).encode()
    req = urllib.request.Request(SSO + "/realms/master/protocol/openid-connect/token", data=form)
    try:
        with open_request(req) as response:
            return json.load(response)["access_token"]
    except urllib.error.HTTPError as exc:
        exc.close()
        raise RuntimeError(f"Keycloak administrator authentication: HTTP {exc.code}") from None


def bao_headers():
    """Read the single local operator credential without exposing its value."""
    token_lines = (
        (Path.home() / ".codex/skills/vault-operator/root-token.txt").read_text().splitlines()
    )
    bao_tokens = [
        line.strip()
        for line in token_lines
        if line.strip().startswith(("s.", "hvs.")) and len(line.split()) == 1
    ]
    if len(bao_tokens) != 1:
        raise RuntimeError(
            "Expected exactly one OpenBao token in the local operator credential file"
        )
    bh = {"X-Vault-Token": bao_tokens[0]}
    return bh


def reconcile_client(admin, kh, desired, write):
    """Check or update only the dedicated client and preserve its existing secret."""
    request(admin + "/roles/admin", headers=kh)
    clients = request(admin + "/clients?clientId=traefik-admin", headers=kh)
    clients = [c for c in clients if c["clientId"] == "traefik-admin"]
    if len(clients) > 1:
        raise RuntimeError("Duplicate traefik-admin clients; refusing to guess")
    if write:
        if clients:
            # Preserve fields unrelated to this client contract and its existing secret.
            merged = request(admin + "/clients/" + clients[0]["id"], headers=kh)
            existing_mappers = {m["name"]: m for m in merged.get("protocolMappers", [])}
            for mapper in desired["protocolMappers"]:
                existing_mappers[mapper["name"]] = {
                    **existing_mappers.get(mapper["name"], {}),
                    **mapper,
                }
            merged.update(desired)
            merged["protocolMappers"] = list(existing_mappers.values())
            request(admin + "/clients/" + clients[0]["id"], method="PUT", data=merged, headers=kh)
        else:
            request(admin + "/clients", method="POST", data=desired, headers=kh)
        clients = request(admin + "/clients?clientId=traefik-admin", headers=kh)
        client = next(c for c in clients if c["clientId"] == "traefik-admin")
        client_secret = request(admin + "/clients/" + client["id"] + "/client-secret", headers=kh)[
            "value"
        ]
    else:
        client_secret = None
    if not clients:
        raise RuntimeError("Keycloak traefik-admin is missing; run --write to provision")
    return clients, client_secret


def verify_client(admin, kh, desired, clients):
    """Verify the client contract and ID-token mapper after reconciliation."""
    actual_client = request(admin + "/clients/" + clients[0]["id"], headers=kh)
    for field in [
        "redirectUris",
        "publicClient",
        "standardFlowEnabled",
        "implicitFlowEnabled",
        "directAccessGrantsEnabled",
        "serviceAccountsEnabled",
    ]:
        actual_value, expected_value = actual_client.get(field), desired[field]
        if field == "redirectUris":
            actual_value, expected_value = set(actual_value), set(expected_value)
        if actual_value != expected_value:
            raise RuntimeError("Keycloak traefik-admin configuration mismatch: " + field)
    mapper = next(
        (
            m
            for m in actual_client.get("protocolMappers", [])
            if m["name"] == "realm-roles-id-token"
        ),
        {},
    )
    if not all(
        mapper.get("config", {}).get(k) == v
        for k, v in desired["protocolMappers"][0]["config"].items()
    ):
        raise RuntimeError("Keycloak ID-token role mapper mismatch")
    print("Keycloak traefik-admin: client contract and role mapper verified")


def read_prerequisite(name, bh):
    """Read existing KV data and its version before verification or CAS updates."""
    current = request(BAO + "/v1/kv/data/" + name, headers=bh, missing=True)
    data = {} if current is None else current["data"]["data"]
    version = 0 if current is None else current["data"]["metadata"]["version"]
    return data, version


def write_prerequisite(name, namespace, sa, bh, client_secret):
    """Write the dedicated KV record with CAS and its narrow policy and role."""
    url = BAO + "/v1/kv/data/" + name
    data, version = read_prerequisite(name, bh)
    if name == "traefik-oidc":
        data["clientSecret"] = client_secret
        data.setdefault("sessionSecret", secrets.token_hex(16))
        if len(data["sessionSecret"]) != 32:
            raise RuntimeError(
                (
                    "Existing OIDC session secret has invalid length; refusing "
                    "to rotate automatically"
                )
            )
    else:
        data.setdefault("csLapiSecret", secrets.token_hex(48))
        data.setdefault("registrationToken", secrets.token_hex(32))
    request(url, method="POST", data={"options": {"cas": version}, "data": data}, headers=bh)
    policy = "\n".join(
        f'path "kv/{prefix}/{name}" {{ capabilities = ["read"] }}'
        for prefix in ["data", "metadata"]
    )
    request(
        BAO + "/v1/sys/policies/acl/" + name,
        method="PUT",
        data={"policy": policy},
        headers=bh,
    )
    request(
        BAO + "/v1/auth/kubernetes/role/external-secrets-" + name,
        method="POST",
        data={
            "bound_service_account_names": [sa],
            "bound_service_account_namespaces": [namespace],
            "audience": "vault",
            "token_policies": [name, "external-secrets-token"],
            "token_ttl": "1h",
            "token_max_ttl": "24h",
        },
        headers=bh,
    )


def verify_prerequisite(name, namespace, sa, bh):
    """Read back required keys, exact policy scope and service-account bindings."""
    url = BAO + "/v1/kv/data/" + name
    for _ in range(5):
        ready = request(url, headers=bh, missing=True)
        policy = request(BAO + "/v1/sys/policies/acl/" + name, headers=bh, missing=True)
        role = request(
            BAO + "/v1/auth/kubernetes/role/external-secrets-" + name, headers=bh, missing=True
        )
        if ready and policy and role:
            break
        time.sleep(0.5)
    if not (ready and policy and role):
        raise RuntimeError("OpenBao prerequisite missing: " + name)
    role_data = role["data"]
    if (
        role_data["bound_service_account_names"] != [sa]
        or role_data["bound_service_account_namespaces"] != [namespace]
        or set(role_data["token_policies"]) != {name, "external-secrets-token"}
        or role_data["audience"] != "vault"
    ):
        raise RuntimeError("OpenBao role binding mismatch: " + name)
    expected_policy = "\n".join(
        f'path "kv/{prefix}/{name}" {{ capabilities = ["read"] }}'
        for prefix in ["data", "metadata"]
    )
    if policy["data"]["policy"].strip() != expected_policy:
        raise RuntimeError("OpenBao policy scope mismatch: " + name)
    required_keys = (
        ["clientSecret", "sessionSecret"]
        if name == "traefik-oidc"
        else ["csLapiSecret", "registrationToken"]
    )
    if not all(ready["data"]["data"].get(k) for k in required_keys):
        raise RuntimeError("OpenBao required secret key missing: " + name)
    print(
        (
            f"OpenBao {name}: secret keys, read-only policy, namespace and "
            f"service-account bindings verified"
        )
    )


def main():
    """Check prerequisites or provision dedicated records when --write is selected."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Provision the dedicated external resources; does not deploy Kubernetes objects",
    )
    args = parser.parse_args()
    token = keycloak_token()
    kh = {"Authorization": "Bearer " + token}
    bh = bao_headers()
    desired = json.loads((ROOT / "keycloak/config/traefik-admin.client.json").read_text())
    admin = SSO + "/admin/realms/master"
    clients, client_secret = reconcile_client(admin, kh, desired, args.write)
    verify_client(admin, kh, desired, clients)
    for name, namespace, sa in [
        ("traefik-oidc", "traefik", "oidc-vault-auth"),
        ("crowdsec", "crowdsec", "vault-auth"),
    ]:
        if args.write:
            write_prerequisite(name, namespace, sa, bh, client_secret)
        else:
            read_prerequisite(name, bh)
        verify_prerequisite(name, namespace, sa, bh)
    if not args.write:
        print("Check only; no external configuration changed.")
    print("Kubernetes deployment and browser login remain separate validation steps.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("Failure type: " + type(exc).__name__, file=sys.stderr)
        # Response bodies, command stderr and exception text may contain credentials.
        print(
            (
                "Prerequisite check/provisioning failed; no secret values "
                "printed. Check connectivity, administrator access and "
                "resource contracts."
            ),
            file=sys.stderr,
        )
        sys.exit(1)
