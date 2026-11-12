# Harbor internal DNS cutover — 2026-11-12

## Applied scope

The existing Harbor hostname now resolves internally to `192.168.30.212`.
Public GoDaddy A `81.19.4.105` and AAAA `2a02:e98:c0:181e::210`, WAN forwarding,
the old public Traefik route and certificate renewal remain unchanged.

Owning UDM sources in `/home/shaman007/git/unifi-infra`:

- `harbor-internal-lan.tf`: Default LAN (`192.168.1.0/24`) to `.212`, IPv4 TCP
  **443 only**, with established return traffic. No UDP, other ports or other
  destination hosts are added. Existing 132 policies and their indexes were
  compared against the live pre-change inventory and remained unchanged.
- `harbor-internal-dns.tf`: local CNAME `harbor.andreybondarenko.com` to
  `harbor-registry.k8s.my.lan`, whose A is `.212`; both TTLs are 60 seconds.
  A plain local A override still forwarded public AAAA. The CNAME and local
  A-only target prevent this without introducing a Kubernetes/CoreDNS dependency.
  On UDM DNS `.30.1` and `.1.1`, AAAA queries now return the local CNAME with no
  AAAA address. The public authoritative records were not edited.

Legacy zone/network IDs in the imported Terraform tree are stale. A first
reference-based targeted plan exposed provider identity errors and unrelated
network drift; it was **not applied**. The new firewall policy uses IDs read from
live zone/network API metadata, isolating it from those dependencies. Do not run
a broad apply. The verified firewall apply was exactly 1 create; the final DNS
step was 1 local target create and 1 existing local DNS record update, no destroy.

## Node ingress policy correction

Kubelet traffic from a different node arrived as Cilium `remote-node` identity
using its Cilium host IP. Hubble proved `INGRESS DENIED / Policy denied` at the
new controller despite the Kubernetes NetworkPolicy CIDR allowances.

`traefik/cilium-network-policy-traefik-registry-allow-node-pulls.yaml` permits
`host` and `remote-node` identities plus cluster pod identities (separate ingress
rules, explicit Kubernetes namespace-label selector) to pods labelled
`app.kubernetes.io/instance=traefik-registry-traefik`, only backend TCP **8443**.
The Service still exposes only TCP 443. No other controller, listener or egress
is opened. This manifest is included by the existing `traefik-network-policy`
Application source filter; cold-start candidate generation now includes both
policies.

The CNP is controller-validated (`Valid=True`).

Image-builder's existing web egress permits external TCP443 but did not permit
Cilium-translated internal endpoints. A second scoped policy,
`image-builder/network-policy-podman-builder-internal-registry.yaml`, selects
only the existing podman-builder labels and allows only the internal registry
pod selector in `traefik` on TCP8443. Live Hubble first proved EGRESS DENIED;
after correction it proved EGRESS and INGRESS ALLOWED, and the builder-network
TLS probe returned HTTP200 from `.212`. The original public route still returns
200. Direct `.210` access from builder pods remains denied, as it was before;
no old egress policy was widened. No build or push was executed.

Both policies are live; their sources are committed locally for publication.
The policy rollout introduced no Argo reconciliation pause. After publishing, run an explicit
selective sync of this new CNP through `traefik-network-policy` if needed to add
Argo tracking: a manually pre-created identical resource can otherwise appear
Synced while remaining untracked. Do not suppress orphan monitoring to hide it.

## Runtime validation

- LAN/Wi-Fi HTTPS with the real hostname and normal DNS returns HTTP 200,
  remote IP `.212`, with system-trusted TLS verification.
- Three explicit kubelet tests (`talos-qlw-pbh`, `w386`, `talos-d4h-k5m`) used
  `imagePullPolicy: Always`, image
  `harbor.andreybondarenko.com/dockerhub/library/hello-world:latest`, and verified
  `Pulled` events plus successful container execution. Before global DNS change,
  temporary per-node hosts entries pinned `.212`; Hubble confirmed internal
  backend TLS flows. These entries were removed immediately after each test.
- After DNS cutover, all three kubelet tests passed again **without hosts
  overrides**. New Hubble flows relative to the pre-test snapshot proved actual
  requests to the isolated internal controller, rather than the old route.
- Only temporary, uniquely named pods without volumes or credentials were
  deleted. Production images and volumes were not removed. Host overrides are
  absent on all nodes. No node or runtime restart was performed.
