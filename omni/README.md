# Omni test instance

Omni v1.12.4, chart 2.12.4, one replica with embedded etcd and a 10 GiB Longhorn volume.

- UI/API: https://omni.w386.k8s.my.lan
- Kubernetes proxy: https://omni-k8s.w386.k8s.my.lan
- SideroLink API: https://omni-siderolink.w386.k8s.my.lan

All three names resolve internally to Traefik at 192.168.1.210. TLS uses the existing
`vault-acme` ClusterIssuer. Sign in through Keycloak (`omni-test` client in the
`master` realm); the initial administrator is `me@andreybondarenko.com`.
The client callback is `https://omni.w386.k8s.my.lan/oidc/consume`.

External Secrets reads `omni.asc` and `config.yaml` from OpenBao `kv/omni` using the
namespace-scoped `external-secrets-omni` role and `omni` policy. Preserve this key
along with the volume: it is required to decrypt the database. No secret values
are stored in the repository.

The initial test deployment uses Helm release `omni` in namespace `omni`.
`argocd/application-omni.yaml` supplies the same pinned chart and values once these
files are published to main. The existing `home-k8s` cluster has been imported with all three control-plane
nodes. It remains locked to prevent Omni from changing its configuration.
`talos/omni-trusted-roots.yaml` adds the public lab CA without a reboot.
Original pre-enrollment node configurations are backed up in OpenBao
`kv/omni-import-backup`; no private configuration is stored in Git.
The WireGuard endpoint is LAN-only `192.168.1.100:30180/UDP`; gRPC tunneling is enabled.
