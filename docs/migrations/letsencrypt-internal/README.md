# Internal ingress migration to Let's Encrypt DNS-01

Status: staging solver/canaries deployed and verified on 2026-11-05.
Production certificate and backend CA cutover remain outstanding. See `STAGING.md`.
Selected suffix: `int.andreybondarenko.com` (user decision).

## Verified starting point

All three existing ClusterIssuers are Ready. `cert-manager`, `traefik-private`,
and `openbao` Argo applications are Synced/Healthy. There are 17 private ingress
endpoints using private-CA cert-manager Certificates and one private-CA canary.
Their exact namespace/name/Secret/hostname mapping is in `inventory.json`.
Every live ingress in that inventory uses `traefik-private`.
New names replace `.w386.k8s.my.lan` with `.int.andreybondarenko.com`.
The private ingress VIP remains `192.168.30.211`.

GoDaddy PAT at `kv/godaddy`, field `token`, was verified to list DNS records for
andreybondarenko.com. Write capability and DNS challenge issuance are not tested.
`~/git/dns` owns the permanent DNS configuration. Its reconciler now excludes
`_acme-challenge` TXT records so it cannot remove certificate solver challenges.

## Implementation direction

Use cert-manager with a GoDaddy v3 DNS solver. The inspected snowdrop and
neoGeneva solvers use legacy sso-key authentication. Lego v5.6.0 supports the new
PAT but its provider takes raw key authorization rather than cert-manager's
already-hashed TXT value, and its cleanup uses process-local record IDs. A small
adapter is implemented at `tools/godaddy-webhook`, using cert-manager's standard
aggregated API server with direct v3 API calls and restart-safe record discovery.

The chart at `tools/godaddy-webhook/chart` supplies the namespaced service
account, auth-delegator and authentication-reader bindings, APIService and
cert-manager caller RBAC, webhook serving TLS/CA injection, Service, Deployment,
network policy, External Secrets objects, staging issuer and unconsumed canary.
Production is disabled by default. Image digest and OpenBao CA bundle are required
values; the chart refuses to render without them. Before deployment, complete
image delivery/digest pin and provision the dedicated OpenBao role/policy. A Kubernetes-internal webhook serving CA
is distinct from the private ingress CA being migrated and is not user-facing.

Materialize the GoDaddy token through External Secrets. Create a dedicated
OpenBao Kubernetes auth role/policy restricted to `kv/data/godaddy`, bound to a
cert-manager-namespace service account. Do not give the webhook OpenBao root
access or broader secret-reading permissions. Mount the resulting token Secret
as a file; the solver rereads it per API operation to support token rotation.

Use distinct `letsencrypt-internal-staging` and `letsencrypt-internal-prod`
ClusterIssuers. Restrict their solver selector to `int.andreybondarenko.com`.
Leave public HTTP-01 issuers as configured. Decide recursive DNS self-check
configuration after testing resolution from controller Pods; public validation
requires authoritative GoDaddy TXT visibility despite internal service DNS.

## Ordered rollout and acceptance gates

1. Deliver the tested solver image and install its complete plumbing without
   modifying existing ingress routes or Certificates. Verify APIService Available,
   token synchronization, RBAC, and network reachability.
2. Issue an unconsumed staging canary for `acme-canary.int.andreybondarenko.com`.
   Verify Order/Challenge success, public authoritative TXT propagation, and
   cleanup. Retry after a solver restart to verify cleanup persistence.
3. Issue an unconsumed production canary. Verify SAN, validity and public chain.
4. Pre-issue separate per-namespace production Certificates for all 17 new names,
   with distinct Secret names. Keep existing names/certificates until cutover.
   Do not request a certificate containing both .lan and public names.
5. The staged `production-certificates.yaml` and `private-routes.yaml` provide
   17 parallel certificate/route pairs; they are outside active Argo paths.
   Add private-class ingress routes for new names. Set internal DNS names to the
   private VIP using the existing UniFi/split-DNS mechanism. Public A/AAAA records
   and public exposure are unnecessary. Verify internal resolution and TLS per
   endpoint, then update clients and application canonical URLs.
