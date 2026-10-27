# MetalLB

MetalLB advertises reserved Layer 2 VIPs on Infrastructure VLAN 30, using
`loadBalancerClass: metallb-l2`:

- `192.168.30.210` and `2a02:e98:c0:181e::210`: shared Traefik ingress.
- `192.168.30.213`: backup-rsync, IPv4 only.

Traefik requests its two addresses through `metallb.io/loadBalancerIPs` and keeps
IPv4 primary with `RequireDualStack`. The pool and L2 advertisement are reconciled
by the `metallb-config` Argo application.

See [dual-stack ingress](../docs/migrations/dual-stack-ingress/README.md) for the
Cilium/Talos allocation model, firewall rules, verification and rollback order.
