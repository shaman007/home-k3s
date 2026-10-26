# Infrastructure VLAN migration — staged, not executed

Prepared 2026-10-26. No node addresses, switch ports, live DNS, firewall policies,
or active GitOps manifests have been changed by this preparation.
Network IaC belongs in `/home/shaman007/git/unifi-infra`, outside this repository.

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
- Verify IPv6 egress from each application workload that requires it. IPv6 on
  nodes does not provide native IPv6 connectivity to IPv4-only Pods automatically.
  Before migration, identify those workloads and validate an explicit supported
  egress design (dual-stack Pod networking or an appropriate application proxy).
  Keeping Pod/Service CIDRs unchanged is conditional on meeting this requirement;
  any required CNI/CIDR change needs a separate reviewed migration plan.
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
The canonical Kubernetes API remains `https://192.168.1.100:6443`.
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
