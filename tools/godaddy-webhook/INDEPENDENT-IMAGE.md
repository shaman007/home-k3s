# Independent GoDaddy webhook image — prepared, not published or deployed

The current chart still uses the existing Harbor digest. This package prepares
`ghcr.io/shaman007/godaddy-webhook` from the same tracked Go source and Dockerfile.
It does not claim byte identity with the old build: take the new digest from the
successful publishing run, never reuse the Harbor digest without verification.

## Build and publication

`.github/workflows/publish-godaddy-webhook.yml` is manual-only and accepts only
this repository's `main`. It tests the checked-out source with the declared Go
image, builds linux/amd64 on a GitHub-hosted runner, publishes a full-SHA tag,
then signs and verifies the immutable digest using GitHub OIDC/cosign.
No Harbor, OpenBao, Kubernetes credentials or long-lived signing key is used.
Only the publish job receives packages-write and id-token-write permissions.
The workflow does not deploy, change package visibility or rewrite chart values.

The existing cluster build generator is retained for the old Harbor recovery
path; it is not needed for independent builds. This package does not dispatch
the workflow, publish an image, create a package, or change GitHub settings.

After review/commit/user push, separately authorize and manually run the new
workflow on main. Record its full source SHA, image digest, signature identity
and result. The first GHCR publication is private even for a public repository:
make **only this package** public before any cutover, with explicit authorization.
See [GitHub Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry).
Public anonymous reads avoid introducing a GHCR credential/ESO boot dependency.

Verify signature with the exact identity printed in the workflow and issuer
`https://token.actions.githubusercontent.com`. Test anonymous digest pull from
an empty, isolated auth/cache directory (including layers, not just metadata),
and reject any manifest/digest mismatch. Never dump auth configuration or tokens.
Inspect the new executable/image, rerun source tests and verify isolated solver
startup with disposable TLS/API fixtures before using it. Do not treat upload success
as runtime acceptance.

## Inactive cutover candidates

With the **verified new digest**:

```sh
python3 tools/godaddy-webhook/prepare_independent.py \
  --digest sha256:REPLACE_WITH_64_HEX_DIGITS \
  --output /tmp/godaddy-ghcr-reviewed
helm template godaddy-webhook tools/godaddy-webhook/chart \
  --namespace cert-manager \
  -f /tmp/godaddy-ghcr-reviewed/values-ghcr.yaml
```

The generator rejects tags/malformed digests and requires a new output directory
outside Git. It verifies syntax only; it cannot attest that a supplied digest
exists or is trusted. Its image-only values overlay changes no issuer, token,
CA, RBAC, serving certificate, readiness, volumes or replica strategy.
Its two Kyverno policy candidates cover ordinary and ephemeral Pod admission,
match only this GHCR repository and trust only the new main-branch workflow's
exact OIDC subject. They retain the current Audit/Ignore behavior; this is no
security-policy weakening or an enforcement rollout. All candidates are outside
Argo paths. Existing Harbor signature policies remain intact for rollback.

## Later authorized transition and rollback

1. Finish public anonymous pull, digest/signature and isolated runtime acceptance.
   Review the generated policies with the current Kyverno CLI/CRD and render the
   current Argo application with the image-only override. Inspect admission and
   signature results before promoting either policy candidate.
2. Prepare a focused Git change for chart repository/new digest and the two
   policy candidates. Refresh `docs/bootstrap-images/images.lock.json` and the
   independent image bundle with both old and new images during transition;
   do not substitute an unknown digest into the observed lock now. Record the
   old Harbor digest and matching rollback Git source.
3. Before authorized rollout, create short resource-scoped maintenance silences.
   The existing Deployment uses Recreate: allow a short solver interruption.
   Preserve all CA/serving/token Secrets, Certificates, DNS delegation and Harbor
   TLS. Do not force-renew Harbor or remove its current certificate as a test.
4. Verify imageID, ready APIService/Deployment, no repeated auth/TLS/admission
   failures; use an explicitly authorized staging DNS-01 canary and clean only
   its resources. Confirm Harbor's current certificate and both routes remain
   valid. Remove maintenance silences and verify Argo/alerts.
5. Only after acceptance mark the GHCR provider active in the startup graph and
   retire the active Harbor-image edge. Keep the old conditional recovery
   scenario as historical evidence and keep the independent bundle off-cluster.

Rollback is the old image repository + digest, retaining its signature policy.
It causes the same brief Recreate restart and restores the conditional Harbor
image dependency; use the preloaded old image/independent bundle if Harbor TLS is
unavailable. Do not roll back certificates, DNS, credentials or application data.

## Graph effect and limits

Current conditional ring:
`Harbor pull -> DNS-01 webhook -> Harbor certificate -> Harbor pull`.
After an accepted **public anonymous** GHCR cutover, the image edge comes from
external GHCR instead. Webhook serving TLS uses its local self-signed CA; DNS API
credentials are a persisted Secret (ESO needs OpenBao only to recreate it).
Fresh-cache startup still needs Internet/DNS/GHCR or the independent image
bundle. Missing credentials, lost CA/unseal material and disk loss remain
separate recovery prerequisites; this image move does not solve them.

## Local acceptance notes

The previously tracked module graph mixed Kubernetes 0.37.2 client/api modules
with 0.36.2 apiserver components and failed compilation (`scheme.Validate` API
mismatch). The prepared graph aligns apiserver, apiextensions, component-base
and their selected dependencies to 0.37.2, retaining the existing cert-manager
version and explicit patched x/crypto/x/net versions. `go mod tidy` removes stale
checksums; no production executable or Pod is changed by this local correction.
A dedicated read-only GitHub Go test/build workflow now runs on relevant source
changes, separately from manual publishing.

The alignment initially selected etcd client/pkg 3.7.0. Although govulncheck
reported no reachable vulnerable symbols, its package scan found
[GO-2026-6107](https://pkg.go.dev/vuln/GO-2026-6107); the final candidate pins the
fixed 3.7.1 release. The repeated source scan reports no vulnerabilities.

Validated locally: Go race tests and binary build in official Go 1.27.4; scratch
image built with the tracked Dockerfile; read-only/no-network/nonroot `--help`
smoke check; both workflows with containerized actionlint; 19 focused Python
tests, Ruff/Pylint, pre-commit and Helm render comparison. The image-only overlay
changes only the Deployment image in the rendered resources. The local image is
`localhost/godaddy-webhook-independent:20261114`; it is not a published GHCR digest.
No signed registry publication, anonymous GHCR pull, solver API startup with
Kubernetes authentication or staging DNS-01 was performed in this preparation.
