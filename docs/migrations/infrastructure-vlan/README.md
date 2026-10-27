# Infrastructure VLAN migration

Prepared 2026-10-26; migration started 2026-10-27. Network IaC is in
`/home/shaman007/git/unifi-infra`, outside this repository.

## Current checkpoint — 2026-10-27

The three Talos nodes have moved to VLAN 30 using DHCP reservations and SLAAC:
`talos-qlw-pbh` `.30.100`, `w386` `.30.209`, and `talos-d4h-k5m` `.30.242`.
The canonical API `api.k8s.my.lan` now points to `.30.100`; ingress uses `.30.210`
and backup-rsync uses `.30.213`. Existing etcd member identities were preserved.
Home Assistant remains on its old LAN addresses; its migration is deferred by the user.

- Updated DNS records and port forwards to the new targets. The separate UniFi
  OpenTofu configuration adopted the existing reservations and switch ports; its
  final plan showed no changes. Preserved the full switch port-override array,
  including unmanaged false/empty flags. Disabled the obsolete old-node transition
  allowance. IDS/IPS remains disabled.
- Allowed Infrastructure TCP/443 to its own ingress VIP for gateway hairpin traffic.
  Public-hostname Harbor HTTPS from VLAN 30 returned 200. Application image pulls
  recovered. This does not establish independent external reachability.
- Added Infrastructure to both the shared internal ingress guard and Headlamp's
  separate LAN guard. Both Argo CD and Headlamp returned 200 from `.30.79`.
- Restored recorded replica counts, scheduled jobs and migration reconciliation
  holds. The pre-existing `karakeep` and `mempalace` Argo holds remain. Removed all
  temporary migration NetworkPolicies after checking their permanent replacements,
  and restored original Harbor/Traefik workload placement.
- Post-migration etcd backup `home-k8s-2026-10-27T11:32:34Z.snap.zst.age` was
  downloaded to the workstation, decrypted, integrity-checked, and restored using
  isolated etcdutl in tmpfs. Snapshot revision: `123976744`. This remains an isolated
  snapshot restore, not a full Talos-cluster recovery rehearsal.
- Loki returned historical canary logs from before maintenance and fresh entries
  after recovery. Retain PVC policy and discovery of not-ready members are now
  configured. These checks do not prove recovery of the deleted local WAL.
- Repeated host DNS and forced outbound IPv6 HTTPS checks after reconciliation: all
  three nodes transferred 1 MiB with HTTP 200 from their Infrastructure IPv6 addresses.
- Repository validation passed: 155 unit tests, runtime contracts and generated
  NetworkPolicy bundle checks. Ingress guard tests now require the new subnet.
- Cilium completed its reconciliation rollout with 3/3 agents and Envoy pods ready.
  Longhorn recovery included read-only mounts and automatic detach/reattach of the
  Prometheus and Harbor registry volumes; monitor their recovery and replica rebuilds.

The sections below record preparation and earlier execution stages. Their old
addresses, temporary rules and incomplete-stage statements are historical.

## Execution checkpoint — 2026-10-27

Completed:

- Created Infrastructure VLAN 30 with `192.168.30.1/24`, DHCP `.50`–`.99`,
  static IPv6 `2a02:e98:c0:181e::1/64`, SLAAC and router advertisements.
- Attached it to a dedicated Infrastructure zone. Controller defaults allow
  IPv4/IPv6 outbound Internet and return traffic, block unsolicited WAN ingress,
  and block new connections to/from other private zones. Added explicit trusted
  Default-LAN and WireGuard ingress with return rules, plus the temporary
  new-node-to-old-node IPv4 transition allowance. IDS/IPS remains disabled.
- Applied the stable canonical API endpoint `https://api.k8s.my.lan:6443` and SAN
  additions to all three control planes without rebooting. Verified the DNS
  certificate and `/readyz` individually on `.209`, `.242`, then `.100`.
  Updated the workstation's existing kubeconfig and verified its normal API access.
- Downloaded and decrypted a fresh scheduled etcd snapshot from 2026-10-27
  08:17 UTC (09:17 Europe/Prague), validated revision 123835344 and restored it
  in isolated tmpfs. This is not a full Talos-cluster recovery rehearsal.
- Saved encrypted Talos effective config, Talos/kube client config and UniFi
  network exports under
  `/home/shaman007/.local/state/infrastructure-vlan-migration/20261027T082726Z`.

Desktop validation and remaining gates (host renumbering has not started):

