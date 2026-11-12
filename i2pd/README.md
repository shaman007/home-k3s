# Experimental IPv6 I2P client proxy

Deployed and runtime-tested on 2026-11-12. The Argo application stays manual.
The final Service/policy fixes are local and live; publish them before any Argo
sync. The published initial version does not contain the working configuration.
Upstream image is pinned by manifest digest, resolved with `skopeo inspect`.

- HTTP: `http://[2a02:e98:c0:181e::214]:4444`
- SOCKS5 with remote name resolution: `socks5h://[2a02:e98:c0:181e::214]:4447`
- Client allowlist: Infrastructure `2a02:e98:c0:181e::/64` only. Wi-Fi and
  WireGuard are not included. No public proxy, Ingress, NodePort or WAN rule.
- The address is proposed in a dedicated non-autoassigned MetalLB /128 pool.
  Repository and current Service inventory have no competing allocation; verify
  against LAN address ownership before rollout. Existing UDM policy permits only
  the shared ingress ::210, so no WAN opening is requested.
- Outbound source is the selected node's global IPv6 through existing Cilium
  masquerading, **not ::214**. The pod's internal IPv6 is a cluster ULA.
- Cilium still allocates an internal IPv4. This deployment isolates IPv4 traffic;
  it does not create an addressless-IPv4 network namespace. If absence of an IPv4
  assignment or a dedicated outbound /128 is required, do not deploy this design.

## Isolation and client behavior

`ipv4=false`, exact Pod IPv6 listener binding, an IPv6-only Service with no
allocated NodePorts, and namespace-wide Cilium IPv4 ingress/egress deny work
at separate layers. Explicit host/remote-node/kube-apiserver entity denies also
close Cilium's implicit host-ingress exception; CIDR denies alone do not cover
all node and pod identities. Cluster-pod IPv4 traffic is default-denied. Cilium
deny overrides additive allow policies. No host
network, host ports, privileges, capabilities or API token are used.

The Service uses `loadBalancerClass: metallb-l2`; the installed controller ignores
unclassified Services. `externalTrafficPolicy: Cluster` avoids the health-check
NodePort that Kubernetes allocates for `Local`, even with ordinary NodePorts
disabled. Cross-node IPv6 SNAT preserves the `reserved:world-ipv6` identity;
matching only the visible router /128 does not admit that traffic. The policy
therefore admits that exact reserved identity only to 4444/4447. The Service's
BPF `loadBalancerSourceRanges` map filters the **original client** before SNAT;
this is the client /64 access boundary for the VIP. Do not replace the identity
selector with dual-stack `world`, remove the Service source ranges, or expose
or route the Pod ULA directly outside the cluster. Direct Pod access from
external IPv6 identities does not have the Service's source-range filter.

Cluster DNS currently has only an IPv4 Service. This pod uses only the two
explicit Cloudflare IPv6 DNS resolvers, with no cluster search list. Resolving
an A record over IPv6 is allowed and does not constitute IPv4 traffic. Actual
IPv4 connection attempts, including reseed fallback, must be dropped.

Only outbound NTCP2 TCP is enabled. SSU2 is disabled, NTCP2 publication is
turned off, and no inbound transport port is exposed. Public IPv6 TCP is allowed
for variable peer ports and HTTPS reseeding, excluding the local Infrastructure
/64. Only the named resolvers have UDP/53 allowed. Verified reseeds require
IPv6-capable upstreams; an IPv4-only upstream fails closed.

There is no clearnet exit service, configured server tunnel or upstream outproxy.
HTTP/SOCKS serve I2P destinations only. `notransit=true`, `share=0` and
`floodfill=false` additionally disable participating transit and floodfill duties.
Transit forwarding inside I2P is distinct from an Internet exit.

One retained 1 GiB Longhorn PVC holds router identity and netDb. No claim pruning
or deletion is requested. Backups are not configured for this experimental data.
Bandwidth is limited to 256 KB/s; memory is capped at 512 MiB. The proxy listeners
are not authenticated; the IPv6 source allowlist is the access boundary.

