#!/usr/bin/env sh
set -eu

: "${VAULT_ADDR:?Set VAULT_ADDR to the production Vault API URL}"
: "${VAULT_TOKEN:?Set VAULT_TOKEN to a Vault administrator token}"
: "${SNAPSHOT_DIR:?Set SNAPSHOT_DIR to an encrypted, non-repository directory}"

umask 077
mkdir -p "$SNAPSHOT_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
snapshot="$SNAPSHOT_DIR/vault-raft-$timestamp.snap"
inventory="$SNAPSHOT_DIR/vault-raft-$timestamp.inventory.json"

if [ -n "${SNAPSHOT_POD:-}" ]; then
  pod_snapshot="/tmp/vault-raft-$timestamp.snap"
  printf '%s\n' "$VAULT_TOKEN" | kubectl exec -i -n vault "$SNAPSHOT_POD" -- \
    sh -ec '
      IFS= read -r VAULT_TOKEN
      export VAULT_TOKEN
      export VAULT_ADDR=https://vault-active.vault.svc:8200
      export VAULT_CACERT=/vault/userconfig/vault-server-tls/ca.crt
      vault operator raft snapshot save "$1"
    ' sh "$pod_snapshot"
  kubectl cp "vault/$SNAPSHOT_POD:$pod_snapshot" "$snapshot"
  kubectl exec -n vault "$SNAPSHOT_POD" -- rm -f "$pod_snapshot"
else
  vault operator raft snapshot save "$snapshot"
fi
sha256sum "$snapshot" > "$snapshot.sha256"

mounts="$(vault secrets list -format=json)"
auth="$(vault auth list -format=json)"
policies="$(vault policy list -format=json)"
peers="$(vault operator raft list-peers -format=json)"

jq -n \
  --arg timestamp "$timestamp" \
  --argjson mounts "$mounts" \
  --argjson auth "$auth" \
  --argjson policies "$policies" \
  --argjson peers "$peers" \
  '{
    capturedAt: $timestamp,
    mounts: ($mounts | with_entries(.value |= {type, accessor, options})),
    auth: ($auth | with_entries(.value |= {type, accessor})),
    policies: $policies,
    raft: {
      servers: [
        $peers.data.config.servers[]
        | {node_id, address, leader, voter}
      ]
    }
  }' > "$inventory"

printf 'Snapshot: %s\nChecksum: %s\nInventory: %s\n' \
  "$snapshot" "$snapshot.sha256" "$inventory"
