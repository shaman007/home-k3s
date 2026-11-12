# Execution checkpoint — 2026-11-12

## Completed live changes

- Created `openbao-root-bootstrap` SelfSigned Issuer, `openbao-internal-root`
  Certificate, `openbao-internal-ca` CA Issuer and staging leaf
  `openbao-internal-tls`. All became Ready.
- Encrypted old backend TLS, root/staging keys and actual new active backend
  key off-cluster. Each backup was decrypted in memory and matched byte-for-byte;
  root certificate/private-key public numbers also matched.
- Added temporary old+new trust to 35 ESO stores, Traefik backend transport and
  Prometheus. Existing public ISRG roots permit certificate-first rollback.
- Changed the existing backend Certificate to internal CA issuance with old and
  Service DNS SANs, retaining its compatibility resource/Secret/mount names.
  Both listeners hot-reloaded the new ECDSA leaf; no OpenBao Pod was restarted.
- Moved all 35 stores and the Prometheus scrape job to internal Service DNS.
  Updated future-start Raft CA/DNS configuration and StatefulSet `BAO_CACERT`;
  StatefulSet remains `OnDelete`, without any Pod deletion or rollout request.

## Observed evidence

Internal root SHA-256: `b3122674538d9086485540b92aac217e7c0848229438f3b4eed938fc4fa8db51`. Root expires 2036-11-09; current active leaf expires 2027-02-10.

- All six listener TLS handshakes verified using ONLY the new root and internal
  DNS SNI. Active leaf SHA-256:
  `7ea25b7bb4da4fa9908693d647710a88a41a4e493af92b721c8dd5422e583e81`.
- All three original Pod UIDs retained, zero container restarts, unsealed.
  Authenticated Raft configuration has three voters, leader `openbao-1`.
- All 35 stores Ready on the internal URL. Forced GoDaddy and Firefox Sync
  ExternalSecret refreshes succeeded at 15:10:31Z and 15:10:35Z respectively.
- Existing public OpenBao ingress health returned HTTP 200 with normal public
  TLS verification, and `sealed=false`.
- Prometheus internal OpenBao target `up=1`; running `promtool check config`
  passed with 186 rules. Prometheus was restarted once to add a public CA mount;
  OpenBao was not restarted.
- Existing backup-freshness procedure passed before the transition. This was
  not an OpenBao Raft data-restore drill, leader-failover or cold-boot test.

## Private recovery directory

`/home/shaman007/.local/state/openbao-internal-tls/2026-11-12/` is owner-only.

- `baseline.json`: original scoped configuration and Argo annotations, no TLS keys.
- `old-backend-tls.json.age`: original backend certificate/private key.
- `internal-pki.json.age`: internal root and staging leaf Secrets.
- `active-backend-tls.json.age`: actual active internal backend Secret.
- Matching `*-verification.json`: ciphertext SHA-256, size and verified decryption.
- `root-ca.pem`, `dual-trust.pem`: public trust only.

Age identity remains at the existing private workstation location. No plaintext
private key was written to this directory or Git. An off-cluster workstation
copy is not an off-site/offline copy; retain an independent copy of encrypted
artifacts and the age identity according to the existing manual DR procedure.

## Rollback, only if required

Keep affected GitOps reconciliation paused during rollback. The original ACME
certificate remains valid until 2027-02-03. From repository root:

```sh
python3 tools/bootstrap/openbao_tls_transition.py rollback \
  --state-dir /home/shaman007/.local/state/openbao-internal-tls/2026-11-12
```

This restores the original backend Certificate spec and decrypts/restores the
old TLS Secret through stdin, never secret-bearing command arguments. Wait for
projection and TLS auto-reload; do not restore old-only clients prematurely.

```sh
python3 tools/bootstrap/openbao_tls_transition.py restore-clients \
  --state-dir /home/shaman007/.local/state/openbao-internal-tls/2026-11-12
```

This refuses to restore clients until all six listener probes present the OLD
certificate fingerprint and healthy/unsealed state. It then restores the
original store trust/URL, ConfigMaps, transport, Pod templates and original Argo
pause annotations (children before parent). No PVC/data deletion, initialization,
Raft restore, forced unseal, Pod deletion or CA deletion is performed. These
rollback stages are prepared, not executed against production. If more changes
occur after this checkpoint, review the scoped snapshot before using it.

## GitOps publication gate

The runtime manifests match the transition and are recorded in the local
OpenBao TLS commit. Publication is still pending. `argocd-applications` and 32 affected child Applications carry a
temporary `argocd.argoproj.io/skip-reconcile=true`. The original settings and exact
application list are retained in private `baseline.json`.

Do not remove those pauses before the matching manifests reach protected main.
Repository policy prohibits this agent from `git push`; runtime manifest commits
also require explicit authorization. After publication, compare the exact Git
revision, restore child annotations and parent annotation to their original
values, then verify application health/revision and TLS functionality again.
Keep the internal CA key out of Git. The public-only trust Secret in Git has no
private key or API credential.

Harbor, split DNS, VIP allocation, MetalLB and UDM were NOT changed. Its later
rollout requires UDM prefix-list/maximum-prefix preparation in unifi-infra and
fresh VIP availability checks, described in README.md.
