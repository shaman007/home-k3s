# Harbor internal ingress: BGP preparation and rollback

Status: internal Harbor ingress deployed on 2026-11-12; see
[EXECUTION.md](EXECUTION.md). UDM permits `.212/32`, MetalLB advertises it, and
monitoring requires all four service routes. DNS remains unchanged. The existing
public Harbor ingress and its middleware remain in place. The three GitOps
owners `harbor-custom`, `metallb-config`, `unifi-exporter` are temporarily paused
with explicit approval until these sources are published. Do not resume against
old Git. Default Wi-Fi cannot reach `.212`; resolve access policy before any
DNS change for that network. `unifi-infra` is not yet a Git repository.

## Exact applied UDM change

Owning source: `/home/shaman007/git/unifi-infra/bgp-kubernetes.conf`, read by the
existing `unifi_bgp.kubernetes` OpenTofu singleton. Its mirror is
[`docs/bgp-trial/udm-services.conf`](../../bgp-trial/udm-services.conf).

```diff
-  neighbor K8S-TRIAL maximum-prefix 3
+  neighbor K8S-TRIAL maximum-prefix 4
@@
 ip prefix-list K8S-TRIAL-ONLY seq 30 permit 192.168.30.211/32
+ip prefix-list K8S-TRIAL-ONLY seq 35 permit 192.168.30.212/32
 ip prefix-list K8S-TRIAL-ONLY seq 40 permit 192.168.30.213/32
```

The limit is four accepted prefixes per peer, not twelve paths across three
peers. Existing ASNs, neighbors, timers, route maps, three permits and outbound
deny are preserved. No subnet-wide allowance or new route export is introduced.
The existing `prevent_destroy` on the BGP singleton remains in place.

[Reviewable patch](udm-bgp.patch) and [original payload](udm-before.conf) are
retained. Original payload SHA-256:
`ea4be2a6c58532a34476d8515754549748dfe8c4b7fe105774a5b85393400dba`.
Before editing, a refreshed targeted plan returned exit 0 / no changes, proving
the controller's stored BGP object matched that original payload. This does not
prove live FRR session or forwarding-table state; those require their own checks.

## VIP check and limits of the evidence

Candidate `192.168.30.212`:

- Not allocated to any current Kubernetes LoadBalancer Service.
- Outside the existing MetalLB pools (`.210`, `.211`, `.213`, public IPv6 VIP).
- Outside the configured infrastructure DHCP range `.50` through `.99`.
- No occurrence in the inspected current/backup local OpenTofu state, and no
  configured reservation found in the reviewed IaC sources. State contents and
  credentials were not printed or copied.
- Five duplicate-address ARP probes on `enp6s0` / infrastructure VLAN returned
  zero replies. No address was assigned or reserved by the probe.

This establishes no observed conflict, not permanent ownership: an offline or
nonresponding device may still have a manual address. SSH to UDM failed at
hardware-key/agent authentication, so its current lease/client/ARP inventory was
not read. Before reserving the VIP, restore authenticated router access or
inspect the controller UI, repeat the probes and check live reservations/leases.
Do not change host SSH configuration as part of this networking preparation.

## Reproducible plan and validation

The existing credential-safe helper now supports a fixed `--bgp-only` scope:

```sh
cd /home/shaman007/git/unifi-infra
tofu validate -no-color
python3 tools/plan.py --from-cluster --bgp-only
```

It runs `tofu plan -target=unifi_bgp.kubernetes`, saves no plan and applies
nothing. Cluster credentials remain in process memory and are redacted from
output. Normal environment/prompt authentication remains available without
`--from-cluster`. Expected exit is **2** (reviewable change), with:

```text
unifi_bgp.kubernetes will be updated in-place
Plan: 0 to add, 1 to change, 0 to destroy.
```

Accept only the two FRR changes shown above. A full refreshed plan before these
edits had unrelated drift (17 additions / 8 updates) and 14 provider errors
`Missing Resource Identity After Read`; it is incomplete and must NOT be used
for a broad apply. Do not repair imports, camera/WLAN/WAN settings or Terraform
state as part of this BGP change. A targeted plan is intentionally incomplete
for the whole estate; it establishes only the BGP update's scope.

