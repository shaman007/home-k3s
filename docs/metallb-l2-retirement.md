# Staged retirement of unused FRR

Reviewed 2026-11-04 against MetalLB chart 0.16.1. The cluster has no BGPPeers,
BGPAdvertisements, FRRConfigurations or FRRK8sConfigurations. Two IPAddressPools
and two L2Advertisements serve three LoadBalancer Services, all class
`metallb-l2`. FRR's node/session status objects are not routing configuration.

## Stage 1: publish the L2-only backend configuration

`argocd/application-metallb.yaml` disables both bundled and external frr-k8s and
legacy in-speaker FRR. Automatic pruning is explicitly false. This switches the
controller and speaker to the native backend; it does not disable the L2
announcer. The pinned upstream source selects native when `METALLB_BGP_TYPE`
is absent and only watches FRR resources when that backend is selected:

- https://github.com/metallb/metallb/blob/v0.16.1/speaker/main.go
- https://github.com/metallb/metallb/blob/v0.16.1/charts/metallb/templates/speaker.yaml

The chart review verifies that exactly three retained resources change: only the
BGP environment entry disappears from controller/speaker, and the speaker loses
its FRRConfiguration RBAC rule. Images, probes, capabilities, host networking,
memberlist, load balancer class, metrics, and seccomp stay unchanged. Pool and
L2Advertisement manifests stay unchanged.

Run this read-only review with an unpacked copy of the pinned chart:

```sh
python3 tools/security/review-metallb-l2.py --chart /path/to/metallb --live
```

After publishing, verify the controller is available, all three speakers are
updated/ready, and their backend is native. Compare all Service ingress addresses
with this baseline:

| Service | Addresses |
| --- | --- |
| traefik/traefik | 192.168.30.210, 2a02:e98:c0:181e::210 |
| traefik/traefik-private | 192.168.30.211 |
| backup-rsync/backup-rsync | 192.168.30.213 |

Check public and private ingress HTTP/TLS from the LAN and the backup SSH banner.
Also verify IPv6 ingress from an IPv6-capable LAN client; readiness and assigned
VIPs alone do not prove ARP/NDP delivery. Confirm ServiceL2Status still identifies
announcing speakers and inspect fresh speaker logs for errors. Do not create test
mail, modify backup data, or alter GPU/Plex discovery endpoints.

Argo may show OutOfSync with `requiresPruning` resources during this transition.
That is expected; do not perform a broad sync-with-prune to clear it. FRR still
runs and its six root/capability findings remain visible until stage 2.

## Stage 2: approve a narrow retirement after L2 verification

The exact chart-derived inventory is
[`metallb-frr-retirement-inventory.json`](../tools/security/metallb-frr-retirement-inventory.json).
It lists 13 operational resources for eventual retirement and four CRDs to retain.
It contains resource identities only, including the certificate Secret name;
never export its value.

Before stopping FRR, publish a follow-up that removes the FRR DaemonSet and
statuscleaner entries from `infra-guards/catalog.json`, regenerates the guard
resources, updates target-inventory tests, and verifies the new backfill hook.
The current hook intentionally requires both workloads to exist; deleting them
first would break subsequent reconciliations. Keep their guards during stage 1
because the old FRR Pods are still live. Review any FRR monitoring targets at the
same time. Do not remove unrelated GPU or Longhorn targets.

Recheck that BGP/FRR configurations are still absent. Obtain explicit approval
for deletion of only the 13 `retire` identities. Remove the FRR validating webhook
before its backing Service, then stop the DaemonSet and statuscleaner, and remove
the remaining exact-name operational resources. Retain all four CRDs and their
status objects; do not delete namespaces, MetalLB controller/speaker resources,
memberlist Secret, pools, L2Advertisements or LoadBalancer Services. Do not enable
broad automated pruning. Verify ingress, backup SSH, speaker health and Kyverno
again. Retirement should remove six current Fail results, leaving nine if no
other workloads change.

No live deletion is authorized or performed by this preparation. The review tool
only calls `helm template` and optional `kubectl get`.

## Rollback

Before retirement, revert the L2-only values to `frrk8s.enabled: true` and publish;
FRR remains live, so controller/speaker can reconnect without rebuilding it.
After retirement, restore the prior chart values and the reviewed FRR guard
catalog entries together, let Argo recreate FRR, then verify all routing helpers
before relying on that backend. Preserve the retained CRDs throughout.

## Other remaining findings

MetalLB speakers still need NET_RAW for L2 ARP/NDP. Their rootless conversion needs
separate compatibility evidence, especially the root-owned mode-0400 exclude-L2
ConfigMap mount. Do not drop NET_RAW or set a non-root UID blindly.

OpenBao's template already drops all capabilities, but its three old Pods use an
OnDelete StatefulSet. It uses Shamir sealing without auto-unseal. Do not replace
those Pods until an operator can unseal replacements; never send unseal keys in
chat. These three findings remain visible.
