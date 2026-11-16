"""Recover mirrored KV fields without writing or logging plaintext credentials."""

import base64
import json
import re
from collections import defaultdict


class RecoveryError(ValueError):
    """A recovery ambiguity; messages must never contain credential values."""


def reverse_template(template, rendered):
    """Invert only literal Go templates containing simple field substitutions."""
    matches = list(re.finditer(r"{{\s*\.([A-Za-z_][A-Za-z_0-9]*)\s*}}", template))
    if not matches or re.search(r"{{", re.sub(r"{{\s*\.[A-Za-z_][A-Za-z_0-9]*\s*}}", "", template)):
        raise RecoveryError("Template is not a reversible literal substitution")
    pieces, names, offset = [], set(), 0
    for match in matches:
        pieces.append(re.escape(template[offset:match.start()]))
        name = match.group(1)
        pieces.append(f"(?P={name})" if name in names else f"(?P<{name}>.*?)")
        names.add(name)
        offset = match.end()
    pieces.append(re.escape(template[offset:]))
    result = re.fullmatch("".join(pieces), rendered, flags=re.DOTALL)
    if result is None:
        raise RecoveryError("Rendered Secret does not match the literal template")
    return result.groupdict()


def recover_kv(snapshot):
    """Return KV values in memory, plus a value-free recovery report."""
    secrets = {
        (d["metadata"]["namespace"], d["metadata"]["name"]): d
        for d in snapshot["items"] if d["kind"] == "Secret"
    }
    values, sources = defaultdict(dict), defaultdict(list)
    canonicalized, covered = [], []
    for external in snapshot["items"]:
        if external["kind"] != "ExternalSecret":
            continue
        meta, spec = external["metadata"], external["spec"]
        identity = meta["namespace"] + "/" + meta["name"]
        target = spec.get("target", {})
        secret = secrets.get((meta["namespace"], target.get("name", meta["name"])))
        if secret is None:
            raise RecoveryError(f"Missing target Secret for {identity}")
        if spec.get("dataFrom"):
            raise RecoveryError(f"Unreviewed dataFrom mapping for {identity}")
        decoded = {
            key: base64.b64decode(value, validate=True).decode("utf-8")
            for key, value in secret.get("data", {}).items()
        }
        inputs = dict(decoded)
        for key, template in target.get("template", {}).get("data", {}).items():
            if key not in decoded:
                raise RecoveryError(f"Missing rendered template field for {identity}")
            if "{{" not in template:
                if template != decoded[key]:
                    raise RecoveryError(f"Static template differs for {identity}")
                continue
            if "{{- $store := .source | fromYaml -}}" in template:
                if not identity.startswith("monitoring/thanos-") or key != "objstore.yml":
                    raise RecoveryError(f"Unreviewed canonical configuration for {identity}")
                # Original public endpoint was overwritten by this template. The
                # working, already-rendered internal S3 configuration is recoverable.
                inputs["source"] = decoded[key]
                canonicalized.append(identity)
            else:
                try:
                    recovered = reverse_template(template, decoded[key])
                except RecoveryError as error:
                    raise RecoveryError(f"Template recovery failed for {identity}: {error}") from None
                for name, value in recovered.items():
                    if name in inputs and inputs[name] != value:
                        raise RecoveryError(f"Template/direct field conflict for {identity}")
                    inputs[name] = value
        for mapping in spec.get("data", []):
            remote = mapping["remoteRef"]
            if remote.get("decodingStrategy", "None") != "None":
                raise RecoveryError(f"Unreviewed decoding strategy for {identity}")
            path, field = remote["key"], remote.get("property")
            if not field or remote.get("metadataPolicy", "None") != "None":
                raise RecoveryError(f"Unreviewed remote property for {identity}")
            source = mapping["secretKey"]
            if source not in inputs:
                raise RecoveryError(f"Missing recoverable input for {identity}")
            if field in values[path] and values[path][field] != inputs[source]:
                raise RecoveryError(f"Conflicting mirrored values for KV {path} field {field}")
            values[path][field] = inputs[source]
            sources[path].append(identity)
        covered.append(identity)
    report = {
        "external_secrets_covered": len(covered),
        "kv_paths": {path: sorted(fields) for path, fields in sorted(values.items())},
        "kv_field_count": sum(len(fields) for fields in values.values()),
        "canonicalized_thanos_sources": canonicalized,
        "sources": {path: sorted(set(items)) for path, items in sorted(sources.items())},
    }
    return dict(values), report


