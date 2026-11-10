# Image and release signing

Signing sources have been published and the initial audit rollout is in progress.
The approved signing key and dedicated builder role are provisioned in OpenBao;
only the public key is in Git. Audit reports do not block images.

## Publishing paths

| Source | Output | Signing path |
| --- | --- | --- |
| Dockerfiles `docker-publish.yml` | GHCR images | GitHub OIDC, exact Buildx output digest, then verification |
| Bastioncam `container.yml` | GHCR image | GitHub OIDC, exact build-action output digest, then verification |
| User-owned Immich fork `docker.yml` | GHCR server and ML variants | After successful build/retag jobs, resolve commit-specific tags, sign and verify digest |
| Dockerfiles `build.sh` | Harbor images | `SIGN=1`, encrypted signing key from OpenBao, verify using pinned public key |
| Published release assets | Binaries, archives, packages, checksums | `sign-release.yml` publishes one `<filename>.sigstore.json` per file |

Release-file workflows are added to home-k3s, Dockerfiles, Bastioncam, key-val,
dotfiles and the user-owned Immich fork. These sign existing uploaded
files; they do not invent release/build pipelines for projects without releases.
The upstream Strata, SuperTux and Immich test checkouts are not our publishers;
their upstream release workflows and unrelated local edits are preserved.
Folders without a Git repository/release publisher have no automatic publication
path to integrate. Their files can use the manual verification contract below.

The release workflow runs on publication and supports manual retry with a release
tag, after all uploads finish. Downloads are treated as data, never executed.
It refuses unsafe filenames, drafts, empty releases, changed assets and failed
verification. GitHub-generated source archives are not uploaded assets and are
not covered; upload a stable source archive explicitly if it must be signed.
GitHub Actions uploads using `GITHUB_TOKEN` may not trigger another workflow;
if a producer uses that token to publish a release, dispatch signing explicitly
after upload or integrate the signing step into that producer.

Cosign v3.0.6 and its installer action are pinned. The installer checks its
bootstrap and downloaded release. Image/referrer compatibility with Harbor and
the deployed Kyverno must pass the rollout checks before enabling denial.

## Trust and admission

`kyverno/policy-verify-own-ghcr.yaml` restricts trusted signatures to the specific
repository, workflow, GitHub issuer, and main/release tag refs. Dockerfiles,
Bastioncam and Immich use separate repository match sets; signatures from one
project do not authorize images belonging to another project. Extend these
sets when adding new Dockerfile directories.

