# home-k3s

![Talos](https://img.shields.io/badge/Talos-Kubernetes-blue?logo=kubernetes&style=flat-square)
![Helm](https://img.shields.io/badge/Helm-package%20manager-blue?logo=helm&style=flat-square)
![Longhorn](https://img.shields.io/badge/Longhorn-storage-orange?logo=longhorn&style=flat-square)
![Prometheus](https://img.shields.io/badge/Prometheus-monitoring-orange?logo=prometheus&style=flat-square)
![Grafana](https://img.shields.io/badge/Grafana-visualization-yellow?logo=grafana&style=flat-square)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s?ref=badge_shield)

My home/small-office Kubernetes cluster: self-hosted applications, shared platform
services, observability, and storage, with significantly more pain and fun than
buying them as a service.

The repository keeps its original `home-k3s` name, but the platform now uses
**Talos Linux**, with **Argo CD** managing Kubernetes applications from Git.
The inventory below describes the repository configuration; it is not a live
cluster health report.

## Cluster photos

Photos from earlier ARM64/k3s setups:

![ARM-based k3s cluster of 4 OrangePi 5 nodes](https://andreybondarenko.com/wp-content/uploads/2024/01/413937478_7239783166042743_857868293349421697_n-1024x768.jpg "My ARM64 cluster made of 4 OrangePi 5")
![Cluster in the rack](https://andreybondarenko.com/wp-content/uploads/2024/10/4000-3000-max-1536x1152.jpg "Now in the rack")

Older photo:

![ARM-based k3s cluster of 4 OrangePi 4LTS nodes with power supply](https://andreybondarenko.com/wp-content/uploads/2023/07/image-1536x1152.png "My ARM64 cluster made of 4 OrangePi 4LTS")

## Current stack

| Area | Components |
| --- | --- |
| Platform | Talos Linux, Argo CD, Cilium with Hubble, MetalLB |
| Ingress and certificates | Public and private Traefik, cert-manager, GoDaddy DNS-01 webhook |
| Secrets and identity | OpenBao, External Secrets, Keycloak |
| Storage and databases | Longhorn, SeaweedFS, PostgreSQL, MySQL, app-local Valkey, OpenSearch |
| Observability | Prometheus, Grafana, Alertmanager, Thanos, Loki, Alloy, exporters |
| Security | CrowdSec, ClamAV, audit-only Kyverno policies, infrastructure admission guards |
| Image delivery | Harbor and the cluster image builder |

Applications include:

- Mail (Postfix, Dovecot, Rspamd), Bitwarden, Nextcloud and Collabora.
- Matrix (Synapse and Element), Mastodon, WordPress, and Firefox Sync with
  Mozilla accounts for sign-in.
- Immich, Plex, Minecraft, Home Assistant, Dawarich, Karakeep, and Your Spotify.
- Open WebUI, Ollama, ComfyUI, NLLB, SearXNG, and Open Terminal.
- Bastioncam, ConvertX, Stirling PDF, Hister, Year calendar, and Headlamp.
- MemPalace, RIPE Atlas, OONI, connectivity exporters, and the CA scanner UI.

See each service directory and its matching `argocd/application-*.yaml` for
configuration and dependencies. Historical directories alone do not imply an
active Argo CD deployment.

## Repository layout

| Path | Purpose |
| --- | --- |
| [`argocd/`](argocd/README.md) | Applications, scoped AppProjects, and the app-of-apps entrypoint |
| `argocd-install/` | Pinned upstream Argo CD installation managed with Kustomize |
| `argocd-deploy/` | Argo CD configuration and ingress |
| `talos/` | Node-specific machine patches and Cilium/Longhorn values |
| `namespaces/` | Namespaces, quotas, limits, and priority classes |
| `<service>/` | Application manifests, charts, values, and service documentation |
| `tools/` and `tests/` | Validation, policy generation, operational helpers, and tests |
| `docs/` | Operations, security reviews, and migration runbooks |
| [`DEPRECATED/`](DEPRECATED/README.md) | Retired manifests kept for reference |

`k3s-config.yaml` remains as a legacy configuration reference. It is not the
bootstrap configuration for the Talos platform.

## Deployment model

The parent [`argocd-applications`](argocd/applications-manager.yaml) Application
reads `application-*.yaml` from `argocd/` on `main`. Child Applications use
purpose-specific AppProjects and either local manifests or pinned upstream Helm
charts. Automated Applications generally self-heal; pruning is enabled selectively
according to persistence and deletion requirements. See the
[Argo CD notes](argocd/README.md) before adding or moving an Application.

For a new installation, provision Talos and establish Kubernetes API access and
networking before bootstrapping Argo CD from `argocd-install/`. Review the
node-specific patches under `talos/`, storage devices, DNS, ingress addresses,
and secret dependencies for your environment first. This repository contains
cluster-specific configuration, rather than a complete portable installer.

The Argo CD installation is subsequently managed by the `argocd-install`
Application. Renovate updates pinned dependencies; review upstream upgrade notes
and the [upgrade playbook](docs/upgrade-playbook.md) before accepting changes.
Secrets are supplied through External Secrets and OpenBao; secret values and
unseal material do not belong in Git.

## Validation

The [Validate Kubernetes workflow](.github/workflows/validate-k8s.yml) checks
runtime contracts, repository tests, generated policies, rendered Applications,
resource budgets, security contexts, and Kubernetes schemas.

Start with the repository tests:

```sh
python3 -m unittest discover -s tests
```

For application rendering and schema validation, install the prerequisites and
follow the [CI validation guide](docs/ci-validation.md). Rendered Helm output can
contain generated Secrets; keep it private. Passing validation does not establish
runtime connectivity, successful secret refresh, or application functionality.

## Operations and runbooks

- [Upgrade checks](docs/upgrade-playbook.md) and
  [Talos etcd backups](docs/talos-etcd-backup.md).
- [Longhorn rollout safety](docs/longhorn-rollout-safety.md) and
  [Valkey persistence and cutover](docs/valkey-cutover.md).
- [OpenBao migration and rollback boundary](docs/openbao-migration.md).
- [Internal-domain certificate migration](docs/migrations/letsencrypt-internal/PRODUCTION.md).
- [Platform health checks](docs/platform-health-checks.md),
  [monitoring alerts](docs/monitoring-alerts.md), and [log reports](docs/logs-check.md).
- [NetworkPolicy generation](docs/networkpolicy-generation.md),
  [container resources](docs/container-resources.md), and
  [Kyverno audit policies](kyverno/README.md).
- [Firefox Sync setup and verification](firefox-sync/README.md).

## Dockerfiles

Custom images used by this cluster are in
[shaman007/Dockerfiles](https://github.com/shaman007/Dockerfiles). They are
mainly used when upstream images do not support `aarch64` or are missing
required features.

## Deprecated manifests

Historical manifests are kept under [`DEPRECATED/`](DEPRECATED/README.md).
This includes the retired Wazuh stack and Hypermind Swarm.
See [the retirement notes](DEPRECATED/hypermind/README.md).

## License

[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s.svg?type=large)](https://app.fossa.com/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s?ref=badge_large)