6. Update Argo CD URL, Grafana root URL, Prometheus external URL and Alertmanager
   external URL. Inspect Nextcloud/office integration, Keycloak redirect URIs,
   bookmarks, health checks, MCP endpoints and operator tooling for old names.
   Retain the existing private ingress class, source ranges and IP allowlists.
7. Verify the public ingress does not expose the new internal routers (IPv4 and
   IPv6). Verify service functionality internally with normal trust stores.
8. Exercise controlled renewal of the canary and one consumer; verify replacement
   Secret and served certificate. Remove obsolete private ingress Certificates,
   routes and internal DNS only after clients are migrated and caches expire.

No production state can be called migrated based on manifests or tests alone.
The goal requires current served certificate evidence for every endpoint,
working renewal, authoritative challenge cleanup, and working application URLs.

## OpenBao backend CA retirement (included in scope)

The user explicitly selected backend private CA retirement as well as ingress.
`openbao-server-tls` currently serves `.svc` API names and is renewed by the
private-CA `vault-pki-renewer` job. 33 live SecretStores use
`https://openbao.openbao.svc:8200` and pin the current private root. The repository inventory contains 35 definitions, including duplicate and inactive
candidates; these must be reconciled with the live set during cutover. The solver's
bootstrap SecretStore initially uses that same connection, creating an important
renewal dependency that must be preserved throughout the backend migration.

Target design:

- Issue a distinct production Certificate for
  `openbao-api.int.andreybondarenko.com` into a new backend TLS Secret. Keep it
  distinct from ingress certificates. Let cert-manager renew it with GoDaddy TXT.
- Resolve that name inside Kubernetes directly to the OpenBao Service, using a
  scoped CoreDNS rewrite. Avoid routing External Secrets through private ingress,
  adding a Traefik availability dependency, or changing public DNS exposure.
- Add the new listener/certificate in parallel if supported by the installed
  OpenBao version, or perform a staged one-node-at-a-time cutover after first
  migrating callers and trust. Require a verified fresh Raft snapshot and healthy
  three-voter quorum first. Never delete PVCs, peer data or unseal material.
- Migrate all SecretStores (including the solver bootstrap store), Prometheus
  scrape TLS settings, ServersTransport SNI/trust, OpenBao operator tooling and
  health probes to the public name and system trust. Remove pinned private CA
  bundles only after the new certificate is served and verified.
- Configure `leader_tls_servername` for the public backend SAN and system trust.
  Existing `.svc` connection addresses can remain when a caller explicitly sets
  verified SNI; SecretStores lack this override, so they need the DNS alias.
- Remove `BAO_CACERT` pointing at the old secret's `ca.crt`; ACME Secrets generally
  do not supply a root CA. Set `BAO_TLS_SERVER_NAME` where local API commands use
  a loopback address. Verify there are no skip-verification fallbacks.
- Replace the private certificate issuing job with a narrowly scoped certificate
  reload mechanism. Test renewal propagation to all three OpenBao processes.
- After all consumers have migrated, retire the private ingress ACME issuer,
  canary, role and server issuance policy/job, then audit private-root references
  before retiring the old CA. Preserve backups and rollback credentials.

Raft's cluster-port mutual TLS is generated and managed internally by OpenBao;
it is distinct from the user-managed listener certificate and Lab Root CA.
Verify installed-version behavior before changing Raft peer addresses. Retiring
our CA does not mean disabling OpenBao's intrinsic cluster authentication.
Backend cutover manifests remain to be prepared after validating parallel
listener support and the complete client inventory.

## References