`kyverno/policy-verify-upstream.yaml` adds publisher-specific checks for Cilium
agent/operator release images and direct `registry.k8s.io` images. Trust identities
come from [Cilium](https://docs.cilium.io/en/stable/configuration/verify-image-signatures/)
and [Kubernetes](https://kubernetes.io/docs/tasks/administer-cluster/verify-signed-artifacts/).

All initial policies use Audit/Ignore, with digest mutation explicitly disabled.
They resolve signatures for the requested image but do not require digest syntax
yet. Pod policies scan all three image lists: regular, init and ephemeral containers.
Generated admission-only companion policies handle updates to
`pods/ephemeralcontainers`. Background list/watch checks apply only to Pods;
subresource policies explicitly disable background scanning. Autogeneration is
disabled to retain this Pod-only scope. Regenerate companions with
`python3 tools/supply-chain/generate-ephemeral-policies.py` and check with `--check`.
The AppProject permits ImageValidatingPolicy and the existing policy Application
includes these files. The existing force-fail-open controller setting remains.
An unmatched image is outside coverage even if a report shows a vacuous Pass.

Third-party Harbor proxy-cache images are deliberately outside these initial
policies. A cached image does not establish that upstream signatures/referrers
were mirrored. Verify both the exact cached digest and preservation/routing of
its publisher's signature before adding each upstream repository. Do not sign
third-party images with our key and describe that as publisher verification.
Images from publishers without usable signatures need an explicit documented
decision (replacement, reviewed digest, or exception) before blanket enforcement.

## Enable Harbor signing

The CronJob template enables signing. The
Dockerfiles script supports `SIGN=1` and checks Cosign/key prerequisites before
building. It records each Podman manifest push digest or the Docker Buildx output
digest, signs that digest, and verifies it. Failed signing/verification fails the
build. Registry publication and signature publication are separate operations:
a failed sign can leave an unsigned image in Harbor; enforcement is what prevents
its later use. Compatibility mode `SIGN=0` remains the default for existing callers.

The key and narrow `image-signing` policy plus dedicated
`external-secrets-image-builder` role were provisioned with operator approval.
Read-back verified key/public-key correspondence, secret contents and role scope.
The old Harbor role was preserved. Remaining rollout steps are below. Do not commit private keys, passwords or raw Secret manifests.

1. Create a dedicated password-encrypted Cosign key pair in a private temporary
   directory. Transfer the encrypted key and password directly into OpenBao KV
   `image-signing`, properties `private_key` and `password`, without logging them.
   Destroy temporary private material after confirming the secret can be read.
   Keep only `cosign.pub` in Git. This is an exportable build-signing key, not a
   non-exportable Transit key. A compromised privileged builder can use it to sign;
   separate signing infrastructure/Transit authorization would reduce that risk.
2. Give the image-builder External Secrets role read access only to this additional
   KV path; preserve its existing Harbor access. Use a scoped Harbor push account.
3. Render a concrete rollout using the actual public key:

   ```sh
   python3 tools/supply-chain/prepare-harbor-signing.py \
     --public-key /path/to/cosign.pub --output /tmp/harbor-signing-rollout
   ```

4. Review and publish the generated CronJob, ExternalSecret and public ConfigMap
   under `image-builder/`, and the generated policy under `kyverno/`. These
   are now integrated locally using `docs/supply-chain/cosign.pub`. Wait for the
   signing Secret to become Ready before syncing the changed builder CronJob.
   The renderer does not submit resources or modify the active CronJob.
5. The builder shares Podman's registry auth with Cosign, supplies the encrypted
   key/password at runtime, and copies the pinned upstream Cosign binary through
   an EmptyDir; no self-hosted builder image needs to be seeded. Verify those init
   containers on Talos before relying on the next scheduled build.
6. Run a controlled build after publishing the Dockerfiles signing changes.
   Verify the resulting **Harbor digest**, public-key signature, transparency
   record and Kyverno report. Test both the index and the platform selected by
   the node; do not assume signing an index automatically signs its child manifests.

The Harbor policy covers `library/*`. The GoDaddy one-off build renderer now
reuses the signing runtime and key references and signs/verifies its push digest.
For reviewed local one-off images (including the custom reports controller), use
`bash tools/supply-chain/publish-image.sh IMAGE:TAG` with `COSIGN_KEY` and
`COSIGN_PUBLIC_KEY` set; Podman and Cosign must share registry authentication.
The reports-controller build itself still only builds, without publishing.
Rebuild/review retained godaddy-webhook, custom kyverno-reports-controller and
year-vas3k-cloud images before enforcement. Do not retroactively sign unknown
existing images merely to silence findings. The year image's source/publishing
path is not present in the local projects and remains an explicit review gap.

## Verify a release file

Download the file and its adjacent bundle. Obtain the expected workflow identity
from a trusted repository/ref, rather than accepting whatever the bundle claims:

```sh
cosign verify-blob --bundle app.tar.gz.sigstore.json \
  --certificate-identity 'https://github.com/shaman007/PROJECT/.github/workflows/sign-release.yml@refs/tags/v1.2.3' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com app.tar.gz
```

For a manual dispatch on main, the identity ends in `@refs/heads/main`. A bundle
authenticates exact file bytes and the signing workflow identity. It does not
prove source-to-binary provenance or provide native RPM/DNF GPG trust, Apple
notarization, or Windows Authenticode. Those require package/platform-specific
release pipelines if introduced. Signing/checking individual files covers RPMs
as downloadable files, not automatic package-manager verification.

## Rollout acceptance and enforcement

1. Publish reviewed source changes without enabling Deny. Run each actual producer
   and verify its signatures from the destination registry/release independently.
2. Check Argo sync, all twelve image policies Ready, admission/report health, and
   per-policy report errors. Check signing/registry access from Kyverno's namespace.
3. Use safe unscheduled fixtures containing a valid signed image, an unsigned
   image, a wrong-signer signature, a tampered file, mixed signed/unsigned
   containers and init/ephemeral containers. Require the expected result in each
   case. A valid schema or a registry pull is not a signature test.
4. Complete Harbor signing, one-off-image review and upstream proxy-cache trust.
   Audit missing signatures separately from authentication, network and trust-root
   evaluation errors. Keep recovery-critical bootstrap dependencies available.
5. Only after operator review, enable scoped denial and digest requirements.
   Check the effective image-verification webhook failure policy as well as each
   policy: the existing forceFailurePolicyIgnore setting may defeat fail-closed
   behavior on verification errors. Review its effect on existing audit policies
   rather than changing it blindly. Test that unsigned/wrong-signer requests are
   actually rejected before claiming enforcement.

Rollback is to remove/disable only the new image policies and restore the previous
builder template. Keep trusted public keys and existing signatures for verification;
never delete images or workload data as part of rollback.

## Verification performed

- All 377 repository tests passed (21 skipped) using the existing CI virtualenv;
  focused signing/builder/project tests also passed after builder integration.
- Dockerfiles' three mocked build tests verified digest-only signing, read-back
  verification, and failure before latest publication when signing fails.
- The installed Kyverno 1.19.2 CLI verified the actual Cilium v1.20.4 signature.
  An intentionally wrong publisher identity failed without evaluation errors.
  Existing unsigned Canitiser images failed in regular, init and ephemeral roles,
  with zero evaluation errors. These were local fixtures, never admitted Pods.
- Twelve policies validated against the live CRD schema; Argo source rendering,
  actionlint, shell syntax, generated builder idempotence and strict Kubernetes
  schema checks passed.
- OpenBao encrypted-key/public-key correspondence, KV read-back, policy and
  dedicated namespace/service-account role binding were verified.

Still unverified: a newly signed own image through GHCR/Harbor, actual release
OIDC signing, External Secrets reconciliation using the new role, Talos execution
of the signing init containers, webhook enforcement, and third-party proxy-cache
signature preservation. Publication and destination-registry tests are required.

## Initial rollout repairs

The first live rollout exposed two issues that offline schema checks did not catch:

- A policy matching `pods/ephemeralcontainers` with background scans enabled
  fails Kyverno's reporting RBAC readiness checks. Pod background policies and
  generated admission-only subresource policies now have separate scopes,
  without granting unnecessary subresource list/watch rights.
- The default BusyBox binary requires a dynamic loader absent from the distroless
  Cosign image. The builder now uses the musl variant; its ELF was independently
  verified as statically linked before the retry.

The validation expression explicitly concatenates `images.containers`,
`images.initContainers` and `images.ephemeralContainers`. Relying on
`required: true` to reject unchecked init/ephemeral images produces false failures
for correctly signed images. Actual signed Cilium images now pass in all three
roles in CLI tests. The initial failed Job stopped in initialization before any
image build or publication.
