# Native dual-stack shared ingress

Enabled 2026-10-27. IPv4 remains primary; no public DNS records were changed.

## Addresses and allocation

- Existing ingress IPv4 VIP: `192.168.30.210`.
- Shared ingress IPv6 VIP: `2a02:e98:c0:181e::210`.
- Existing IPv4 Pod/Service ranges stay `10.42.0.0/16` and `10.43.0.0/16`.
- Private IPv6 allocation: `fd74:67a:1fcf::/48`.
- IPv6 Pod allocation envelope: `fd74:67a:1fcf:4200::/56`.
- IPv6 Service range: `fd74:67a:1fcf:4300::/112`.

The cluster uses Cilium Kubernetes-hostscope IPAM. Existing Node `spec.podCIDRs`
are immutable and retain their original IPv4 allocations. Cilium's documented
IPv6 annotation fallback supplies fixed per-node IPv6 ranges without replacing
nodes, changing IPAM mode, or changing the IPv4 Pod allocator:

| Node | IPv6 Pod range |
| --- | --- |
| w386 | `fd74:67a:1fcf:4200::/64` |
| talos-qlw-pbh | `fd74:67a:1fcf:4201::/64` |
| talos-d4h-k5m | `fd74:67a:1fcf:4202::/64` |

The `talos/dual-stack-node-*.yaml` patches persist these annotations in Talos
`machine.nodeAnnotations`. Apply the matching node patch together with
`talos/dual-stack-services.yaml` using a scoped, no-reboot Talos patch. The latter
adds the IPv6 Service range and selects both Infrastructure node address families.
Talos `cluster.network.podSubnets` deliberately stays IPv4: IPv6 per-node ranges
are assigned explicitly, not by kube-controller-manager. **New nodes need their
own unique IPv6 annotation before Cilium can initialize.**

Cilium values enable IPv6, `annotateK8sNode` and `k8s.requireIPv6PodCIDR`. The chart
also grants its agent the node-status annotation permission. Existing Pods keep
their IPv4 networking; newly created Pods receive both families. Only ingress is
converted to a dual-stack Service; IPv4 application backends remain supported.

## Exposure and security

MetalLB advertises both VIPs from the public-ingress pool. Traefik requests them
through `metallb.io/loadBalancerIPs` and `RequireDualStack`, with IPv4 first.
No host networking or additional edge proxy is used.

The separate `/home/shaman007/git/unifi-infra/public-ipv6-ingress.tf` permits only
this IPv6 /128 from WAN and untrusted Wi-Fi:

- TCP 25, 80, 443, 587, 993, 4190 and 25565.
- UDP 443 for HTTP/3.
- ICMPv6 for diagnostics and IPv6 control/error traffic.

These rules do not expose node APIs, other node addresses, or private Pod ranges.
Existing outbound IPv6 and IPv4 WAN port forwards are preserved. Private HTTP
routes still use their allowlists; Infrastructure's IPv6 /64 is trusted, while
Default LAN/Wi-Fi's IPv6 subnet is not. The shared guard also trusts the private
IPv6 Pod allocation envelope. WireGuard remains IPv4-only.

All public HTTPS routes on the shared listener are reachable by IPv6, whether or
not each hostname has an AAAA record. DNS is not an access control.

## Mail

Traefik now listens on TCP 25 and sends it to the existing Postfix backend with
PROXY v2. IPv6 uses no router 25-to-587 translation. The original IPv4 WAN forward
25-to-587 remains unchanged.

Only the proxy-facing Postfix `submission` smtpd has `-o inet_protocols=all`, so it
can accept IPv6 client metadata in PROXY headers. Global `inet_protocols = ipv4`
is preserved: outgoing SMTP retains its existing IPv4 identity and behavior.

## Verification

- PDF returned HTTPS 200 over IPv6 from two external Czech probes, with the
  hostname overridden and no AAAA record.
- Local forced IPv6 HTTP/2 and HTTP/3 returned 200.
- External TCP probes succeeded for 25, 587, 993, 4190 and 25565.
- From untrusted Wi-Fi, native IPv6 SMTP STARTTLS 25/587, IMAPS 993 and ManageSieve
  STARTTLS 4190 completed certificate-verified TLS 1.3 handshakes. No mail was sent.
- Minecraft returned its status response over IPv6.
- Headlamp returned 200 from wired Infrastructure IPv6 and 403 from Wi-Fi IPv6,
  including HTTP/3. Private node API access from Wi-Fi IPv6 remained blocked.
- IPv4 PDF and existing IPv4 mail handshakes were also checked after rollout.
- All 158 unit tests, runtime contracts and generated policy checks passed.
- All three nodes/Cilium agents, etcd membership and 63 attached Longhorn volumes
  remained healthy. Encrypted pre-change Talos/Kubernetes baselines and a verified
  independent etcd snapshot are in the workstation's private migration state.

Example without publishing DNS:

```sh
curl -6 --resolve 'pdf.andreybondarenko.com:443:[2a02:e98:c0:181e::210]' \
  https://pdf.andreybondarenko.com/
```

External HTTP/3 was not independently measured. Full mail delivery/authentication,
all application workflows and a full Talos cluster restore were not rehearsed.

## Rollback order

1. Disable the new IPv6 WAN/Wi-Fi policies in the separate network IaC. Remove any
   subsequently published AAAA records before withdrawing the IPv6 listener.
2. Return Traefik's Service to IPv4 SingleStack, preserving its original IPv4 VIP
   and NodePorts; remove only the IPv6 MetalLB allocation after it is unused.
3. Keep the native SMTP listener unless intentionally rolling it back. Existing
   IPv4 forwarding still targets 587, independently of the new port 25 listener.
4. Keep cluster dual-stack support unless a separate full rollback is required.
   Disabling Cilium IPv6 requires accounting for every Pod created since rollout;
   do not remove per-node allocations while dual-stack Pods still rely on them.

Changes are staged in Git, not committed or pushed by the assistant. Relevant
Argo applications are temporarily held until the matching revision is pushed and
verified. Resume only the migration holds, preserving unrelated existing holds.
