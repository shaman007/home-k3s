# Harbor

Managed by Helm.

## Proxy cache projects

Workload images should use Harbor whenever the upstream registry has a proxy
cache project. The project name is inserted between the Harbor hostname and the
upstream repository path.

| Harbor project | Upstream registry | Registry endpoint name |
| --- | --- | --- |
| `dockerhub` | `https://hub.docker.com` | `dockerhub` |
| `quay` | `https://quay.io` | `quay` |
| `github` | `https://ghcr.io` | `github` |
| `google` | `https://gcr.io` | `google` |
| `k8s` | `https://registry.k8s.io` | `kubernetes` |
| `elastic` | `https://docker.elastic.co` | `elastic` |
| `nvidia` | `https://nvcr.io` | `nvidia` |
| `ecr` | `https://public.ecr.aws` | `ecr-public` |

For example, `registry.k8s.io/metrics-server/metrics-server:v0.8.1` becomes
`harbor.andreybondarenko.com/k8s/metrics-server/metrics-server:v0.8.1`.

Run `harbor/reconcile-proxy-caches.sh` with `HARBOR_USERNAME` and
`HARBOR_PASSWORD` set to an administrative Harbor credential to recreate any
missing endpoint/project pairs. The script never changes an existing endpoint
or project.

Bootstrap components intentionally keep upstream image references. Harbor,
Argo CD, Cilium, cert-manager, Longhorn, MetalLB, Traefik, and Vault participate
in bringing up Harbor's storage, networking, ingress, certificates, or GitOps
control plane and must remain recoverable when Harbor is unavailable.
