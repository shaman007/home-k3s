# Isolated IPv4 BGP trial

The initial trial was deployed and verified on 2026-11-06 and remains running.
The [subsequent production rollout](services-migration.md) enabled FRR-K8s and
IPv4 BGP for all three existing services, preserving L2 and service addresses.
The configuration and measurements below describe the initial native-backend
trial. Its namespace, service and pool remain manual trial resources outside
Argo source paths; the shared BGP peer is now managed by `metallb-config`.
No commit or push was performed by the assistant.

## Configuration

- Dream Machine Pro: UniFi OS 5.1.35; Network 10.6.109.
- UDM peer: `192.168.30.1`, ASN `65030`.
- Kubernetes ASN: `65040`; peers `192.168.30.100`, `.209`, `.242`.
- Test pool: only `192.168.40.240/32`, not an on-link VLAN or DHCP network.
  No matching non-default route existed before the trial.
- UDM accepts only that exact prefix, with a one-prefix limit per neighbor,
  exports no routes, and installs up to three equal-cost paths. No connected,
  pod, service, default, IPv6 or SD-WAN routes are redistributed.
- Existing MetalLB native backend handles IPv4 BGP without restarting any
  speaker. Native mode rejects an explicit `keepaliveTime`; `holdTime: 9s`
  derives the keepalive interval. UDM timers are 3/9 seconds.
- Existing public/private ingress and backup-rsync pools and L2 advertisements
  are unchanged. The new BGP advertisement explicitly selects only `bgp-trial`.
- The controller-wide Service class remains `metallb-l2`; this string identifies
  the existing controller, not the advertisement protocol.
- A restricted, digest-pinned Python HTTP DaemonSet runs on the three control
  plane nodes. No storage, service-account token, application NodePort, or
  external dependency is needed by the HTTP endpoint.
- Service source ranges and NetworkPolicy permit only `192.168.1.112/32` on
  TCP/8080. Pod egress is denied. Kubernetes still allocates a health-check
  NodePort for `externalTrafficPolicy: Local`.
- A temporary UniFi policy allows that same source/destination/port from
  Internal to Infrastructure, with an automatically generated response rule.
  No WAN port forward or DNS record was added.

Files: `cluster.yaml`, `udm.conf`, and `udm-firewall.json`. The firewall payload
is specific to the existing zone IDs; UniFi assigns the effective rule index.
The live trial policy index is 10007.

## Verification

| Check | Result |
| --- | --- |
| BGP sessions | Three Established/OK; one received route and zero advertised routes each |
| UDM forwarding table | Only test BGP prefix `192.168.40.240/32`; three active next hops, distance 20 |
| HTTP with all paths | 60/60 successful; all served by `talos-qlw-pbh` |
| Withdraw `.100` test advertisement | UDM retained `.209` and `.242`; 20/20 HTTP requests served by `w386` |
| Advertise only from `.242` | UDM installed that one next hop; 20/20 requests served by `talos-d4h-k5m` |
| Final restoration | Three active next hops restored; HTTP passed again |
| Production HTTPS after tests | Public IPv4, private Argo CD IPv4, and public IPv6 all returned HTTP 200 |
| MetalLB | Controller and all speakers running with zero restarts; all ConfigurationStates Valid |
| Trial pods | Three ready, zero restarts |

The test deliberately changes only BGPAdvertisement node selection. It verifies
route withdrawal and HTTP through all three nodes, not physical node failure,
the 9-second dead-peer timer, preservation of established connections, or router
reboot persistence. No production node, speaker or ingress pod was stopped.

Three installed ECMP next hops did **not** spread the 60 connections from this
single source across nodes. This is consistent with hashing that does not use
TCP ports, but the gateway's hash settings were not read. Multi-client load
distribution and throughput remain unverified.

The initial test from the workstation's Infrastructure IP (`192.168.30.79`)
completed a TCP handshake but stalled before HTTP, with repeated SYN-ACKs and
unacknowledged HTTP data. Same-VLAN return-path asymmetry and stateful gateway
tracking are a likely explanation, not a fully established diagnosis. The
verified test uses Wi-Fi (`192.168.1.112`) so replies traverse the UDM. Its source
allowance is intentionally the only one retained. Broadening access or migrating
ingress should first address routing symmetry and zone policy explicitly.

## Repeat the HTTP check

From the current workstation while its Wi-Fi address is `192.168.1.112`:

```sh
curl -q --interface wlo1 --connect-timeout 3 --max-time 5 \
  http://192.168.40.240:8080/
```

The JSON response identifies the node and pod. Binding the interface matters
because the workstation is connected to both LAN and Infrastructure. An address
change requires reviewing the three source-IP restrictions, not opening the
service generally.

UniFi's installed UI uses these read endpoints under
`/proxy/network/v2/api/site/default`: `/bgp/config/all`, `/bgp/neighbors`, and
`/routes`. Authentication was kept in memory; no credentials or cookies were
saved. The only UniFi configuration objects created are:

- BGP config `6aeda3a53563a3fcce7f329a`, description
  `Isolated Kubernetes IPv4 BGP trial`.
- Firewall policy `6aeda45c3563a3fcce7f32d3`, name
  `TEMP workstation to Kubernetes BGP trial`, plus its generated return rule.

## Rollback

The peer and UDM BGP configuration are now shared with production: do not delete
them or their production prefix allowances just to remove the test service.
Use the production rollout's rollback procedure to undo production BGP.

Remove only the trial, leaving existing ingress, MetalLB, VLANs and storage in
place. The following commands are rollback instructions, not actions performed
as part of verification:

```sh
kubectl delete service bgp-trial -n bgp-trial
kubectl delete bgpadvertisement bgp-trial -n metallb-system
kubectl delete ipaddresspool bgp-trial -n metallb-system
kubectl delete namespace bgp-trial
```

In UniFi, remove only the `192.168.40.240/32` permit from the shared BGP config,
lower its maximum-prefix limit to three, and delete the temporary workstation
HTTP firewall policy. Confirm its generated return policy disappears. Retain
all three production /32 permits and the shared BGP peer. Verify the test /32
is absent, production BGP/L2 routes remain, and repeat public/private IPv4 and
public IPv6 HTTPS checks. Update `udm-services.conf` to match if retiring the
test permanently.

References: [UniFi BGP](https://help.ui.com/hc/en-us/articles/16271338193559-UniFi-Border-Gateway-Protocol-BGP)
and [MetalLB BGP behavior](https://metallb.io/concepts/bgp/).