- [GoDaddy v3 DNS API](https://developer.godaddy.com/en/docs/api-users/domains/manage/dns)
- [cert-manager external webhooks](https://cert-manager.io/docs/configuration/acme/dns01/webhook/)
- [Lego GoDaddy v3](https://go-acme.github.io/lego/dns/godaddyv3/)

## Backend bridge artifacts and current evidence

The deployed image is `quay.io/openbao/openbao:2.7.2`. That release documents
multiple TCP listeners and `tls_auto_reload`. The staged
`openbao-dual-listener-application.yaml` adds a second TLS listener on Pod port
8202, using a distinct ACME Secret and automatic reload every 30 seconds. Existing
8200 API/8201 Raft configuration, CA files and advertised addresses remain for
this bridge phase. `openbao-backend-bridge.yaml` pre-issues the backend certificate
and adds a leader-selected Service mapping port 8200 to target 8202, plus scoped
ingress permission for existing API consumers. These artifacts are not deployed.

The live Talos CoreDNS Corefile has no imports and does not mount
`coredns-custom`. Therefore the old custom ConfigMap cannot implement the alias.
`coredns-bridge-configmap.yaml` stages a single exact-name rewrite in the actual
Corefile. Compare with live state immediately before rollout and establish its
GitOps/Talos ownership before applying it; do not overwrite unrelated DNS edits.
CoreDNS should answer the public-domain API alias with the new Service address.
Its rewrite must leave `_acme-challenge.openbao-api.int.andreybondarenko.com`
untouched so the DNS-01 self-check and public ACME validation still query GoDaddy.

Backend bridge rollout order:

1. Require the production solver and backend Certificate Ready before adding its
   mandatory Secret volume to OpenBao. Check a fresh Raft snapshot and unseal
   readiness before any StatefulSet rollout; the cluster uses Shamir unsealing.
2. Add the second listener with one-node-at-a-time rollout and unseal, preserving
   at least two healthy voters. Require each node's new listener to serve the
   expected certificate before continuing to the next node. Both live and rendered StatefulSets use `OnDelete`; retain that strategy
   and replace only one explicitly selected Pod at a time rather than enabling
   automatic rolling replacement or assuming automatic unseal. Monitor both API health and committed/applied Raft indexes.
3. Add the new Service/network permission and exact DNS rewrite. Verify the alias
   from External Secrets, monitoring and Traefik network contexts. Test TLS using
   normal system trust before changing any SecretStore.
4. Migrate SecretStores in small batches, remove their CA pin, and require store
   Ready plus a successful actual secret refresh. Migrate the solver's own
   bootstrap store last in this phase and verify it still refreshes its PAT.
5. Switch monitoring and Traefik upstream to the verified alias/SNI and new
   listener. Test renewal and actual certificate reload on all three nodes.
6. Retire the old listener, private CA mounts, issuance job/policies and old
   private ACME issuer only after all callers have migrated. Final port and
   advertised-address changes need a separate controlled rollout. OpenBao's
   intrinsic Raft mTLS remains managed by OpenBao.

A local test helper `tools/godaddy-webhook/test-openbao-tls-reload.py` exercises
both loopback listeners and atomic projected-file rotation with generated fixture
certificates, without initializing OpenBao or using production credentials.
This supports the reload design; it does not prove live Raft rollout, public CA
issuance, Kubernetes DNS or SecretStore refresh behavior.

Release-specific reference:
[OpenBao 2.7.2 listener configuration](https://github.com/openbao/openbao/blob/v2.7.2/website/content/docs/configuration/listener/tcp.mdx).

Validation: the pinned OpenBao 0.30.6 chart renders the bridge with three
replicas, both TLS Secret mounts and the existing `OnDelete` update strategy.
The isolated OpenBao 2.7.2 dual-listener/projected-rotation test passed.

The solver chart supports its own backend migration with
`openbao.useSystemTrust=true` and
`openbao.server=https://openbao-api.int.andreybondarenko.com:8200`. That mode
omits the private CA pin and refuses the old `.svc` URL. Its initial bootstrap
mode continues to require the existing CA bundle. Do not enable system trust
before the public backend alias and listener have passed live verification.

The coordinated cross-repository and SSO migration plan is in
`DOMAIN-MIGRATION-PLAN.md`, with hostname-only code and live SSO inventories.
