# MetalLB

MetalLB is staged here as the first step toward moving ingress exposure away
from the single node at `192.168.1.209`.

Current intent:

- install MetalLB in `metallb-system`
- advertise a single Layer 2 VIP for ingress: `192.168.1.210`
- keep MetalLB scoped behind `loadBalancerClass: metallb-l2` for now, so it
  does not take over existing `LoadBalancer` services until Traefik is moved
  in a later step

Files:

- `namespace-metallb-system.yaml`: namespace with Pod Security labels required
  by the MetalLB speaker
- `ip-address-pool-public-ingress.yaml`: reserved ingress VIP pool
- `l2-advertisement-public-ingress.yaml`: enables Layer 2 announcements for
  that pool

Before switching Traefik over, verify that `192.168.1.210` is free on the LAN
and then update the router port forwards to target that VIP.
