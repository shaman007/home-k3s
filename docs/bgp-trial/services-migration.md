# IPv4 BGP for all current MetalLB services

Deployed and verified 2026-11-06. All three production services now use IPv4 BGP
for routed traffic, retaining their original addresses and L2 access. Load
spreading is not an acceptance requirement.

## Live result

| Route | Active UDM next hops |
| --- | --- |
| 192.168.30.210/32: public Traefik | 192.168.30.209, 192.168.30.242 |
| 192.168.30.211/32: private Traefik | 192.168.30.100, 192.168.30.209 |
| 192.168.30.213/32: backup-rsync | 192.168.30.242 |

All three BGP sessions are Established. These three prefixes are the only BGP
routes on the UDM; it advertises zero routes to the cluster. Next hops were
matched exactly against each Service's ready EndpointSlices. FRR-K8s has three
5/5-ready Pods, the status cleaner is ready, and the MetalLB controller and all
speakers are ready with zero container restarts after their rollout. All
MetalLB ConfigurationStates are Valid.

Verification completed:

- All four original LoadBalancer Service specs and VIP status entries match the
  pre-rollout snapshot exactly. All IP pool and L2Advertisement specs also match.
- Public and private HTTPS over L2 returned 200; public IPv6 HTTPS and HTTP/3
  returned 200. Routed Wi-Fi public HTTPS/HTTP/3 and WireGuard private HTTPS passed.
- Certificate-verified TLS 1.3 handshakes passed for SMTP STARTTLS on 25 and 587,
  IMAPS on 993, and ManageSieve STARTTLS on 4190, from L2 and routed Wi-Fi sources.
- Minecraft returned a valid server-status response over L2 and routed Wi-Fi.
- Backup SSH returned its protocol banner over L2 and permitted routed WireGuard
  access. No backup data was changed and no mail was sent.
- Private ingress stayed unreachable from untrusted Wi-Fi, preserving its
  existing source restriction.
