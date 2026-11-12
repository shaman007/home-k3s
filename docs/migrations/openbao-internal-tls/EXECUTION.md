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

## GitOps publication and reconciliation

The user published commit `821664a870647a29bd3971a5b9833622821daaac` to main.
The remote SHA was checked without fetching or changing refs. Parent
`argocd-applications` was resumed FIRST with all children still paused. Once it
was Synced at the published SHA and all 32 child source specifications matched
Git, the original child pause annotations were restored. This order prevents
old Helm values from briefly reverting client trust.

The read-only Argo gate then passed: 93/93 Applications Healthy, Synced and
unpaused with expected automation. Temporary orphan warnings disappeared after
resource adoption/cache refresh; no resources or ignore rules were deleted or
added to hide them. OpenBao's six verified TLS listeners retained their original
Pod UIDs, and no server restart was requested.

Original pause annotations and the exact application list remain in private
`baseline.json` for recovery. The private CA key must stay outside Git. The
public-only trust Secret contains no private key or API credential.

## CI and scanning follow-up

[Validation run 43247068658](https://github.com/shaman007/home-k3s/actions/runs/43247068658)
failed because the operational helper imported `cryptography`, which was absent
from the declared CI environment. The helper now uses fixed OpenSSL operations
with in-memory stdin for key matching and standard-library certificate parsing,
without adding a production/test package dependency. A regression test imports
it while deliberately rejecting any cryptography import.

The TLS probe now explicitly enforces TLS 1.2 or newer and preserves CA/hostname
verification, addressing [CodeQL alert 8322](https://github.com/shaman007/home-k3s/security/code-scanning/8322).
Administrative commands resolve only allowlisted executables in trusted paths,
never ambient PATH, and have bounded execution. Runtime gates use explicit
exceptions rather than assertions that disappear under optimized Python.
Intentional shell-free subprocess boundaries have narrow Bandit rationale
comments; no scanner or rule category was disabled globally.

The public-only backend trust Secret uses readable `stringData` PEM instead of
base64 `data`; this preserves the bytes while making its non-credential contents
clear and avoiding the entropy-based secrets-in-config-file false positive.
New helper/test lint findings were corrected. Existing unrelated historical
alerts, including scanner-side Django initialization diagnostics, are not
silently dismissed. GitHub scan closure requires a genuine upload after the
follow-up commit is published.

Local validation used the existing repository CI requirements in a temporary
virtual environment: 599 tests passed with 21 environment-dependent skips.
The affected six Python files pass Pylint and Ruff checks. The refactored probe
was also exercised against all six live listeners, and the cryptography-free CA
key check succeeded in memory. No PKI/server/client configuration was changed
by these follow-up code checks.

Harbor, split DNS, VIP allocation, MetalLB and UDM were NOT changed. Its later
rollout requires UDM prefix-list/maximum-prefix preparation in unifi-infra and
fresh VIP availability checks, described in README.md.
