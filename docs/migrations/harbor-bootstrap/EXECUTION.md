# Internal Harbor ingress execution — 2026-11-12

Historical pre-DNS deployment snapshot. For the completed DNS cutover and current
state, including removed Argo pauses, see [CUTOVER.md](CUTOVER.md).

## Current state

The separate `traefik-registry` Argo application runs two Traefik v3.7.18
replicas (chart 42.3.2) on distinct nodes. Its only route is the additional
`harbor/harbor-internal-registry` Ingress for the existing Harbor hostname and
`harbor-tls` certificate. It watches only Harbor Ingress resources; CRDs,
plugins, optional mounts and persistence are disabled. The container image is
pulled directly from Docker Hub so this controller does not depend on Harbor.
It uses the existing namespace egress rules and a dedicated ingress NetworkPolicy
selecting only its own pods on TCP 8443. The Service exposes TCP 443, uses
`externalTrafficPolicy: Local` and the explicit `192.168.30.212` VIP. Sources are
limited to Infrastructure, default LAN, WireGuard and pod CIDRs; this does not
override UDM firewall rules.

MetalLB has a separate non-auto-assigned `registry-bootstrap` IPAddressPool,
L2Advertisement and exact `/32` BGPAdvertisement to `udm-bgp-trial`. Existing
pools and advertisements are preserved. Monitoring now requires `.210`, `.211`,
`.213` and `.212`; the canonical exporter and mounted ConfigMap match.

## Verified

- Two ready replicas, zero restarts; ready endpoints on `.209` and `.242`.
- All three UDM BGP peers Established, ASN 65040, zero exported routes.
- Active next hops: `.210` via `.100`/`.242`; `.211` via `.100`/`.209`;
  `.213` via `.242`; new `.212` via `.209`/`.242`.
- Exporter scrape succeeds, reports all four routes, and reports zero policy
  violations. Its first startup scrape was temporarily unsuccessful; subsequent
  background and direct collections succeeded.
- Kubernetes schema validation reports 8 valid resources, 0 invalid, 0 errors;
  3 MetalLB CRDs were skipped by the public schema validator.
- Direct Infrastructure VLAN access to `.212` validates the system-trusted
  certificate, hostname and TLS 1.3. The certificate is identical to `.210`
  and expires 2026-12-27. No TLS verification bypass was used.
- Temporary private BusyBox fixture: anonymous manifest request 401; anonymous
  token grants no pull and still gets 401; authenticated token grants pull and
  manifest returns 200. Two complete `skopeo copy` pulls into fresh directories
  verified configuration/layer SHA-256 hashes (2 blobs, 2,226,622 bytes).
- Existing `.210` Harbor ping and `.211` OpenBao health return verified-TLS 200;
  `.213` still serves its SSH banner. `.210` also returns 200 over routed Wi-Fi.
- DNS answers match the captured pre-deployment baseline. No DNS, WAN forward,
  Harbor external URL, old ingress or UDM firewall change was made.
- 42 focused unit tests pass (cold-start candidates, BGP exporter, isolated pool
  and prefix scope, Argo project membership). Helm rendering succeeds.

## Remaining limits and cleanup

Routed Wi-Fi (`192.168.1.112` through `192.168.1.1`) to `.212:443` times out.
The local UDM source explicitly treats this network as untrusted and permits
published ingress only at `.210`; the broad trusted-LAN policy is disabled.
This is consistent with isolation, but the exact dropping device/rule has not
been confirmed by packet capture/counters. No firewall allowance was added.
A diagnostic request from the existing unifi-poller pod also timed out; its
namespace egress policy permits the controller, DNS and Prometheus rather than
Harbor. No exception was added for this optional diagnostic. This does not test
the node/containerd network path. WireGuard access and actual Talos/containerd
pull through `.212` remain untested.
The private pull was performed by a host client, not a Kubernetes image pull.
Do not switch DNS for a client network until its intended access is verified.

The private project `ingress-verification` (id 10), repository `busybox`, tag
`probe` remains for **the owner to delete**. Auto-review rejected using the
Kubernetes admin secret for cleanup; the owner declined that credential use and
explicitly chose manual deletion. No cleanup mutation ran.

## Publication and rollback

`harbor-custom`, `metallb-config`, and `unifi-exporter` had no skip-reconcile
annotation before this task; they now have `argocd.argoproj.io/skip-reconcile:
"true"` with explicit approval. Preserve these pauses until matching manifests
are published. New `traefik-registry` reconciliation remains enabled. The
new application pins the external Traefik Helm chart version.

After publication, verify the revision contains all new resources and the
four-prefix monitoring inventory, then remove only those three temporary pause
annotations and check owner sync/health and runtime tests again. Harbor sources
are committed locally at the owner’s request; publication is performed by the
owner. The temporary pause annotations are live state, not desired Git state.

DNS has not changed, so clients still resolve the previous route. If rollback
is needed, first withdraw only `registry-bootstrap` BGPAdvertisement, restore
three-prefix exporter inventory, and verify original routes/services. Remove
only the new Harbor Ingress, controller application and dedicated L2/pool
resources when unused. Never delete shared advertisements or Harbor data.
Keep UDM maximum-prefix four unless separately rolling back its policy; reduce
to three only after no peer can advertise a fourth accepted prefix. Publish
matching rollback sources before resuming the paused owners. Live deletions
require scoped authorization; these are instructions, not executed actions.