- Direct queries to UDM Infrastructure and LAN resolvers return `.212` and no
  public AAAA. Queries to external resolver `1.1.1.1` still return the original
  public A and AAAA. Ordinary LAN curl reaches `.212`; explicitly selecting the
  public address still returns HTTP 200 through the old route.

Initial digest/tag pulls could be satisfied by cache and were not treated as
proof. A physical-interface VIP filter was also insufficient with Cilium service
translation; the successful gates used real kubelet pull events and Hubble.
An interrupted test left one temporary hosts entry; it was explicitly removed
before testing continued. No temporary mapping remains in the intended state.

## HTTP-01 renewal follow-up

Harbor's existing `letsencrypt-prod` issuer uses HTTP-01 on public Traefik.
Before the correction below, cert-manager had no explicit HTTP-01 resolver
flag. Its default self-check would use the internal view, reaching `.212:80`,
which is intentionally not exposed. The certificate remains Ready and its
scheduled renewal is 2026-11-27. The resolver correction is already applied.

Applied, Helm-rendered correction: controller extraArg
`--acme-http01-solver-nameservers=1.1.1.1:53,8.8.8.8:53`. Existing controller egress
policy already permits TCP/UDP53. This changes only HTTP-01 self-check resolution,
not GoDaddy records or DNS-01. This is the supported
[HTTP-01 propagation-check resolver option](https://cert-manager.io/docs/configuration/acme/http01/#setting-nameservers-for-http-01-solver-propagation-checks). The chart has three controller replicas with
`maxUnavailable: 1`, `maxSurge: 0`. The user explicitly authorized this shared-controller change. It is applied:
all three controller replicas rolled successfully and carry the flag. Only
Argo application `cert-manager` is temporarily paused until the local source is
published. Existing Harbor certificate remains Ready, with no forced renewal. Full ACME
renewal was not forced or claimed as tested.
Both public resolvers were verified reachable from the cert-manager namespace.

## Final verification limits

The exporter reports three Established peers, four expected routes (next-hop
counts 2/2/1/2), zero route exports and zero policy violations. Extra direct BGP API
reads briefly timed out and the exporter reported scrape failure; subsequent
fresh reads recovered and confirmed all three peers Established and exact
unchanged next hops (.210 via .100/.242, .211 via .100/.209, .213 via .242,
.212 via .209/.242). No BGP configuration changed in this stage. Both targeted post-apply plans
for the new firewall and DNS resources are clean. Final BGP scrape success is 1,
with a 14-second-old successful collection, three established peers and zero
policy violations. 26 related unit tests pass; the standard NetworkPolicy schema
validates, and Cilium separately confirms `Valid=True` for the CNP. All old VIP service probes pass.

Argo's global report currently flags the newly created, unpublished CNP as an
orphan in the shared Traefik namespace. Its source must be published and adopted
by `traefik-network-policy`; the builder policy similarly belongs to
`image-builder`. After publication, selectively sync both policies and verify
tracking before removing the remaining `cert-manager` pause. This is a publication caveat, not a reason to delete or ignore
working security policies. Only `cert-manager` is paused with explicit approval; the three earlier Harbor/MetalLB/exporter pauses remain removed.

## Rollback

1. Keep `.212` and its Cilium policy serving traffic while resolver caches drain.
2. Disable only `unifi_dns_record.harbor_internal` (`enabled = false`) with a
   reviewed targeted plan showing one in-place update and no unrelated changes.
   Public DNS then becomes visible internally again. Verify both old public
   answers and old Harbor HTTPS before retiring the internal path.
3. Leave `harbor_internal_address` harmlessly present or disable it separately;
   deleting protected Terraform resources is unnecessary. Account for previous
   cached DNS TTLs before removing any serving resources.
4. Disable only `harbor_internal_lan_https` if rolling back LAN access. Keep
   public firewall/WAN policy unchanged. Do not remove the node-ingress CNP while
   any client still resolves `.212`.
5. If retiring the ingress later, follow the narrow BGP rollback in README:
   withdraw only its dedicated advertisement, never shared old VIPs. Reducing
   UDM maximum-prefix is separate and must wait until a fourth route is absent.

A rollback changes only the new internal resources. It never edits GoDaddy or
removes Harbor data, certificates, existing routes or shared policies.