def configuration_inventory(snapshot):
    """Derive least-privilege ESO policies and namespace/SA-bound roles."""
    stores, roles = {}, {}
    for item in snapshot["items"]:
        if item["kind"] not in ("SecretStore", "ClusterSecretStore"):
            continue
        meta, provider = item["metadata"], item["spec"]["provider"]["vault"]
        if provider.get("path") != "kv" or provider.get("version") != "v2":
            raise RecoveryError("Only the reviewed KV v2 mount is supported")
        auth = provider["auth"]["kubernetes"]
        account = auth["serviceAccountRef"]
        namespace = account.get("namespace", meta.get("namespace"))
        if not namespace or auth.get("mountPath", "kubernetes") != "kubernetes":
            raise RecoveryError("Unreviewed Kubernetes auth binding")
        if account.get("audiences") != ["vault"]:
            raise RecoveryError("Unreviewed Kubernetes auth audience")
        role_name = auth["role"]
        stores[(item["kind"], meta.get("namespace"), meta["name"])] = role_name
        role = roles.setdefault(role_name, {"service_accounts": set(), "namespaces": set(), "paths": set()})
        role["service_accounts"].add(account["name"])
        role["namespaces"].add(namespace)
    for item in snapshot["items"]:
        if item["kind"] != "ExternalSecret":
            continue
        meta, spec = item["metadata"], item["spec"]
        ref = spec["secretStoreRef"]
        kind = ref.get("kind", "SecretStore")
        namespace = meta["namespace"] if kind == "SecretStore" else None
        role = roles[stores[(kind, namespace, ref["name"])]]
        role["paths"].update(entry["remoteRef"]["key"] for entry in spec.get("data", []))
    # Each grouped role must not introduce cross-product SA/namespace grants.
    for role in roles.values():
        if len(role["service_accounts"]) > 1 and len(role["namespaces"]) > 1:
            raise RecoveryError("Role grouping would broaden namespace/service-account bindings")
    return {name: {key: sorted(value) for key, value in role.items()} for name, role in sorted(roles.items())}


def assert_secret_free_text(text, values):
    """Reject accidental long credential inclusion in plans/state or generated code."""
    for fields in values.values():
        for value in fields.values():
            if len(value) >= 12 and (value in text or json.dumps(value)[1:-1] in text):
                raise RecoveryError("Credential detected in a supposedly non-secret artifact")


def supplemental_secrets(snapshot):
    """Preserve unmapped application Opaque Secrets under explicit recovery paths.

    These are retained originals, not inferred mappings to historic KV paths.
    TLS, Helm releases, cluster bootstrap and obsolete Bao tokens stay only in
    the encrypted source archive, never copied into application configuration.
    """
    allowed = {'argocd', 'harbor', 'kyverno', 'lenka', 'longhorn-system',
               'mastodon', 'monitoring', 'nextcloud', 'seaweedfs'}
    mirrored = {
        (x['metadata']['namespace'], x['spec'].get('target', {}).get('name', x['metadata']['name']))
        for x in snapshot['items'] if x['kind'] == 'ExternalSecret'
    }
    values = {}
    for item in snapshot['items']:
        meta = item['metadata']
        identity = (meta.get('namespace'), meta['name'])
        if (item['kind'] != 'Secret' or item.get('type') != 'Opaque'
                or identity[0] not in allowed or identity in mirrored
                or not item.get('data')):
            continue
        values['recovery/kubernetes/' + '/'.join(identity)] = {
            # Preserve exact bytes, including binary values, without guessing.
            'encoding': 'base64', 'data': dict(item['data']),
            'source_date': '2026-11-16',
        }
    return values
