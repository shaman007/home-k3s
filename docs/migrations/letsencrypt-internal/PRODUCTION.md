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
