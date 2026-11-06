# MetalLB

The [all-service IPv4 BGP migration](../docs/bgp-trial/services-migration.md) is
prepared locally but not deployed. Its FRR-K8s backend and production BGP
advertisement must be rolled out in that order. Existing L2 advertisements and
all service addresses are retained.

MetalLB advertises reserved Layer 2 VIPs on Infrastructure VLAN 30, using
`loadBalancerClass: metallb-l2`:

- `192.168.30.210` and `2a02:e98:c0:181e::210`: shared Traefik ingress.
- `192.168.30.211`: private Traefik, IPv4 only, in its own non-auto-assigned pool.
- `192.168.30.213`: backup-rsync, IPv4 only.

Traefik requests its two addresses through `metallb.io/loadBalancerIPs` and keeps
IPv4 primary with `RequireDualStack`. The pool and L2 advertisement are reconciled
by the `metallb-config` Argo application.

See [dual-stack ingress](../docs/migrations/dual-stack-ingress/README.md) for the
Cilium/Talos allocation model, firewall rules, verification and rollback order.

See [private ingress](../traefik-private/README.md) for class isolation and internal DNS.

See [staged FRR retirement](../docs/metallb-l2-retirement.md) for the reviewed
L2-only backend migration, retained CRDs and verification/rollback steps.

See [speaker non-root compatibility](../docs/metallb-speaker-nonroot.md) for the
projected-volume group requirement, retained NET_RAW and post-rollout checks.
