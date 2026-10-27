# Public and private ingress

The cluster has two Traefik controllers in namespace `traefik`. They share the
existing backend NetworkPolicy trust boundary, but watch disjoint, explicit
classes for both Kubernetes Ingress and Traefik CRD routes.

| Controller | Class | Addresses |
| --- | --- | --- |
| `traefik` | `traefik` (public) | `192.168.30.210`, `2a02:e98:c0:181e::210` |
| `traefik-private` | `traefik-private` | `192.168.30.211` only |

Neither class is the default. Every declared Ingress has an explicit
`spec.ingressClassName`; every IngressRoute/IngressRouteTCP/IngressRouteUDP has an
explicit `kubernetes.io/ingress.class` annotation. The public controller does not
load private routes, even if a caller supplies their hostname directly.

Internal `*.k8s.my.lan` ingress routes use the private class. Their UniFi DNS A
records point to `.211`; API DNS remains on `.100`, and public DNS is unchanged.
The private Service is IPv4-only, with source ranges for Infrastructure, WireGuard
and cluster Pods. It has no public/global IPv6 address or WAN port forward.
Existing per-route IP allowlists remain as a second check. Default Wi-Fi cannot
reach the private VIP. Physically connected Infrastructure devices remain trusted.

The private controller has two stateless replicas, no shared persistent volume,
and only HTTP/HTTPS/HTTP3 entrypoints. Public mail and Minecraft remain on the
original controller. Both controllers use the pinned Traefik chart 42.1.3.
The private application sets `helm.skipCrds: true`: shared CRDs stay outside its
ownership and cannot be pruned with that release.

`vault-acme` uses `traefik-private` for internal HTTP-01 challenges. Public
Let's Encrypt issuers retain the public `traefik` class. This matters because
internal DNS now sends the ACME validator to the private controller.

## Verification and rollout

Start the private controller and its dedicated MetalLB pool/advertisement first.
Verify private routes and TLS before moving DNS. Allow previous DNS cache TTLs to
expire before withdrawing internal routes from the public controller.

Temporary private-class Ingress copies were used to preload routes during this
migration. They are labelled `migration.home.arpa/private-ingress=true` and must
be removed after the original routes reconcile to `traefik-private`. They are
not permanent manifests or reconciliation holds.

Verify all of the following after pushing the class split:

- Internal Ingress status advertises only `.211`.
- Headlamp and other internal services work through Infrastructure and WireGuard.
- The public VIP returns 404 for internal hostnames, over IPv4 and IPv6.
- Public websites, SMTP/IMAP and Minecraft still work on the public VIP.
- Internal HTTP-01 certificate issuance works through the private class.
- The public VIP has no private routers, and the private release owns no CRDs.

Existing Karakeep and MemPalace holds were removed during this change. Fresh
Longhorn backups completed for both Karakeep PVCs before its queued upgrades.
Karakeep 0.34.1, Chrome 156 and Meilisearch 1.56.0 became ready; the database
upgrade tasks succeeded and the existing search indexes remained present.
