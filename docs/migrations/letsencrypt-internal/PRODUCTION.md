# Production migration — 2026-11-05

## Verified live

- Production GoDaddy DNS-01 issuer enabled; production canary issued successfully.
- All 17 service certificates and the separate OpenBao backend certificate are Ready.
- All 17 new service names resolve to the private ingress address. TLS verification succeeds using only ISRG roots, excluding the lab root.
- Both public ingress addresses return 404 for all 17 private hosts.
- Keycloak and OpenBao OIDC accept both old and new callbacks during the transition.
- UniFi contains 17 additional private DNS records; original records remain available.
- Daily health reporting now checks certificate readiness and expiration.

## GitOps phase 1 prepared

The active application directories now contain the new certificates and parallel private routes. Canonical application URLs switch to the new names. The GoDaddy webhook is adopted into Argo CD, and CI renders its Git-hosted Helm chart before validation.

OpenBao gains a second listener on 8202 using the public certificate, a leader-selected bridge Service, and a CoreDNS rewrite for `openbao-api.int.andreybondarenko.com`. The existing listener and private trust remain available. The StatefulSet uses OnDelete: syncing this source does not restart the three servers. Roll and unseal one server at a time only after the updated source is synced and the configuration is verified.

Before backend changes, an encrypted Raft snapshot was captured and its decryptability checked:

- Path: `/home/shaman007/.local/state/home-k3s/migrations/2026-11-05/openbao-before-domain-cutover-121900.snap.enc`
- SHA-256: `b8c373f14a1f310a3cd983b0a765da6e02ff4c1ececf5f42fb812dfd1b3521dd`

Validation: 320 repository tests passed (16 skipped); runtime-contract validation and diff whitespace checks passed. Eight affected applications rendered successfully.

## Remaining migration gates

1. Push phase 1 and verify Argo sync. Roll OpenBao followers individually, verify quorum and public TLS, then roll the leader.
2. Move SecretStores, monitoring, and Traefik backend verification to the new backend name and system trust. Migrate the GoDaddy credential store last.
3. Verify SSO login/logout on the new application URLs before removing old redirects.
4. Complete active repository and installed-client hostname updates; preserve Kubernetes API/node names and intentional historical references.
5. Retire old routes, certificates, DNS records, backend CA consumers, and private issuer only after consumer and renewal verification. Preserve Raft's intrinsic transport security and Kubernetes trust.

The backend private CA has not yet been retired. Automatic approval review rejected a global Argo reconciliation hold because of its broad impact; no holds were applied. Continue through staged source pushes and normal GitOps reconciliation.

## OpenBao bridge rollout completed

All three OpenBao servers were rolled individually and unsealed. Leadership was transferred before replacing the original leader. Each server's 8202 listener passed ISRG-only certificate verification. The new backend name resolves through CoreDNS, and the OpenBao container's bundled system trust successfully validates it.

A temporary SecretStore using the existing GoDaddy Kubernetes auth role authenticated through the new backend name without a CA bundle; it became Ready and was then removed. All 34 production SecretStores were Ready after the rollout.

The shell `VAULT_UNSEAL` value was rejected. With explicit user authorization, the separate recovery material in the local operator file successfully unsealed the replacements. No recovery value was printed or copied. The existing shell helper still uses the stale shell value; use the verified recovery source for further controlled rolls.

## GitOps phase 2 prepared (not deployed)

- All active SecretStore sources, including embedded Traefik objects and the GoDaddy chart, use the public backend name without a private CA pin.
- Traefik's OpenBao transport uses public SNI and system trust; both OpenBao ingress routes target the verified bridge Service.
- Prometheus uses the public backend name and no longer mounts the private CA.
- The primary listener and Raft retry-join configuration switch to public trust; the private TLS Secret is removed from the server mounts. Intrinsic Raft transport security and port 8201 remain intact.
- The obsolete backend certificate renewer is suspended. Its old certificate and PKI role remain available for rollback until phase 2 is deployed and verified.

Validation: 321 tests passed (16 skipped), runtime contracts passed, and six affected applications rendered. Push phase 2 before the next controlled server roll. After all servers and clients use public trust, remove the retired backend Secret and issuance role; do not remove shared PKI resources while legacy ingress certificates still depend on them.

## Final backend cutover completed — 2026-11-05

Source revision `6982530c` was reconciled. All three servers were rolled individually with leadership transferred before the original leader was replaced. Both listeners on every server use the current Let’s Encrypt certificate and pass ISRG-only trust verification; no server mounts the old private certificate.

All 34 live SecretStores use the public backend name with no private CA pin. All 49 ExternalSecrets completed a forced refresh. Prometheus reports `up{job="openbao",instance="openbao-api.int.andreybondarenko.com:8200"}=1`.

The backend certificate was manually renewed through cert-manager to revision 2. All six running listeners served the new certificate while all three pod UIDs remained unchanged, proving projected Secret propagation and automatic TLS reload without restarts.

The old server leaf was revoked through `pki-root/revoke`. Its dedicated issuance role, Kubernetes auth role, and ACL policy were deleted. The old `openbao-server-tls` Secret has no data or private key. The renewer remains suspended. Shared root/intermediate PKI and old ingress certificates are intentionally retained until their separate route/SSO retirement is verified.