- End-host outbound checks now pass on the desktop's real switch port 6:
  DHCP `192.168.30.79/24`, SLAAC
  `2a02:e98:c0:181e:af5b:89f3:6c17:d57f/64`, DNS over IPv4 and IPv6,
  forced IPv6 HTTPS and a 1 MiB transfer (HTTP 200, approximately 0.16 seconds).
  IPv4 HTTPS also passed in approximately 24 ms. This supersedes the failed
  in-cluster diagnostic probes below; it does not waive per-node/HA checks.
- Verified new VLAN-to-old LAN blocking to a known listening Talos API port
  over IPv4 and IPv6: both connected from trusted Wi-Fi and timed out when
  bound to new-VLAN Ethernet. External unsolicited IPv6 ingress still needs
  an independent external probe before final sign-off.
- Confirm the owner's independent offline age-key copy and local console access.
- Complete the disposable Talos recovery rehearsal, transition NetworkPolicy
  expansions and ingress placement/cutover preparation before the first node move.
- Desktop test path is now available on USW-16-PoE port 6. At the owner's request
  Ethernet remains on VLAN 30 with a retained NetworkManager profile named
  `Infrastructure Ethernet (temporary)` using diagnostic MAC `02:30:00:00:00:61`.
  Wi-Fi remains preferred for Internet/management (route metric 600 versus 10000).
  The original `Wired connection 1` profile is preserved. Its original MAC's old
  LAN reservation and unrelated public forwarding have not been changed. Services
  pinned to the old desktop `.1.141` address will need separate review while this
  interface stays on the new VLAN.
  Roll back by restoring only port 6's former native network, then activating
  the original Ethernet profile. Encrypted prior port state is in
  `/home/shaman007/.local/state/infrastructure-vlan-migration/test-port6.json.age`.

All production node/HA addresses and their access-port assignments, MetalLB VIPs, public
port forwards and ingress DNS targets remain on their original network. Current
Pod/Service networks remain IPv4-only. HA migration has not started.

## Rolling migration checkpoint — 2026-10-27 10:27 UTC

The owner confirmed console access and completed PVC backups, and authorized changes
with predictable service downtime. A fresh encrypted etcd snapshot was downloaded at
10:08 UTC, revision 123887914, SHA256
`443273a30ea9ecda7f386a021455776488b34bb502270e515928a47aaf3b676d`.
Decryption, integrity inspection and an isolated etcdutl restore passed.

Expanded 18 node-address NetworkPolicy manifests and their common generator to allow
both node subnets. Installed equivalent temporary supplemental live policies labeled
`migration=infrastructure-vlan30`, preserving the original policies and their Argo
ownership. Remove these supplements after the changed manifests are pushed and synced.

Traefik reconciliation is temporarily paused (`skip-reconcile=true`). Its Deployment
has a temporary `kubernetes.io/hostname=talos-qlw-pbh` nodeSelector to retain the old
VIP during migration. Removed that node's persistent Talos load-balancer exclusion
using `talos-enable-ingress.patch.yaml`; a Kubernetes label removal alone was restored
by Talos. Verified the relocated endpoint, MetalLB L2 advertisement and HTTPS 200.

Requested a graceful reboot of w386 and changed its reservation/port 16 to VLAN 30.
It continued answering ARP on its old address while the new address remained absent.
Restored only w386's original reservation and native port to preserve its shutdown
network path. The other two etcd members remained healthy with matching indexes.
w386 recovered at its original address; Talos services, Kubernetes Ready and three-member
etcd synchronization were verified. Its restarted OpenBao member was unsealed using
protected workstation recovery material. Longhorn replicas are rebuilding; wait for
healthy storage before further moves. The owner reports that the console is unreliable.
Validate a timed, automatically reversible explicit network configuration before
retrying; do not assume shutdown has finished when a reboot request returns. Encrypted per-node rollback
state is outside Git under `~/.local/state/infrastructure-vlan-migration/`.

## Application maintenance shutdown — owner authorized

Recorded original replica counts, CronJob suspension and Argo reconciliation flags in
`application-replicas.json`. Paused all 84 Argo applications, suspended 14 application
CronJobs (preserving those already suspended), and requested zero replicas for 87
application Deployments/StatefulSets (including pre-existing zero counts). Retained
platform controllers in the listed namespaces. No active application Jobs required
suspension. Application services are intentionally unavailable during this window.
Restore original counts in dependency order after network verification: OpenBao and
unseal, SeaweedFS, Harbor, then databases and applications. Restore scheduling and
reconciliation annotations only after live configuration and Git desired state agree.

