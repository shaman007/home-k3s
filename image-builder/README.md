# Image builder

The `podman-builder` CronJob rebuilds the custom images from the public
Dockerfiles repository every day at 02:29 UTC. It runs privileged Podman with
`vfs` storage and publishes AMD64 images, matching every current cluster node.
Manual `build.sh` runs retain the default AMD64+ARM64 build contract; automated
ARM64 builds would require Talos nodes installed with the `binfmt-misc` system
extension or a native ARM64 builder node.

The dedicated namespace is the security boundary for this privileged workload;
Harbor remains under the cluster's default baseline Pod Security policy.

The `podman-builder` image is self-hosted in Harbor and must be seeded once from
the Dockerfiles repository with `./build.sh podman-builder`.

The ExternalSecret maps `kv/harbor` properties `user` and `password` to the
runtime-only `podman-builder-harbor` Secret. The associated SecretStore expects
a `vault-token-image-builder` Secret containing a `token` key with a Vault
policy that can read `kv/data/harbor` and `kv/metadata/harbor`.
