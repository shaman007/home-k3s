# Retired IPv4 BGP trial

The isolated trial was retired on 2026-11-06 after successful production rollout
for public Traefik, private Traefik and backup-rsync. No test workload or test
route is needed for normal operation.

Removed from the cluster: namespace `bgp-trial` and its HTTP DaemonSet, Service
and NetworkPolicy; MetalLB IPAddressPool `bgp-trial`; and BGPAdvertisement
`bgp-trial`. No PVCs or application data were present in the test namespace.

Removed from UniFi: the `192.168.40.240/32` acceptance entry and temporary
workstation-to-test TCP/8080 policy, including its generated return policy.
The shared BGP config now permits only `192.168.30.210/32`, `.211/32` and `.213/32`,
with maximum-prefix three and no route exports.

The shared peer `udm-bgp-trial` and production advertisement `routed-services`
are retained. The peer's historical name does not mean the trial still exists;
it now belongs to production. Existing addresses, L2 access and IPv6 remain.

After retirement, all three peers were Established with zero route exports;
the UDM had exactly the three expected production routes and unchanged next
hops. Public/private L2 HTTPS, routed public HTTPS, IPv6 HTTPS, mail TLS
handshakes and backup SSH passed again. Private ingress remained blocked from
untrusted Wi-Fi. MetalLB and its config application were Healthy/Synced.

Obsolete test deployment files were deleted. This also removes the root-path
readiness probe rejected by CI run 42204420038; no validator was weakened.

The initial trial verified three BGP sessions, HTTP through each node, and route
withdrawal: 60/60 baseline requests, 20/20 after removing the selected next hop,
and 20/20 through the third node. Production subsequently passed its own routed
checks and a 40/40-request withdrawal exercise. Load spreading was not required.

See [production rollout, verification and rollback](services-migration.md).
[udm-services.conf](udm-services.conf) is the current production router payload.
No commit or push was performed by the assistant.
