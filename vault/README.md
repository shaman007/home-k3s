# Vault (retired rollback source)

The Vault Helm application and public runtime resources are removed. Its two PVCs remain retained as a rollback source; OpenBao is the production endpoint.

## OpenBao backend TLS

OpenBao uses the cert-manager Certificate `openbao/openbao-server-letsencrypt-tls` and the backend name `openbao-api.int.andreybondarenko.com`. External Secrets, Traefik, and Prometheus validate it with system trust. CoreDNS resolves the backend name to the leader-selected bridge Service.

Both API listeners automatically reload the projected certificate every 30 seconds. A production renewal to revision 2 was verified on all three servers without pod restarts on 2026-11-05. Raft retains its intrinsic transport security on port 8201.

The old backend leaf certificate was revoked, its private key was removed from `openbao-server-tls`, and the dedicated `pki-root/roles/openbao-server`, Kubernetes auth role `vault-pki-renewer`, and matching ACL policy were deleted. The empty Secret and suspended renewer are retained as GitOps tombstones. The renewer source has no credentials, token mounts, or RBAC permissions; its ServiceAccount disables token automount.

Do not recreate the retired backend issuance role or restore the old private key. Recovery requires the verified unseal material; the old shell `VAULT_UNSEAL` value was rejected during this migration.

## Metrics and dashboard

Prometheus scrapes `openbao-api.int.andreybondarenko.com:8200/v1/sys/metrics?format=prometheus` using public TLS. See [the scrape configuration](../metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml). Grafana retains the [Vault overview dashboard](../metrics/grafana/config-map-grafana-dashboard-vault-overview.yaml).

## Legacy ingress PKI

The shared `pki-root` and `pki-int` mounts remain because legacy ingress certificates still depend on them. The compatibility-named ClusterIssuer `vault-acme` uses the restricted OpenBao ACME directory and the `w386-lab-intermediate` issuer. Retiring the backend credential does not revoke that issuer or its other leaf certificates.

New internal ingress domains use Let’s Encrypt. Remove the legacy PKI only after the remaining old routes and certificate consumers have been retired. See [the production migration record](../docs/migrations/letsencrypt-internal/PRODUCTION.md).

## External Secrets authentication

All 34 live SecretStores use `https://openbao-api.int.andreybondarenko.com:8200` without a private CA pin. Existing application ServiceAccount, role, and policy names remain unchanged. All 49 ExternalSecrets completed a forced refresh after the cutover.

The legacy Vault token rotator remains suspended with empty RBAC and no bootstrap token reference.
