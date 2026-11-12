# UDM-only BGP expansion — 2026-11-12

Applied with explicit user authorization to only `unifi_bgp.kubernetes` in
`/home/shaman007/git/unifi-infra`. The fresh targeted plan was checked to contain
exactly one in-place update and the expected two FRR changes. No plan file was
saved because serialized plans may include sensitive prior state.

```text
Apply complete! Resources: 0 added, 1 changed, 0 destroyed.
```

Applied policy: permit only the additional `192.168.30.212/32` at sequence 35,
raise `neighbor K8S-TRIAL maximum-prefix` from 3 to 4. All other payload bytes
match the preserved baseline. A fresh `--bgp-only` plan after apply returned
exit 0 / no changes, including a refreshed controller read.

## Access and before/after observations

SSH remains unavailable because the hardware-key/agent authentication fails.
The existing authenticated HTTPS controller API was reachable with normal TLS
verification. Credentials and session cookies stayed in process memory only.
Live neighbor and forwarding data came from the existing exporter's reviewed
`bgp/neighbors` and `routes` endpoints, not from stale Terraform state.

Baseline was collected at 16:13:54 UTC; stable post-change checks passed at
16:15:59 UTC and again at 16:17:02 UTC. One immediate post-change gate failed
during configuration reload; later fresh checks passed. Zero interruption or
preservation of every established connection was not measured or claimed.

| Peer | Before / after | Remote ASN | Received prefixes | Exported routes |
| --- | --- | --- | --- | --- |
| 192.168.30.100 | Established / Established | 65040 | 2 / 2 | 0 / 0 |
| 192.168.30.209 | Established / Established | 65040 | 1 / 1 | 0 / 0 |
| 192.168.30.242 | Established / Established | 65040 | 2 / 2 | 0 / 0 |

Active forwarding next hops matched before and after exactly:

| Prefix | Active next hops |
| --- | --- |
| 192.168.30.210/32 | 192.168.30.100, 192.168.30.242 |
| 192.168.30.211/32 | 192.168.30.100, 192.168.30.209 |
| 192.168.30.213/32 | 192.168.30.242 |

The existing exporter's policy-violation checks were zero. No unexpected BGP
prefix was present; `.212/32` remained absent from the forwarding table.

Service checks before and after:

- `.210`: certificate-verified Harbor `/api/v2.0/ping` returned HTTP 200 over the
  infrastructure VLAN. An additional request bound to Wi-Fi `wlo1` verified
  routed public HTTPS returned HTTP 200 before and after.
- `.211`: certificate-verified OpenBao `/v1/sys/health` returned HTTP 200.
- `.213`: TCP 22 returned the expected `SSH-2.0-OpenSSH_10.0` banner; no login,
  remote command or backup-data operation was performed.

The API forwarding-table observations cover all three routes; positive service
probes for private VIPs were from the permitted infrastructure VLAN. No new
WireGuard session or network access rule was created for a routed private probe.

## Scope and recovery

No other Terraform resource was applied. The unrelated full-plan drift/provider
identity errors were not repaired or applied. Harbor, MetalLB pools and
advertisements, DNS, firewall policies and required-route monitoring were not
changed. The new VIP is allowed by UDM but is not allocated or advertised.

Original payload: [udm-before.conf](udm-before.conf), SHA-256
`ea4be2a6c58532a34476d8515754549748dfe8c4b7fe105774a5b85393400dba`.
Since no fourth route exists, rollback remains a scoped restoration of this
original BGP payload after verifying every peer accepts at most three prefixes.
Do not withdraw the shared existing `routed-services` advertisement.

The staged Harbor rollout and later withdrawal-first rollback remain in
[README.md](README.md). No Git repository was initialized in `unifi-infra`, and
no commit or push was performed by this deployment step.