The timed static-network test confirmed automatic rollback, but exposed that DHCP
also provided w386's hostname. The temporary generated alias `talos-oa1-nj3` was
cordoned and removed with its orphaned system pods; no application workloads or
Longhorn disks belonged to it. Fixed the existing hostname `w386.k8s.my.lan` in Talos
without rebooting; verified effective hostname and the original three etcd members.
Pin each node's current hostname before removing DHCP. Do not repeat the hostname
change or use generated node identities during renumbering.

## Target addresses

VLAN 30, gateway `192.168.30.1/24`; DHCP dynamic range `.50`–`.99`.
**Mandatory requirement: working outbound IPv6. An IPv4-only Infrastructure
VLAN is not an acceptable migration outcome.** Use dual-stack host networking:
IPv4 `192.168.30.0/24` plus IPv6 `2a02:e98:c0:181e::/64`, with gateway
`2a02:e98:c0:181e::1`, SLAAC and router advertisements. This /64 is within
Faster's statically routed `2a02:e98:c0:1800::/56`, confirmed in the ISP email
“Re: IPv4 adresa Francouzska 95” dated 17 June 2021. Verify upstream routing
still works before moving production hosts; no DHCPv6-PD or WAN change is assumed.

IPv6 acceptance is a hard stop gate for the first node move, each subsequent
node move, HA cutover and final sign-off:

- From a test client on VLAN 30, then from every migrated node and HA, verify a
  global IPv6 address in the new /64, a usable default route, working DNS and an
  IPv6-forced HTTPS request to a known externally reachable IPv6 destination.
  Record destination, source address and result. Test DNS resolution separately
  from IPv6 connectivity so IPv4 fallback cannot hide a broken IPv6 path.
- Permit outbound IPv6 and established/related replies. Allow necessary ICMPv6
  for neighbor/router discovery and path-MTU discovery; do not block ICMPv6
  wholesale. Test larger transfers and connections beyond only the gateway.
- Enforce equivalent IPv4/IPv6 inter-VLAN isolation and block unsolicited inbound
  WAN IPv6. Verify these with external and cross-VLAN probes, not only rule review.
- Scope confirmed by the owner on 2026-10-27: outbound IPv6 is required for
  nodes and Home Assistant only. Keep Pods and Services IPv4-only, with their
  current CIDRs and Cilium address-family settings. No Pod IPv6 egress or
  dual-stack CNI migration is included.
- Do not accept disabling IPv6 as a workaround for a failed cutover; stop and
  repair the path or roll back the affected host.

Public IPv6 ingress and public AAAA records are optional and outside this
requirement. Existing IPv4 ingress must keep working.
Keep Kubernetes Pod `10.42.0.0/16` and Service `10.43.0.0/16` networks unchanged.

| Device/service | Current | Target | Switch port |
|---|---|---|---|
| talos-qlw-pbh / canonical API node | 192.168.1.100 | 192.168.30.100 | 13 |
| w386 | 192.168.1.209 | 192.168.30.209 | 16 |
| talos-d4h-k5m / GPU and local data | 192.168.1.242 | 192.168.30.242 | 9 |
| Traefik MetalLB VIP | 192.168.1.210 | 192.168.30.210 | L2 announcement |
| backup-rsync MetalLB VIP | 192.168.1.213 | 192.168.30.213 | L2 announcement |
| Home Assistant Ethernet | 192.168.1.246 | 192.168.30.246 | 3 |
| Home Assistant Wi-Fi | 192.168.1.247 | retire after Ethernet verified | Wi-Fi |

Node MACs, respectively: `a0:ad:9f:5e:33:76`, `cc:28:aa:47:07:15`,
`30:c5:99:a9:5f:84`. HA Ethernet MAC: `e4:5f:01:bc:d6:fb`.
Reserve these target addresses before changing access ports. Exclude VIPs from DHCP.
Do not alter switch/AP management networks, camera VLAN 20, or WAN Tap VLAN 3.

## Observed readiness and stop conditions

All three machines are control-plane members. Live `talosctl etcd members/status`
showed three voting members, matching applied indexes, no errors, and leader `.242`.
The canonical Kubernetes API is now `https://api.k8s.my.lan:6443`, currently
resolving to the unchanged node address `192.168.1.100`.
Cilium uses the Talos local API proxy (`localhost:7445`) and VXLAN.