An omitted public-SNI transport annotation on the new bridge Service caused ingress verification failures during the cutover. It was corrected live, added to source, and covered by a regression test.

Final cleanup source turns the retired renewer into a credential-free suspended stub, empties its RBAC, disables its ServiceAccount token automount, and prevents the legacy PKI bootstrap helper from recreating the backend role. These cleanup changes still need a source push; the live backend credential and issuance permissions are already retired.

Validation: 322 tests passed (16 skipped), including the bridge transport regression. The old shell unseal key remains stale; the explicitly authorized separate local recovery key successfully unsealed the servers. No recovery credential was printed or copied.

## SSO and legacy ingress retirement prepared

The backend cleanup at `87a4c399` is live: the old renewer is suspended, has no token automount or credential references, and its Role has no rules.

All active Keycloak URL settings and the OpenBao OIDC callback list now use the new domains. Grafana's database-backed SSO settings use the client ID `graphana`, despite the deployment environment specifying `grafana`; both active client identities were retained, and the actual runtime client's URLs were migrated without rotating its credentials or invalidating sessions. Only the unused `vault` client was disabled. URL-only inventory finds zero old-domain Keycloak clients. Grafana and Argo's actual redirects reach valid Keycloak login forms; Headlamp and OpenBao callbacks are accepted with PKCE. Interactive user login/logout remains unverified.

Remaining installed-client references were updated in the Bastioncam collector unit, two Noctalia plugin scripts, Codex's MemPalace endpoint, and the operator skill defaults. The collector was restarted and is active. Kubernetes API, node/service names, metadata annotation namespaces, historical documentation, fixtures, and deprecated sources remain intentionally unchanged.

Source now removes 17 old ingress routes, 18 private certificates (including the canary), and the `vault-acme` ClusterIssuer. The retired PKI bootstrap script exits without making changes. The daily health checker requires verified TLS for every ingress. The current source scan finds no old ingress-domain references in active home-k3s code/configuration.

Alertmanager's live external URL is `https://alerts.int.andreybondarenko.com`. Its deployed HTML email template rendered correct Alertmanager and Prometheus URLs without sending mail. The plain-text template previously lacked a direct Alertmanager link; source now includes one, validated with the deployed amtool template engine.

The failed CI run `42032262832` stopped in the hostname-inventory subprocess test. CI now explicitly installs ripgrep, the scanner reports a missing executable clearly, and the test exposes controlled subprocess diagnostics and uses the test interpreter. A fresh GitHub run remains pending the next push.

Validation: 314 tests passed (16 skipped), runtime contracts passed, and 13 affected applications rendered. UniFi's targeted retirement plan has zero additions, 17 in-place disables, and zero destroys; it has not been applied. Existing API/Omni/other unrelated records remain outside this plan.

After pushing this source, verify Argo reconciles removal, delete any non-pruned old ingress/certificate resources and unused certificate Secrets from `legacy-ingress-retirement.json`, disable private ACME issuance, and remove `pki-int/roles/w386-k8s-my-lan-acme`. Preserve the shared PKI mounts and issuer: `pki-int/roles/orangepi-monitoring` still covers the separate `m.k8s.my.lan` monitoring identity. Do not disable the entire issuer or remove host private trust blindly. Apply the reviewed legacy DNS plan after the route cutover.

## Legacy ingress retirement completed — 2026-11-05

Source `259090b1` was reconciled. All 17 old ingress routes, 18 legacy Certificate objects and their TLS Secrets, and the `vault-acme` ClusterIssuer are absent. All 18 retired leaves were revoked through the intermediate PKI. Private ingress ACME is disabled and its dedicated `w386-k8s-my-lan-acme` role was deleted. The unused private ACME account key and completed manual production canary were removed.

The shared root/intermediate issuers and the exact `orangepi-monitoring` role were preserved unchanged. `m.k8s.my.lan` still resolves to `192.168.1.111`; its HTTPS endpoint was unreachable from the operator host (errno 113), so runtime monitoring could not be verified. `api.k8s.my.lan` remains enabled and resolves to `192.168.30.100`; Kubernetes API trust and kubeconfigs were not changed.

UniFi cleanup destroyed all 22 old records: the 17 migrated service records plus `omni`, `omni-k8s`, `omni-siderolink`, `postfixadmin`, and retired `vault`. Their resource blocks and import stanzas were removed from `/home/shaman007/git/unifi-infra`. All 22 names no longer resolve, while all 17 new private records remain enabled at `192.168.30.211`. The full Terraform/OpenTofu configuration validates and a full plan would not recreate the deleted records. Its only remaining action is an unrelated in-place change to `unifi_client.g4_instant_left`, which was not applied.

All Argo applications are Healthy/Synced. The deployed daily certificate check passes for 42 Certificates and four ClusterIssuers. Two generated TLS Secrets with names outside the existing `*-tls` orphan-ignore pattern still trigger orphan warnings; source now explicitly recognizes only `godaddy-webhook-serving` and `letsencrypt-internal-staging-canary`. This narrow reporting correction needs a source push; certificate readiness remains checked normally.

GitHub validation run `42034528214` passed the previously failing inventory unit tests, runtime contracts, policy bundle generation, and application rendering; its remaining policy checks were still running at handoff. No email was sent during template/health verification.
