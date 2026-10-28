# Public ingress high availability

Public Traefik uses two replicas, required pod anti-affinity by hostname, a
minAvailable=1 disruption budget, and RollingUpdate (maxUnavailable=0,
maxSurge=1). MetalLB VIPs and public/private ingress classes are unchanged.
Three eligible nodes are needed for a fully surge-based rolling update with
required anti-affinity. If only two eligible nodes remain, restore the third
before starting an update; the disruption budget does not make applications HA.

Certificates are provided by cert-manager Secrets. No Traefik ACME resolver
uses the archived acme.json. The original `traefik` RWO claim is preserved with
Prune=false and its original PV binding; it is no longer mounted by Traefik.
Do not delete it without a separate archive/retention decision.

The `traefik-geoip-rwx` Longhorn claim contains GeoIP data. The migration copies
only geoip/dbip-country-lite.mmdb from the original volume and verifies matching
SHA-256 hashes before deployment. Init containers download into a private staged
file in the destination filesystem, then atomically rename it. Concurrent starts
cannot expose a truncated database; a failed download falls back to the existing
complete copy. The monthly refresh CronJob triggers a rolling restart to refresh
both replicas. No ACME init container remains.

Longhorn stores two replicas with the current longhorn StorageClass. RWX uses a
share manager/NFS endpoint: a node loss can require storage recovery even when
a Traefik replica survives. Pod deletion tests do not establish NFS server or
full node-failure recovery time. Established connections can reset on failover.

Keep `traefik/values.yaml` and the embedded values in
`argocd/application-traefik.yaml` aligned for these settings. Render chart 42.1.3
and run test_traefik_ha.py plus the existing ingress tests before pushing.