Backup repair on 2026-10-26 enabled the hourly CronJob. A scheduled job completed,
and an encrypted snapshot was downloaded to the workstation, decrypted in memory,
checked with etcdutl and restored into isolated tmpfs. See
`../../talos-etcd-backup.md` for key location, independent copy, alerts and GitOps
handoff. A full disposable Talos-cluster recovery rehearsal and the owner's offline
key copy remain required before migration.
Attached Longhorn volumes were healthy. Detached volume
`pvc-ac9d6cd7-76b1-43c7-a4f5-81e6c597811c` reported unknown robustness:
it belongs to `ooni/ooniprobe-data`, last used by a Succeeded Job. Confirm its retained-data requirements before proceeding.
Backup repair used temporary Python age/zstd libraries and checksum-verified etcdutl
v3.7.1 under `/tmp`; these temporary tools must be re-provisioned after cleanup.

Before the first live change:

1. Obtain an encryption recipient with its private identity held independently of
   the cluster. Install/verify encryption and snapshot inspection tools. Choose an
   off-cluster backup directory with mode 0700; never use this repository.
2. Take a fresh etcd snapshot with `talosctl etcd snapshot <protected-path>` from a
   healthy member. The raw snapshot contains Kubernetes Secrets. Use an encrypted
   filesystem for any plaintext temporary copy; encrypt the final artifact before
   moving it elsewhere. Do not assume the snapshot CLI supports stdout streaming.
3. Decrypt on the protected filesystem, inspect with a compatible `etcdutl snapshot
   status`, and perform an isolated recovery rehearsal. Record artifact checksum,
   timestamp, snapshot revision, successful decryption, and recovery result without
   recording secret data. A nonempty encrypted file alone is insufficient.
4. Independently encrypt and back up complete effective Talos configuration documents
   (including storage/network documents), Talos recovery material/client config,
   kubeconfig, UniFi console backup, and a full HA backup. Keep recovery keys apart.
   Never paste effective machine configs or their embedded secrets into this repo.
5. Verify PVC/application backups and off-cluster copies of SeaweedFS/hostPath data.
   An etcd snapshot does not back up volume contents. The GPU node has local data;
   do not reset/reinstall it as a migration shortcut.
6. Establish console/local recovery access and an admin client that can reach both
   subnets. Validate Talos v1.14.2's etcd peer-address update procedure in a disposable
   cluster or version-matched source before scheduling production renumbering.
   This procedure has not yet been established here; do not guess member removal,
   bootstrap, or reset commands.

## Phase 1 — network and API preparation, before renumbering

The separate UniFi staging folder contains a proposed VLAN resource template.
Use a dedicated Infrastructure firewall zone; Internal would inherit broad trust.
Before assigning the network, inspect the controller-generated zone matrix and add
rules that permit the following, with established/related return traffic:

- Admin LAN/authorized VPN clients to Infrastructure management and application ports.
- Infrastructure to gateway DNS/NTP and the Dream Machine Protect API/stream services
  HA actually uses. Keep recorder on gateway; cameras stay on IoT VLAN 20.
- Infrastructure outbound Internet over both IPv4 and IPv6 for current workloads;
  outbound IPv6 must pass the mandatory acceptance gate above.
- Temporary old/new node IP sets to each other for the migration. Prefer a temporary
  all-protocol rule scoped to the six exact old/new node IPs over an incomplete port
  guess; include Pod-network routed traffic if the observed Cilium path needs it.
  Restrict this exception to the maintenance window and test VXLAN across the router.
- HA's specific IoT integration destinations and device callbacks, established from
  HA integration inventory. Discovery across VLANs may require selective mDNS relay;
  SSDP needs separate treatment. Do not turn on universal discovery as a shortcut.
- Deny new IoT/other untrusted traffic to Infrastructure, except measured HA callbacks;
  deny new Infrastructure-to-trusted-client-LAN connections after transition exceptions
  are removed. Test both directions rather than inferring isolation from HA access.

Keep IDS/IPS globally disabled. IoT exclusion is only documented future intent:
this controller discarded `enabled_networks` while inspection was disabled, so a
persisted per-network exclusion has not been proven.