Upstream references:
[configuration](https://docs.i2pd.website/en/latest/user-guide/configuration/),
[container source](https://github.com/PurpleI2P/i2pd/tree/openssl/contrib/docker).

## Rollout and acceptance

Publish through the owner's permitted Git workflow. Reconcile namespace/project
and MetalLB pool/advertisement before manually syncing the `i2pd` Application.
The policy has an earlier sync wave than the workload. Keep automatic sync disabled. Runtime acceptance below passed; publish the final
Service/policy fixes before performing a manual sync. Schema validation and readiness
only establish configuration/listener health, not I2P tunnel readiness or policy
enforcement. Historical restored Cilium endpoints have failed enforcement, so
policy existence alone is insufficient evidence.

Read-only inventory:

```sh
kubectl get pods,svc,pvc,ciliumnetworkpolicies,ciliumendpoints -n i2pd -o wide
kubectl logs -n i2pd deployment/i2pd --tail=100
kubectl exec -n i2pd deployment/i2pd -- cat /proc/net/tcp /proc/net/tcp6 /etc/resolv.conf
```

Acceptance must cover:

1. Cilium policy validity and realized ingress **and** egress enforcement for the
   actual endpoint on its node. Verify IPv4 deny in the realized policy/BPF rules,
   not just the Kubernetes object. Correlate active negative tests with Hubble
   policy-drop observations; distinguish a network-policy drop from no route.
2. Only the exact Pod IPv6 listens on 4444 and 4447. No IPv4 listening sockets.
   Service and EndpointSlice have only IPv6 proxy endpoints, no IPv4 VIP/NodePort.
3. From an allowlisted IPv6 LAN client, bootstrap builds working I2P tunnels and
   an actual known `.i2p` or `.b32.i2p` destination returns its expected content:

   ```sh
   curl --noproxy '' --max-time 180 --proxy 'http://[2a02:e98:c0:181e::214]:4444' http://stats.i2p/
   curl --noproxy '' --max-time 180 --proxy 'socks5h://[2a02:e98:c0:181e::214]:4447' http://reg.i2p/
   ```

4. Try each proxy port on the **Pod IPv4 and each node IPv4** from a routed LAN
   client and an existing peer pod. All must fail. A client cannot address an IPv6
   literal over IPv4; that is not an IPv4 isolation test.
5. From inside the workload network namespace, attempt a TCP connection to a
   known-working literal public IPv4 and a DNS query to an IPv4 resolver. Both
   must produce policy drops. Include a host/node IPv4 destination to detect
   host-identity exemptions. Use available diagnostic tools; do not install or
   start privileged containers as part of a supposedly read-only check.
6. Observe DNS and reseed during initial bootstrap and steady-state peer traffic:
   no successful workload IPv4 flows, and global IPv6 peer/reseed connections
   originate in our /64 after masquerading. IPv4 image pulls, storage and Cilium
   overlay traffic belong to cluster infrastructure, not the i2pd process.
7. Untrusted IPv6 Wi-Fi and external WAN clients cannot access 4444/4447. Verify
   using actual clients at those locations; LAN success proves no WAN isolation.
8. Plain Internet hostnames and literals through HTTP and SOCKS cannot use a
   clearnet outproxy; no transit tunnels appear. Check both HTTP and CONNECT/SOCKS.

Stop the experiment if any IPv4 flow succeeds; do not relax the deny to repair
bootstrap. Retain the PVC when disabling/removing the workload. Any live sync,
scale-down or network/router change needs its own applicable authorization.

## Verified live outcome — 2026-11-12

- Pod running/ready on talos-d4h-k5m. IPv6-only Service/EndpointSlice and two
  exact Pod IPv6 listeners; `/proc/net/tcp` has no IPv4 sockets. No proxy NodePorts
  or health-check NodePort remain. Node IPv4 addresses do not answer on
  4444/4447 or the retired health-check port.
- HTTP proxy: `stats.i2p` returned 200 and the expected statistics landing page.
  SOCKS5 with remote resolution: `reg.i2p` returned 200 and the Registry page
  (19,351 bytes). `stats.i2p` rejected the SOCKS request with its upstream 403
  inproxy check; that response was not treated as a successful content check.
- External trace observed source `2a02:e98:c0:181e:32c5:99ff:fea9:5f84`, in our
  Infrastructure /64. The trace was a diagnostic request using the existing
  BusyBox TLS client's no-check-certificate option because its CA trust failed;
  it was not a certificate validation test. Live TCP sockets show IPv6 I2P peers.
- IPv6 DNS succeeded. Forced IPv4 public TCP, IPv4 DNS/UDP, own-node/API and
  cluster-pod connections failed with Cilium policy-drop evidence. IPv4-mapped
  IPv6 (`::ffff:1.1.1.1`) also produced IPv4 deny events.
- Incoming IPv4 to both proxy ports from the same node, another node and an
  ordinary temporary pod failed with destination Cilium policy-drop evidence.
  The ordinary test pod reached public IPv4 successfully as a positive control.
  The temporary pod was removed after testing.
- Wi-Fi IPv6 (untrusted /64) could not reach the proxy. The allowed /64 is present
  for both proxy frontends in Cilium's BPF source-range maps. No independent WAN
  client was available; WAN rejection was not separately exercised.
- HTTP clearnet request returned 502 with no outproxy; SOCKS rejected a literal
  public IPv4 destination. No server tunnels, outproxy, transit or floodfill are
  configured. The web console remains disabled.
- Cilium reports realized policy enforcement `both`, valid policy and explicit
  IPv4/node denies. These tests establish observed enforcement on this rollout;
  recheck it after changes or endpoint restore, rather than relying on object
  existence. Internal Pod IPv4 allocation still exists by cluster design.
- Argo reports Healthy/OutOfSync: resources were created directly under explicit
  user authorization and the final Service/policy corrections are unpublished.
  Do not sync the old published manifests over this working deployment.
