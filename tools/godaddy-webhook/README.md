# GoDaddy v3 cert-manager solver

Staging solver was validated on 2026-11-05. Harbor production DNS-01 was
subsequently accepted on 2026-11-14; see `docs/migrations/harbor-dns01/README.md`
from the repository root. This is the existing custom GoDaddy v3 solver.

Uses cert-manager's authenticated aggregated webhook server and GoDaddy's v3 DNS
API with a PAT mounted at `/var/run/godaddy/token`. Solver group is
`acme.int.andreybondarenko.com`; solver name is `godaddy-v3`.
Only `_acme-challenge` TXT names beneath `int.andreybondarenko.com` are accepted.
The API host and authoritative zone are fixed; per-request config cannot redirect
credentials or expand domain access. The GoDaddy token itself should be limited
to DNS operations in the account.

`ChallengeRequest.Key` is already the TXT value. Lego's provider takes a raw ACME
key authorization and computes the TXT value itself, so it cannot directly serve
this interface. Also, its current GoDaddy v3 cleanup retains record IDs in process
memory. This adapter instead queries matching records on every operation, reuses
an existing exact name/value on Present, and deletes only matching IDs on CleanUp.
That supports cert-manager retries, solver restarts, and simultaneous challenges
with different TXT values. Requests are serialized within the process; run one
replica until multi-process races are covered. API write requests are not retried.
Network errors and response bodies are never logged or returned to cert-manager.

Build/test with Go 1.26 or newer:

```sh
go test ./...
CGO_ENABLED=0 go build -trimpath -o /tmp/godaddy-webhook .
```

The chart includes webhook TLS/APIService/RBAC, External Secrets integration,
staging issuer and canary. The chart is managed by Argo application
`godaddy-webhook` with production enabled; chart defaults keep production
disabled for isolated rendering. Image delivery, scoped OpenBao auth, staging
issuance/renewal/cleanup and Harbor production cutover have been verified.
No real GoDaddy writes are performed by the unit tests.

## Independent image preparation

See [GHCR publication, cutover and rollback](INDEPENDENT-IMAGE.md). This is an
inactive preparation package; current chart/Argo sources retain the Harbor image.