Capture complete current port overrides and actual uplink paths before editing.
The imported provider device resources omitted existing overrides: **do not replace
these with a partial list**. Preserve mirror port 8, WAN Tap ports 14/15 and all
uplinks. Ensure VLAN 30 is tagged end-to-end before changing native VLAN on a node.
Use switch access/native VLAN changes; don't add Talos VLAN subinterfaces for a
single untagged server network. Verify no client Virtual Network Override conflicts.

Prepare local DNS `api.k8s.my.lan -> 192.168.1.100` with a short TTL. The staged
`talos-api-endpoint.patch.yaml` changes the canonical endpoint to this stable name
and adds the current and future IP SANs. Merge with each complete config preserving
all existing SANs and documents; don't replace existing SAN lists blindly. Validate
against the installed Talos schema before applying. Change one node at a time,
verify API certificate and DNS from nodes, and test a separate kubeconfig using the
DNS endpoint before making it canonical. A DNS name pointing at one node is not
an HA load balancer; this migration does not add API high availability.

Keep `talosctl` recovery endpoints as direct healthy node IPs. Kubernetes API SANs
and the Talos management API are separate. See the upstream maintainer explanation:
https://github.com/siderolabs/talos/discussions/9623.

Audit `lan-reference-inventory.json` before the first node move. Add new addresses
alongside old addresses in API/kubelet/monitoring egress policies first. Inspect
node-IP-dependent workloads (Plex, Talos backup, platform reports, generated policy
sources and tests). Preserve trusted-LAN allowlists and external-device addresses;
there must be no global `192.168.1` replacement. Those policy expansions are not
included in the cutover patches and remain a required review gate.

## Phase 2 — rolling node renumbering

Only proceed after backup/recovery, endpoint, firewall, policy and etcd gates pass.
Maintain at least two healthy voting etcd members at every step. Choose `.209`
first, `.242` second, and the canonical endpoint node `.100` last; move leadership
away from the node being maintained when the approved Talos procedure requires it.
For each node, align DHCP reservation and native VLAN in the maintenance window,
then force lease renewal using the validated Talos procedure. Do not move the next
node until the current node has all of:

- Direct Talos management access at the new IP, expected interface/routes and DNS,
  plus verified outbound IPv6 meeting the mandatory gate above.
- Updated etcd peer/client URLs and all three healthy members with caught-up indexes.
- Kubernetes Ready with the correct InternalIP; working Cilium cross-node Pod traffic,
  service DNS, API access, and no stale tunnel/node address failures.
- Healthy Longhorn replicas/mounts and application I/O; expected local storage/NVIDIA
  on `.242`; no stuck attachments or growing errors.

During split-subnet operation the old ingress VIP needs an eligible advertiser on
the old L2 segment. Traefik is currently on `.209` with Local external traffic policy,
and one replica: moving it first can interrupt ingress. Before that move, establish
and verify an eligible Traefik endpoint/MetalLB advertiser remaining on the old LAN,
or explicitly schedule ingress downtime. Do the same for backup-rsync. Do not
promise that a router will forward ARP advertisements between VLANs.

Before moving `.100`, change `api.k8s.my.lan` to an already migrated healthy
control-plane address and verify access from all nodes/admin clients. After `.100`
is healthy on its new address, point DNS to `192.168.30.100`, verify TLS and update
client endpoint lists. Never point DNS to `.30.100` before it is serving.

## Phase 3 — ingress and external dependencies

`ingress.patch` is a **staged diff**, not an active manifest. It changes the MetalLB
pool, both Traefik value sources, and backup-rsync VIP. Review current Argo ownership
before scheduling its eventual application. Coordinate new VIP activation with
UniFi DNS and port-forward targets; public DNS pointing at the WAN IP stays intact.

Update cluster DNS records currently targeting `.1.210` to `.30.210`. Update all
relevant forwards, including TCP and UDP 443 (HTTP/3), mail, Minecraft, and alternate
HTTPS ports. Plex's node target `.1.209` becomes `.30.209`; review its separate
advertised `.1.242` setting. Preserve unrelated torrent forwarding to `.1.141`.
Check real public access from outside: HTTPS, QUIC/HTTP3, mail and other exposed
services, plus internal DNS, TLS, backup-rsync and IPv6 behavior. Capture successful
requests rather than relying only on configuration or gateway hairpin tests.

## Phase 4 — Home Assistant separately

