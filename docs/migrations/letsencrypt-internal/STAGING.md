# First live stage for review

This stage builds and publishes only the new solver image, provisions its scoped
OpenBao read access, and installs the staging solver/canary. Production ingress
and backend cutover are later stages. The first live stage was executed and verified on 2026-11-05; see the result below.

## Image delivery

`tools/godaddy-webhook/prepare-build.py` generates a one-off Job manifest under
`/tmp`, bundling exactly Dockerfile, go.mod, go.sum and main.go in a ConfigMap.
The source archive hash selects the Job name and image tag. The Job runs the
same privileged Podman image as the existing image-builder CronJob, inherits its
network-policy labels, and uses the existing Harbor builder credential Secret.
It has no Kubernetes API token. It builds AMD64 and publishes
`harbor.andreybondarenko.com/library/godaddy-webhook:<source-hash-prefix>`.
The output includes the pushed image digest. The build Job has no automatic retry.

After approval, submit the generated ConfigMap and Job with `kubectl create -f`
(not `kubectl apply`), monitor that exact Job, inspect build logs, and obtain the
pushed digest. A failed Job is investigated rather than automatically recreated.
The temporary source ConfigMap can be deleted after successful delivery.

## Scoped OpenBao role

Inspect for existing policy/role names before writing. Using an already
authenticated administrative vault CLI, create:

```sh
vault policy write godaddy-dns-read tools/godaddy-webhook/openbao-policy.hcl
vault write auth/kubernetes/role/external-secrets-godaddy \
  bound_service_account_names=godaddy-vault-auth \
  bound_service_account_namespaces=cert-manager \
  audience=vault \
  token_policies=godaddy-dns-read \
  token_ttl=1h \
  token_max_ttl=1h
```

The policy only permits reading `kv/data/godaddy`. Do not print or change its
secret value. The role must not overwrite an unrelated existing role.

## Solver and canary

Render/lint the chart with the real image digest and existing public CA bundle
from an OpenBao SecretStore. Install a new Helm release `godaddy-webhook` in
`cert-manager` using these values. This installs 18 objects including an
unconsumed staging Certificate. `productionEnabled` stays false.
Do not use a placeholder image digest or test CA value from local render tests.

Validate APIService Available, SecretStore Ready, ExternalSecret Ready and the
staging Certificate Ready. Inspect Order/Challenge events without exposing token
Secrets. Independently query authoritative GoDaddy nameservers for the canary
TXT during issuance and its cleanup afterward. Confirm the resulting Secret
contains a staging-issued certificate for the exact canary SAN. Exercise renewal
and cleanup after a solver restart before enabling production issuance.

Rollback removes only this release and its scoped policy/role after its staging
challenges are cleaned up. Never remove pre-existing TLS Secrets, issuers, roles,
PVCs or backend trust while rolling back this stage.

## Verified result: 2026-11-05

- Build Job `godaddy-webhook-build-4c0784c82399` completed and published image
  `harbor.andreybondarenko.com/library/godaddy-webhook` at digest
  `sha256:0659c43b533c28641cf3f9bff97817878ded53fca924ad37535b8c9322f588c5`.
- Created `godaddy-dns-read` policy and `external-secrets-godaddy` role, bound only
  to `cert-manager/godaddy-vault-auth`, audience `vault`, token TTL/max TTL 1 hour.
- Installed Helm release `godaddy-webhook` revision 1 in `cert-manager`.
  APIService Available, SecretStore Ready and ExternalSecret Ready were verified.
- Main staging canary issued with the expected SAN and Let's Encrypt staging
  issuer, then renewed to certificate revision 2. Its observed expiry was
  2027-01-08T10:50:26Z. This is a test certificate, not public production trust.
- Both authoritative nameservers (`ns65` and `ns66.domaincontrol.com`) were
  independently observed serving the canary TXT, then removing it.
- A second unconsumed canary for `acme-restart-canary.int.andreybondarenko.com`
  was issued while the webhook was deliberately restarted after Present.
  It became Ready and its TXT was removed on both authoritative nameservers.
- The second canary and its Secret, plus the initial temporary build resources,
  were removed after validation. The main staging canary remains for renewal
  monitoring. No production issuer, production certificate or backend listener
  cutover was deployed in this stage.

The release is currently installed through Helm, outside Argo reconciliation.
Production migration must establish durable GitOps ownership as well as passing
production certificate and application checks.

The daily-mail source was updated to recognize the new internal suffix, verify
public-domain TLS chains, and inspect all cert-manager Certificates/ClusterIssuers
for readiness, expiry and failed issuance. Its 18 focused tests pass; the new
collector also passed against the live certificate inventory and a strict live
TLS probe passed against Bitwarden. These mail changes require a GitOps push to
become the scheduled report's deployed configuration.

A one-time Codex reminder was created for 2027-10-29 at 09:00 Europe/Prague to
rotate the GoDaddy PAT before its expected one-year expiry. Token contents were
not included in the reminder or deployment files.

## Security update and expanded migration inventory

The security dependency update rebuilt source archive `521881f7837c` and deployed
image digest `sha256:b848a323861e2491fe4686603a07dc2a5d1173464128860c161f9707575dc62a`
as Helm release revision 2. The staging canary then renewed to Certificate
revision 3. Solver tests passed and govulncheck v1.9.0 reported no vulnerabilities
in the updated module graph. See `tools/godaddy-webhook/DEPENDENCIES.md` for the
separate FOSSA license-fixture review and exact security dependency versions.
Remote FOSSA confirmation still needs the source changes pushed and rescanned.

The user requested SSO updates and a code-wide domain-usage scan. The scan now
covers `~/git`; `DOMAIN-MIGRATION-PLAN.md` coordinates the five repositories with
legacy ingress references. Live SSO was inventoried read-only: seven Keycloak
clients plus the OpenBao OIDC role. Only nonsecret URL settings were exported.
SSO mutation and production migration have not been executed in this stage.