- Independent external HTTPS checks from Warsaw and London both returned 200
  at the public WAN IPv4 address. [External report](https://check-host.net/check-report/55ec8168k20).
- Temporarily excluding w386 from the production BGPAdvertisement reduced public
  ingress to `.242` and private ingress to `.100`. Twenty of twenty routed public
  HTTPS requests and twenty of twenty routed private HTTPS requests returned 200;
  backup's `.242` route and routed SSH remained available. All advertisement
  paths were restored and checked against ready endpoints again.
- `metallb`, `metallb-config` and `argocd-applications` are Healthy/Synced, with
  their original reconciliation/pruning settings. No migration holds or parent
  exclusions remain. The temporary WireGuard activation was disconnected,
  restoring the workstation's original interface state.

The repository independently advanced to `14b166453be940924ee713710983edc4f20342e4`
during the operation and already contained the prepared BGP manifests. Argo
therefore created the production advertisement at 10:11:13 UTC while FRR was
still starting, earlier than the planned trial-only gate. Production probes
passed during startup and after convergence. No commit or push was performed
by the assistant; unrelated concurrent Longhorn worktree changes were preserved.

The UDM configuration was updated in its existing object
`6aeda3a53563a3fcce7f329a`, using `udm-services.conf`; SD-WAN redistribution remains
disabled. Existing firewall policies, DNS and port forwards were not edited.
The separate `/home/shaman007/git/unifi-infra` project now manages that existing
object as `unifi_bgp.kubernetes` in `bgp.tf`, using `bgp-kubernetes.conf`. The
resource was imported by site name `default` without a router update. Its full
plan showed no BGP changes, additions or deletions; only unrelated camera-client
drift remained. Keep that FRR payload identical to `udm-services.conf` here.
The isolated test and its temporary HTTP firewall policy were subsequently
retired on 2026-11-06. Its namespace, service, pods, address pool and advertisement
are gone, together with the HTTP firewall policy and generated return rule.
The UDM now accepts only the three production /32s, with maximum-prefix three.
The shared peer retains its historical name `udm-bgp-trial` because it is used
by production; renaming it is unnecessary session churn. The UDM configuration
description is now `Kubernetes IPv4 service routing`. Obsolete test deployment
manifests were removed; `udm-services.conf` remains the production configuration.

Limits: no physical node failure, router reboot persistence, established-session
survival, complete mail delivery or actual backup transfer was tested. FRR's
shipped root/network-capability helpers produce Kyverno audit findings; no
enforcement settings or exceptions were changed to suppress them. The original
same-VLAN routed-pool asymmetry is avoided by retaining L2 for existing VIPs.

## Scope and intended behavior

| Service | Existing IPv4 VIP | Intended routed path |
| --- | --- | --- |
| Public Traefik | 192.168.30.210 | UDM BGP route to a node with a local ready endpoint |
| Private Traefik | 192.168.30.211 | UDM BGP route to a node with a local ready endpoint |
| backup-rsync | 192.168.30.213 | UDM BGP route to a node with a local ready endpoint |

Preserve all current addresses, source ranges, application NetworkPolicies,
DNS, port forwards and zone policies. Keep the existing L2 advertisements, so
same-VLAN clients reach these VIPs directly and do not require asymmetric
forwarding through the UDM. This adds BGP for routed IPv4 traffic; it does not
remove L2 or move the VIPs into the test subnet. The public IPv6 VIP
`2a02:e98:c0:181e::210` remains on L2. No IPv6 BGP is enabled.

`externalTrafficPolicy: Local` is already configured on all three Services;
MetalLB should advertise each VIP only from nodes with local ready endpoints.
Three established peers therefore do not imply three next hops for every VIP.
Private ingress's existing source restrictions remain mandatory even though the
UDM learns its route. No new production firewall allowance is required just to
preserve the existing destination addresses and published ports.

## Backend prerequisite

MetalLB 0.16.2's native validator rejects a BGPAdvertisement selecting a pool
containing IPv6. The public-ingress pool contains both families, so adding its
advertisement directly would be rejected. Do not split that pool while its
RequireDualStack Service depends on it. The staged chart switches to its bundled
FRR-K8s backend instead; the existing IPv4 peer explicitly leaves
`dualStackAddressFamily: false`.

The rendered FRR-K8s chart is 0.0.27, with FRR 10.6.2. It adds a host-networked
FRR DaemonSet, a status-cleaner Deployment, associated RBAC, webhook and four
FRR CRDs. Those CRDs already exist live from the previous installation and need
schema reconciliation, not deletion. The existing controller and speaker gain
the backend selector, and the speaker gains FRR RBAC. Existing speakers retain
their root/NET_RAW L2 context and one-at-a-time rollout strategy.

The shipped FRR container runs with NET_ADMIN, NET_RAW, SYS_ADMIN and
NET_BIND_SERVICE capabilities. This is a material runtime change from the
current native speaker. No Kyverno enforcement settings or policy exceptions
have been changed, and no additional blanket exemption is proposed. The
historical `review-metallb-l2.py` is a retirement-specific audit for chart
0.16.1; it is not a validator for this new backend configuration.

## Configuration files and pre-rollout checks

- `argocd/application-metallb.yaml`: enables bundled FRR-K8s, retains chart
  0.16.2, speaker security context/rolling strategy and disabled pruning.
- `argocd/application-metallb-config.yaml`: includes explicit BGP manifest names.
- `metallb/bgp-peer-udm.yaml`: persists the existing peer identity to avoid
  introducing a duplicate router neighbor. ASN and hold timer are unchanged.
- `metallb/bgp-advertisement-services.yaml`: selects only the two existing
  production pools and the UDM peer, with host-route aggregation lengths.
- `docs/bgp-trial/udm-services.conf`: accepts exactly the three production IPv4
  VIPs, with a per-peer limit of three. Exports no
  routes and keeps SD-WAN redistribution disabled in the existing API object.

Checks completed: YAML parsing; Helm 0.16.2 render comparison; Helm lint; exact
preservation of existing speaker rollout strategy; no chart resource removals;
only controller/speaker/backend RBAC modifications among existing rendered
resources. New components' container images/security contexts were inspected.
FRR startup, mixed-pool IPv4 advertisements and production forwarding were
subsequently verified as recorded above.

## Original rollout procedure (historical)

The trial referred to below existed during the original rollout and has since
been retired. These steps record the completed transition, not a current
instruction to recreate the test.

1. Capture the current application desired state, auto-sync/reconciliation state,
   non-secret MetalLB configuration, Service addresses and ready endpoints, UDM
   BGP config, routes and relevant firewall policies. Record public/private
   IPv4, public IPv6, SMTP/IMAPS/ManageSieve and backup SSH handshake baselines.
   Recheck peer health and the isolated test HTTP endpoint.
2. Update the **existing** UDM BGP config object using `udm-services.conf`, without
   changing its identity, WAN configuration, firewall or SD-WAN setting. Confirm
   it accepts only the four listed /32s. Do not add production advertisements yet.
3. Reconcile the MetalLB backend change first, independently of the production
   configuration application. Preserve existing holds and disabled pruning.
   If a temporary Argo hold is necessary for an uncommitted live rollout, record
   it explicitly and retain the user's existing no-commit/no-push rule. Do not
   let an app-of-apps undo the temporary desired state.
4. Wait for FRR-K8s, controller, webhook and all speakers to become ready. Confirm
   the test /32 returns to three Established sessions and test HTTP works after
   native-to-FRR transition. Recheck existing L2/IPv6 ingress. Stop and roll back
   the backend if this gate fails.
5. Reconcile the production advertisement and peer manifest only after the
   backend gate passes. Check each /32 in the UDM forwarding table against its
   Service's ready endpoint nodes. No unexpected prefixes may be present, and
   UDM-to-cluster advertised-route counts must remain zero.
6. Verify public IPv4 ingress through a routed/WAN path, private ingress over
   permitted routed access, backup SSH handshake from an allowed routed source,
   plus all same-VLAN and IPv6 baselines. A direct same-VLAN success alone does
   not demonstrate BGP forwarding. Preserve private-ingress denials from
   untrusted Wi-Fi and do not send mail or alter backup data for verification.
7. Exercise only an advertisement withdrawal for one production path where
   another ready endpoint exists, with bounded probes and immediate restoration.
   Do not stop a node or application merely to prove BGP. Endpoint failover is
   not equivalent to physical failure or preservation of established sessions.
8. Report the exact live state, any Argo holds and uncommitted GitOps drift.
   Do not resume reconciliation to a revision lacking the new backend and BGP
   configuration. Do not commit or push without a separate user request.

## Rollback

First protect the targeted applications from parent reconciliation and pause
their automatic sync, recording and preserving unrelated existing holds. The
current upstream manifests include BGP, so deleting an advertisement without
this protection would let Argo recreate it. Do not restore a native backend
while the upstream production advertisement can be reconciled again.

Remove only `BGPAdvertisement/routed-services` first, and confirm all three
production /32s disappear from the UDM BGP table. Existing L2 advertisements
should continue providing the original behavior. The production-only UDM
acceptance policy may remain while no production prefixes are advertised.
Do not restore the deleted trial prefix or its obsolete one-prefix policy.

If necessary, restore the captured native backend desired state and prior
reconciliation settings, with production BGP advertisements absent. Do not
delete any retained FRR CRDs, namespaces, PVCs, IP pools or existing L2
advertisements. Unused FRR workload cleanup is a separate reviewed operation;
keep pruning disabled. Recheck every production baseline.

References: [native backend validation in MetalLB 0.16.2](https://github.com/metallb/metallb/blob/v0.16.2/internal/config/validation.go)
and [MetalLB BGP configuration](https://metallb.io/configuration/_advanced_bgp_configuration/).
