# Image builder

The `podman-builder` CronJob rebuilds the custom images from the public
Dockerfiles repository every day at 02:29 UTC. It currently runs privileged
Podman with `vfs` storage and publishes AMD64 images, matching every current
cluster node.
Manual `build.sh` runs retain the default AMD64+ARM64 build contract; automated
ARM64 builds would require Talos nodes installed with the `binfmt-misc` system
extension or a native ARM64 builder node.

The workload does not receive a Kubernetes API token. Its runtime image is
referenced by digest, so rebuilding or replacing `podman-builder:latest` cannot
change the executable used by a later CronJob run. Updating the runtime is a
separate review step: seed the new image, verify its digest in Harbor, and update
the digest in `cron-job-podman-builder.yaml` through Git.
The builder is also isolated by a workload-scoped default-deny NetworkPolicy;
outbound traffic is limited to cluster DNS and HTTP/HTTPS for source downloads,
base-image pulls, and Harbor pushes. It has no allowed inbound traffic.

The `podman-builder` image is self-hosted in Harbor and must be seeded from the
Dockerfiles repository with `./build.sh podman-builder`. Although the nightly
source currently includes that image among its outputs, the output tag is not
used as the CronJob runtime.

## Remaining privileged-builder controls

Privileged mode remains an explicit exception until the Dockerfiles build has
been proven with rootless Podman or rootless BuildKit on Talos. Do not remove the
digest pin while testing rootless operation.

Before adding a builder node, label and taint it specifically for this workload,
then add the matching required node affinity and toleration here. Do not add a
toleration until a dedicated node exists: no current node is isolated for
privileged builds, and a toleration by itself would not provide isolation.

Use a Harbor robot account whose push permission is limited to the repositories
this job publishes. Store that account separately in Vault rather than reusing
an administrator or general-purpose `kv/harbor` login, then update the
ExternalSecret references. Harbor credential scope is an external registry
control and cannot be enforced by the Kubernetes Secret.

The ExternalSecret currently maps `kv/harbor` properties `user` and `password`
to the runtime-only `podman-builder-harbor` Secret. The associated SecretStore
uses the namespace-bound `vault-auth` ServiceAccount and the
`external-secrets-image-builder` Vault Kubernetes auth role. Replace this shared
credential with the scoped robot account described above before treating Harbor
least privilege as complete.
