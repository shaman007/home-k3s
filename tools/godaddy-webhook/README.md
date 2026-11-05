# GoDaddy v3 cert-manager solver

Work in progress for the internal certificate migration. This is not deployed.

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
staging issuer and canary. It is staged outside Argo application paths and has not
been installed. Image delivery, dedicated OpenBao auth role/policy and live staging
issuance must be completed before any consumer cutover. Production issuance is
disabled by default.
No real GoDaddy writes are performed by the unit tests.
