# OpenBao migration

Vault 2.0.3 remains the production endpoint while OpenBao is deployed in
parallel. Do not point clients at OpenBao until the snapshot rehearsal in this
document succeeds.

## Compatibility gate

The upstream in-place migration guide does not support Vault 1.15 or newer.
This cluster therefore uses a forced Raft snapshot restore into an isolated
OpenBao 2.6.1 cluster rather than replacing the Vault container in place.

Before publishing the parallel deployment:

1. Run `vault/configure-pki-acme.sh` with an administrator token. It creates
   the restricted `openbao-server` PKI role.
2. Apply the updated `vault-pki-renewer` policy and run the renewer once. It
   fills `openbao/openbao-server-tls`; Argo CD ignores that Secret's data.
3. Confirm both Vault PVCs have current Longhorn backups.
4. Take and checksum an encrypted Raft snapshot outside the cluster.

Because Vault redirects snapshot requests to its cluster-only active address,
run the helper with the current leader pod, for example:

```sh
VAULT_ADDR=https://vault.w386.k8s.my.lan \
VAULT_TOKEN=... \
SNAPSHOT_POD=vault-0 \
SNAPSHOT_DIR=/encrypted/path \
openbao/tools/snapshot-rehearsal.sh
```

The Vault Enterprise-only `agent-registry/` engine is currently empty, but
Vault marks it as a protected built-in mount and refuses to disable it. The
candidate snapshot therefore retains the mount. OpenBao must load or safely
ignore it during the rehearsal; otherwise the migration stops and the
production Vault cluster remains authoritative. Do not edit Raft storage or
strip the mount from a snapshot.

## Rehearsal

Initialize only the new OpenBao cluster, restore the candidate snapshot with
`bao operator raft snapshot restore -force`, restart it, and unseal it with
the existing Vault Shamir key. Remove stale `vault-*` peers from the restored
Raft configuration and join both `openbao-0` and `openbao-1`.

OpenBao 2.6.1 does not serve its initialization API while `retry_join` is
configured without a reachable leader. The rehearsal manifest therefore
omits `retry_join` while `openbao-0` is initialized and restored. After the
restored node is unsealed, add back a `retry_join` block targeting the
`openbao-active` Service before allowing `openbao-1` to join. Never target a
pod directly: the active Service routes later replicas to the elected leader.

The rehearsal passes only when:

* KV inventory, policies, Kubernetes roles, PKI issuers and roles, OIDC, and
  the SSH signer match Vault.
* Disposable KV, Kubernetes-auth, PKI, ACME, OIDC, and SSH-signing tests pass.
* Both Raft voters have matching committed/applied indexes and survive a
  restart/unseal cycle.
* No production SecretStore or ClusterIssuer has been changed.

Two voters require both nodes for write quorum. This is an accepted deployment
constraint, not high availability against a node loss.

## Cutover and rollback

Pause External Secrets, cert-manager, the PKI renewer, administrative writes,
and new logins. Take the final snapshot, stop Vault, restore and validate
OpenBao, then introduce the compatibility aliases before resuming controllers.

Until ordinary writes are reopened, rollback is to stop OpenBao, restart and
unseal Vault, and restore the old routes. After OpenBao accepts writes, rollback
must restore an OpenBao snapshot or it will lose post-cutover changes.

Retain the Vault PVCs for at least seven days and until an OpenBao Raft snapshot
restore and Longhorn restore have both been tested.