Take/verify HA backup first. Establish the Ethernet reservation `.30.246`, allow
HA-to-Protect and measured IoT flows, and move switch port 3. Confirm direct HA
access over Ethernet before disabling old Wi-Fi; avoid permanent dual-homing that
bypasses segmentation. Then use `homeassistant.patch` to move the external
EndpointSlice and Traefik's explicit egress destination together. Test HA through
its normal hostname, all five camera streams, automations, discovery, and callbacks.
HA and Kubernetes share a subnet: their direct traffic bypasses gateway policy;
use another HA VLAN later if host-to-host separation is required.

## Rollback and completion

At each node stop gate, keep the other two nodes unchanged. If the moved node fails,
restore its prior DHCP/native VLAN and complete prior network config using console
access as necessary; verify the original etcd URLs and full health before continuing.
If peer URLs were explicitly modified, use the validated reverse procedure: reverting
only the switch port may not restore membership. Never reset/bootstrap in response
to a networking failure. Restore DNS only to an API known to be serving that address.

Keep original port settings, encrypted configs and per-stage reverse diffs available.
Reverse ingress/HA diffs only while their old targets are actually reachable. Delete
old IP allowances, leases and DNS after successful observation, then repeat positive
and negative cross-VLAN tests and restore normal TTLs. Retain independent backups.

Preparation validation: cutover diffs checked against current files; YAML parsed;
network template validated with pinned provider in an isolated configuration. None
of the live cutover, backup creation/decryption, restore rehearsal, endpoint change,
or firewall enforcement tests was executed by the initial preparation. Backup
creation, decryption, snapshot validation and isolated etcdutl restore were later
verified during the backup repair; full Talos recovery remains untested.

## Port-provider round-trip caveat observed during phase 1

Provider 0.59.0 merges declared port indices, but serializes some false/empty
flags on unmanaged ports as absent. Port-6 adoption omitted existing false/empty
flags on ports 4, 5, 8, 11, 12, 14, 15 and 18 (including port 18 autoneg=false).
The exact original override objects for those eight ports were restored through
a partial raw API update containing the full preserved override array; all eight
then matched the encrypted baseline exactly. Port 6 remained on Infrastructure.
Before future switch-device writes, capture complete raw overrides, inspect the
plan, and recompare/restore omitted flags afterward. Do not assume an unchanged
native VLAN means every other port setting was preserved by the provider.

## Loki retention incident during maintenance shutdown

The pre-shutdown retention check was missed. Loki's StatefulSet had
`whenScaled: Delete`, and scaling it to zero deleted `storage-loki-0` / volume
`pvc-64003920-403f-44a8-901c-6d5117cca6c0`. No Longhorn backup for namespace Loki
was found. Other StatefulSets had Retain behavior. Loki's durable chunks/index
remain configured in the separate `loki` S3 bucket; local WAL data loss cannot yet
be ruled out. Changed live StatefulSet retention to Retain for both scale/delete.
Persist the matching chart setting and verify S3 history and ingestion after restore.
Do not describe this local PVC as successfully backed up or recovered.

## Verified node procedure and first completed move

w386 is Ready at `192.168.30.209`, its existing etcd member ID is unchanged, and
peer/client URLs point to the new address. All three members reached matching applied
indexes with no errors. Cilium health reached 3/3 nodes and endpoints. Host DNS and a
1 MiB IPv6 HTTPS transfer passed with source
`2a02:e98:c0:181e:ce28:aaff:fe47:715` (HTTP 200).

The effective final networking uses the new UniFi DHCP reservation and SLAAC, retaining
the original host-networking design. Experimental static network patches are not the
final configuration. Persisted fixed hostnames by merging the full **active**
`v1alpha1` configuration in memory and applying the complete validated configuration
without reboot; verified both `persistent` and active resource documents afterward.
Do not select the first listed machine-config resource: it can be a different
persistent snapshot. Preserve active documents and avoid replaying stale resources.

Explicit etcd peer-URL updates are required: the automatic Talos advertised-peer
controller waits for a healthy member, which cannot reliably complete this renumber
on its own. Use version-matched etcdctl `member update` through the healthy quorum,
changing only the existing member's peer URL. No member removal, bootstrap or data
reset was performed. Ephemeral client TLS material was held only in memfd/in memory.
For subsequent moves, keep application volumes detached, persist the unchanged
hostname, set the new DHCP reservation, reboot and change the native port, then
explicitly update that member's peer URL through the two healthy members. Verify
new management, correct node identity, caught-up etcd, Cilium and outbound IPv6 before
continuing. Canonical API DNS now points to verified `192.168.30.209` before moving
its former target `.1.100`.
