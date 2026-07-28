# Image builder

The `podman-builder` CronJob rebuilds the custom images from the public
Dockerfiles repository every day at 02:29 UTC. It runs privileged Podman with
`vfs` storage and registers ARM64 emulation because every cluster node is
AMD64, while the published images support both AMD64 and ARM64.

The dedicated namespace is the security boundary for this privileged workload;
Harbor remains under the cluster's default baseline Pod Security policy.

The `podman-builder` image is self-hosted in Harbor and must be seeded once from
the Dockerfiles repository with `./build.sh podman-builder`.

The ExternalSecret maps `kv/harbor` properties `user` and `password` to the
runtime-only `podman-builder-harbor` Secret. The associated SecretStore expects
a `vault-token-image-builder` Secret containing a `token` key with a Vault
policy that can read `kv/data/harbor` and `kv/metadata/harbor`.