Tests now require all four advertised routes and keep the new VIP confined to
its dedicated, non-auto-assigned pool. The original three-route payload remains
available solely as rollback evidence.

## Staged deployment and remaining gates

1. **Before any write:** repeat VIP/controller checks; obtain a current copy of
   the stored AND effective UDM BGP configuration, three established peer states,
   accepted prefixes/next hops, zero exports and permitted routed/L2 service
   baselines. Keep out-of-band router access available. Capture current DNS
   answers and TTLs. Abort on an existing degraded peer or unexplained route.
2. **UDM only:** after scoped authorization, regenerate and review the targeted
   BGP plan immediately before applying only this singleton update. Full FRR
   payload replacement may reconverge sessions; do not promise preservation of
   existing TCP sessions. Verify all three peers Established, the original three
   routes/next hops and service probes preserved, zero exports, and no prefix
   limit events. `.212` should remain absent from BGP while nothing advertises it.
   Stop and restore the original payload if these checks fail.
3. **Harbor infrastructure:** prepare/publish the minimal internal ingress, its
   dedicated class, explicit `.212` pool and narrowly scoped BGP/L2 advertisement
   through their owning GitOps applications. No plugins, GeoIP download, OIDC
   mount or persistent volume in this controller; Harbor's data remains on its
   existing storage. Add only the intended source access, keeping existing
   public ingress/DNS/WAN forwarding and Harbor external URL unchanged. Include
   the expected fourth live route in monitoring at this phase, not in step 2.
4. **Before DNS:** require ready ingress endpoints, exactly `.212/32` learned at
   UDM with endpoint-consistent next hops, no unexpected prefixes and no limit
   errors. Test both same-VLAN and permitted routed access. With hostname/SNI
   preserved, validate TLS, anonymous `/v2/` rejection/auth challenge, token
   issuance and a real authenticated private-image pull. Verify token realm and
   blob redirects retain the intended Harbor hostname. A plain HTTP 200 is not
   sufficient. Do not test by deleting cached production images.
5. **Split DNS last:** publish the internal A answer for
   `harbor.andreybondarenko.com` only for the intended node/LAN resolvers. Talos
   HOST/containerd resolution matters; CoreDNS alone is insufficient. Suppress
   public AAAA in this split view until an internal IPv6 path is ready. Verify
   node, pod and LAN resolution plus real image pulls, while external DNS and
   public requests retain the old route. Keep public HTTP-01 certificate renewal
   on its existing public Traefik. `harbor-tls` must remain valid.

## Rollback order

For the UDM-only stage, before `.212` exists, verify each peer has at most the
original three accepted prefixes, restore `udm-before.conf` through the same
reviewed BGP singleton operation and recheck all original services/peers.

If Harbor has already been advertised or DNS switched:

1. Restore the previous split-DNS A/AAAA answers and account for resolver caches.
   Confirm node/LAN requests can use the still-existing old public route. Keep
   the new ingress available while DNS caches drain.
2. Pause ONLY the GitOps owner(s) that would recreate the new `.212` advertisement,
   preserving original pause/automation settings. Withdraw only the new BGP
   advertisement after clients have a working old path; confirm `.212/32` is no
   longer learned from any peer and required-route monitoring returns to the
   three-route inventory. If routing is actively broken, restore the known-good
   client path first and stop rollout work.
3. Remove the `.212` acceptance entry. Reduce `maximum-prefix` back to **3 only
   after every peer has at most three accepted prefixes**. Never lower the limit
   while a fourth accepted prefix can still be advertised. Restore the exact
   original payload and reverify zero exports, peers, old routes and service probes.
4. Retire only the new internal ingress/VIP resources once unused, with scoped
   authorization and GitOps source changes in sync. Preserve all existing pools,
   L2 advertisements, BGP peers/FRR infrastructure, Harbor PVCs, registry data and
   certificate material. Resume paused owners only at a revision matching the
   intended rollback state.

Do not follow the older migration's broad `routed-services` withdrawal for this
one-prefix rollback: that would also withdraw the three existing services.
