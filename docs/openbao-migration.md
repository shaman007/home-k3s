# OpenBao migration

The production cutover to OpenBao 2.6.1 completed on 2026-08-14. OpenBao is
authoritative; application SecretStores, cert-manager ACME, Prometheus, OIDC,
and the PKI renewal job all use OpenBao. The Vault StatefulSet is pinned to
zero replicas, while both original Vault PVCs are retained for rollback.

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

## Completed rehearsal

Initialize only the new OpenBao cluster, restore the candidate snapshot with
`bao operator raft snapshot restore -force`, restart it, and unseal it with
the existing Vault Shamir key. Remove stale `vault-*` peers from the restored
Raft configuration and join both `openbao-0` and `openbao-1`.

Raft retry-join uses the `openbao-active` Service. Before initialization that
Service has no active endpoint; after initialization it routes later replicas
to the elected leader. Never target a pod directly. OpenBao service
registration also requires the Cilium `kube-apiserver` entity policy in
addition to the portable Kubernetes API egress policy; without it server
startup blocks before the initialization API becomes available.

The rehearsal passes only when:

* KV inventory, policies, Kubernetes roles, PKI issuers and roles, OIDC, and
  the SSH signer match Vault.
* Disposable KV, Kubernetes-auth, PKI, ACME, OIDC, and SSH-signing tests pass.
* Both Raft voters have matching committed/applied indexes and survive a
  restart/unseal cycle.
* During rehearsal, no production SecretStore or ClusterIssuer was changed.

Two voters require both nodes for write quorum. This is an accepted deployment
constraint, not high availability against a node loss.

## Completed cutover and rollback

External Secrets, cert-manager, and the PKI renewer were paused for the final
snapshot. Vault was then stopped, the final Raft snapshot was restored into
OpenBao, and OpenBao-specific OIDC and PKI cluster URLs were restored. All 28
SecretStores and the `vault-acme` ClusterIssuer were validated Ready before
normal reconciliation resumed. The existing issuer, ServiceAccount, policy,
and SecretStore names intentionally remain for compatibility; their endpoints
now target OpenBao.

Because ordinary writes have reopened, rollback must start from a current
OpenBao snapshot. Restarting the retained Vault PVCs alone would lose all
post-cutover writes. Stop writers first, snapshot OpenBao, then either repair
OpenBao or deliberately restore that snapshot to the rollback target.

Retain the Vault PVCs for at least seven days and until an OpenBao Raft snapshot
restore and Longhorn restore have both been tested.
