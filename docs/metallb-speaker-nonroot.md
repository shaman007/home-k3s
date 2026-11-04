# MetalLB speaker non-root trial and rollback

## Production outcome: incompatible, rolled back

The published trial (13043b50) reached UID/GID 1000 on all three nodes, but the
speakers repeatedly failed creating ARP sockets with `operation not permitted`.
Pods remained Ready despite this failure. IPv6 ingress failed; IPv4 ingress and
SSH still responding could reflect cached neighbour entries and were not proof
of healthy L2 announcement. The exact production capability/runtime cause is
not established. Do not treat the Podman probe as proof of production CRI or
host-network compatibility.

The user authorized immediate restoration of the prior root identity. All four
new identity/group fields were removed from the live DaemonSet; NET_RAW, drop
ALL, no escalation, read-only root, RuntimeDefault and one-at-a-time rollout were
retained. The Git rollback is prepared. MetalLB reconciliation is temporarily
paused with `argocd.argoproj.io/skip-reconcile=true` until that rollback is pushed.
The parent Application restored automated.enabled=true; the skip annotation is
the effective hold. The first live rollback raced Argo before the hold took effect
and was repeated after confirming the annotation. After Git contains the rollback, remove the pause,
restore automated.enabled=true, and verify reconciliation and IPv4/IPv6/SSH.

The proposed NET_RAW audit exception was withdrawn. Speaker root/capability
findings must remain visible while production requirements are investigated.
No OpenBao restart or broader privilege changes are part of this recovery.

The following records the original isolated evidence and trial plan for diagnosis;
it is superseded by the production failure above.

Reviewed 2026-11-04, chart 0.16.1 and speaker image repository
`quay.io/metallb/speaker`. The local probe image includes the deployed digest
`sha256:16561e96531e1852d5c229ad7fae6e994dcfa983ff7f4de6b6208b34a4e2ddbc`.

## Required behavior and privileges

All three speakers use host networking for IPv4 ARP and IPv6 NDP. Keep NET_RAW.
The pinned implementation opens ARP packet sockets and IPv6 NDP sockets, joins
solicited-node multicast groups and writes advertisements; it does not need a root
UID for those operations when NET_RAW is effective. Existing memberlist TCP/UDP
7946 and protected metrics HTTPS 9120 are high ports. Keep the existing drop ALL,
NET_RAW-only capability set, no escalation, read-only root and RuntimeDefault.

Sources reviewed:

- https://github.com/metallb/metallb/blob/v0.16.1/internal/layer2/arp.go
- https://github.com/metallb/metallb/blob/v0.16.1/internal/layer2/ndp.go
- https://github.com/metallb/metallb/blob/v0.16.1/internal/layer2/announcer.go
- https://github.com/kubernetes/kubernetes/blob/v1.37.1/pkg/volume/volume_linux.go

The exclude-L2 ConfigMap is root-owned with defaultMode 0400. A plain non-root UID
would fail reading it. `fsGroup: 1000` makes the projected files group-owned and
adds the read-only group mask (0440); the source ConfigMap mode remains 0400.
Memberlist Secret/config and the service-account projection also remain readable.
No credential values were inspected. The chart mounts only Secret/ConfigMap
volumes; there are no hostPath or persistent volumes to chown. An added volume or
new chart version requires renewed review.

## Prepared change and compatibility evidence

The speaker Pod gains runAsNonRoot true, UID/GID 1000 and fsGroup 1000. Its rolling
strategy explicitly allows one unavailable Pod at a time. No controller, image,
container command/args, capability, networking, probe, port, mount, Secret,
ConfigMap, LoadBalancer Service, pool or advertisement changes are introduced.
An exact before/after Helm comparison verified these boundaries.

```sh
python3 tools/security/test-metallb-speaker-runtime.py
python3 tools/security/review-metallb-l2.py --chart /path/to/metallb --live
```

The disposable runtime probe creates a veth pair inside a network=none namespace.
Only the setup container has NET_ADMIN; the tested process is UID/GID 1000 with
NET_RAW only, NoNewPrivs=1 and seccomp mode 2 under Podman's default profile.
The cluster runtime's RuntimeDefault profile still needs post-rollout verification. It verifies:

- Group-owned 0440 configuration is readable; root-only 0400 is rejected.
- ARP request/reply frames and IPv6 neighbor advertisements pass between fixture
  endpoints; IPv6 solicited-node group join/leave succeeds.
- High-port listeners bind, while changing an interface fails without NET_ADMIN.
- The pinned real speaker starts non-root on a read-only root, reads the synthetic
  group-owned exclude-L2 file and creates its own ARP and NDP responders. The
  root-only version produces the expected permission error.
- Removing NET_RAW prevents raw ARP socket creation.

The speaker's fixture Kubernetes discovery is deliberately stalled on loopback;
there are no production API credentials or live VIPs. This tests its real pre-API
initialization, not full informer/cache reconciliation or its response for a
LoadBalancer VIP. Those require the post-push checks below. All fixture containers
and files are cleaned up. No host interface or production workload is modified.

## Rollout verification after publication

Before this change, IPv4/IPv6 public ingress, private ingress and backup SSH were
verified following FRR retirement. Check them again after each speaker update
when possible, and after all three Pods settle. Stop further changes on failure;
readiness alone does not prove ARP/NDP behavior.

1. Verify Argo MetalLB is Healthy, the speaker DaemonSet is updated/ready 3/3 and
   fresh Pods have UID/GID 1000, fsGroup 1000, NET_RAW only, NNP and seccomp mode 2.
2. Follow symlinks with `stat -L` to verify `/etc/metallb/excludel2.yaml` has group
   1000/read permission. Check token/config readability without printing contents.
3. Check fresh logs for permission failures, ARP/NDP creation failures, memberlist
   errors and configuration reconciliation failures; verify L2 announcing nodes.
4. Confirm VIPs stay .210 plus `2a02:e98:c0:181e::210` for public Traefik, .211 for
   private Traefik and .213 for backup SSH. Request public HTTPS over each IP
   family from the LAN, private HTTPS, and read the backup OpenSSH banner.
5. Check current-Pod Kyverno reports. The three speaker non-root findings should
   clear. Their three capability findings remain because strict audit permits
   only NET_BIND_SERVICE, while L2 needs NET_RAW. Do not drop NET_RAW or add a
   broader audit exception just to hide those findings. A narrowly guarded
   capability exception can be reviewed after live non-root operation is proven.

Expected remaining Fail results after a successful rollout: six across six Pods
(three speaker NET_RAW capability findings and three old OpenBao Pod capability
findings). No OpenBao replacement is included; it requires an unseal-ready operator.

Rollback: remove the four new speaker Pod identity/group fields from chart values
and publish. Preserve NET_RAW, L2 mode, VIPs and the one-at-a-time strategy.
