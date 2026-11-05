# Domain usage and SSO migration plan

Target ingress suffix: `int.andreybondarenko.com`. Scope includes replacement of
our private ingress CA and the OpenBao backend listener's private CA. This plan
was requested after the staging DNS-01 deployment and scans code outside the
Kubernetes repository as well as cluster configuration.

## Evidence gathered

A hostname-only scan across `~/git` found 157 references to the old ingress
names in configuration/code across five repositories. This is a candidate count,
not 157 independent endpoints. It includes snapshots and repeated configuration.
The scan also inventories tests, documentation, Kubernetes API names, metadata
annotation keys and OpenBao/Vault service names. It excludes Git internals,
module/vendor caches, common generated directories and benchmark result fixtures.
Ignored files and symlink targets outside the scan roots need a separate pass.
No source lines, credentials or client secrets are copied into the report.

| Repository | Old ingress references in configuration/code | Main owners |
| --- | ---: | --- |
| home-k3s | 132 | Certificates, Ingresses, app URLs, SSO snapshots, helper scripts |
| unifi-infra | 17 | Internal DNS records in Terraform |
| dotfiles | 6 | Shell OpenBao URL, collector service, Noctalia monitoring plugins |
| bastioncam | 1 | Collector systemd service URL |
| dns | 1 | OpenBao URL used to retrieve the GoDaddy token |

`domain-usage-inventory.json` gives file/line/hostname references and categories.
`scan-internal-domain-usage.py` can regenerate the full candidate report under
`/tmp`. `.local` matches can also be programming-language identifiers: review
those manually instead of replacing them.

The live SSO inventory contains seven Keycloak clients with legacy domains:
`argocd`, `grafana`, `graphana`, `headlamp`, `openbao`, `traefik-admin`, and `vault`.
The OpenBao `keycloak` OIDC role has both UI and CLI callback configuration.
`graphana` and retired `vault` are still enabled; review current usage before
retiring them or expanding their callbacks. `sso-inventory.json` contains only
allowed URL settings and proposed hostname substitutions. It is a plan, not a
full realm export or an executable overwrite payload.

## Ordered implementation

1. **Freeze the mapping and ownership.** Use `inventory.json` for the 17 ingress
   targets. Record each active client, service and config owner before edits.
   Check worktrees and repository-specific instructions before editing another
   repository. Audit ignored/local operator settings and MCP endpoints using
   hostname-only output. Keep credentials in their existing secret stores.
2. **Complete production issuance prerequisites.** Staging has passed initial
   issuance, renewal, authoritative TXT cleanup and solver restart recovery.
   Its security-patched image also renewed the canary to revision 3. After live
   production authorization, issue an unconsumed production canary, verify SAN
   and public trust, then issue parallel per-namespace Certificates and the
   distinct OpenBao backend Certificate. Keep existing Secrets until cutover.
3. **Add internal DNS and routes.** In `unifi-infra`, add the new exact ingress
   names to `192.168.30.211` alongside the old names. Use the private ingress
   class and existing IP/client guards. Configure the OpenBao backend alias via
   the actual CoreDNS Corefile and leader-selected backend bridge Service;
   `coredns-custom` is not loaded by the live Talos CoreDNS deployment.
   No new public A/AAAA records or public exposure are required.
4. **Prepare SSO on both sides.** Add exact new redirect URIs and necessary
   allowed origins to the active Keycloak clients while retaining working old
   callbacks. Include logout redirects. Add the new OpenBao UI/CLI HTTPS
   callbacks to its OIDC role, retaining the intentional localhost CLI callbacks.
   Preserve client secrets, protocol mappers, roles and unrelated authentication
   settings. Do not turn an existing wildcard into a broader allowed origin.
5. **Switch app canonical URLs with their routes.** Update Argo CD `url`, Grafana
   `GF_SERVER_ROOT_URL`, Prometheus and Alertmanager external URLs, and any
   discovered callback/base URL configuration. The Keycloak discovery issuer
   remains `https://sso.andreybondarenko.com`; only migrating relying-party URLs
   change. Switch root/base/admin URLs after each target's DNS and TLS work.
   Update `traefik-admin.client.json` and the sanitized realm snapshot so helper
   scripts cannot restore old allowlists. Validate every private console using
   actual login, authorization, callback and logout flows before removing old
   callbacks. OpenBao has its own callback allowlist as well as Keycloak's.
6. **Update application clients and operator code.** Change Bastioncam collector
   service URLs, the DNS tool's OpenBao address, shell/operator defaults and the
   Noctalia monitoring plugin URLs. Verify repo dotfiles against the actually
   installed user configurations and restart/reload consumers only when needed.
   Update dashboard links, health-check URLs, scripts and tests in the same
   ownership batches. Check clients in other repositories before retiring aliases.
7. **Migrate the OpenBao backend safely.** Follow the staged dual-listener bridge
   in the main runbook: fresh snapshot, healthy three-voter quorum, verified
   unseal path, `OnDelete` one-Pod-at-a-time replacement, public-domain backend
   SAN, system trust, automatic certificate reload. Migrate all 33 live
   SecretStores and other callers in batches. Reconcile the 35 repository
   definitions (including duplicate/inactive candidates) rather than blindly
   applying them. Migrate the solver's own credential store only after the new
   backend is proven so renewal does not lose access to its DNS token.
8. **Update daily mail checks and deploy them through GitOps.** Source changes
   already recognize the new internal suffix, enforce public trust for public
   domain certificates, and check cert-manager readiness, expiry and failed
   renewals, including non-ingress backend certificates. Tests and a read-only
   live check passed. Push is still required for the scheduled job to use them.
   After full migration remove the temporary legacy `.lan` unverified probe path.
9. **Retire the old CA and URLs only after verification.** Remove retired
   ingress routes/certificates, DNS records, obsolete callbacks, private CA pins,
   private server issuance jobs/policies and old ACME issuer in dependency order.
   Audit operator/browser CA trust separately. Retain rollback material and
   backups; never delete PVCs, Raft data or unseal material as certificate cleanup.
10. **Repeat the inventory and prove the result.** Require no unexplained legacy
    references in active configuration/code. Explicitly account for historical
    documentation, test fixtures, rollback artifacts and metadata-only annotation
    domains. Check runtime URLs as well as Git. Verify certificate renewal,
    DNS TXT cleanup, actual served public trust, SSO login/logout, mail report
    content and continued private-only accessibility for every migrated service.

## Names that need separate decisions

`api.k8s.my.lan`, node names, Omni/SideroLink names and Kubernetes `.svc` names
are not aliases of the 17 ingress endpoints. Inventory them, confirm whether they
are active, and assess SANs, kubeconfigs, Talos configuration and clients before
renaming. Kubernetes' own CA and OpenBao's intrinsic Raft mTLS are distinct from
our Lab Root CA; replacing our CA does not imply disabling those trust systems.
Metadata such as `vault.w386.k8s.my.lan/token-policies` is an annotation namespace,
not necessarily a DNS request. Preserve or migrate it only with its consumer.

## Gates still outstanding

Production deployment/cutover authorization, production issuance, private DNS
and route cutover, live SSO updates and browser-flow verification, backend
rollout/unseal, client updates across repositories, deployment of the daily-mail
changes, CA retirement, and final inventory/runtime verification remain open.
No bulk domain replacement or live SSO changes were performed by this planning
pass. The GoDaddy token reminder is scheduled for 2027-10-29 at 09:00 Prague time.
