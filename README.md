# home-k3s

![K3s](https://img.shields.io/badge/K3s-lightweight%20Kubernetes-blue?logo=kubernetes&style=flat-square)
![Helm](https://img.shields.io/badge/Helm-package%20manager-blue?logo=helm&style=flat-square)
![Longhorn](https://img.shields.io/badge/Longhorn-storage-orange?logo=longhorn&style=flat-square)
![Prometheus](https://img.shields.io/badge/Prometheus-monitoring-orange?logo=prometheus&style=flat-square)
![Grafana](https://img.shields.io/badge/Grafana-visualization-yellow?logo=grafana&style=flat-square)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s?ref=badge_shield)

Here is my pet-project of home/small-office cluster that can handle everything
you purchase as a service from the Google or Microsoft, but with significantly
more pain and fun. On the other hand, this would be enough for 20-30 employees
at 1000 USD setup and easy to scale. K3S is used because it's much simplier to
install and I don't really need all that cloud provider's drivers since the
goal was to be self-sustainable.
`home-k3s` is a homelab/small-office cluster built on k3s and managed mostly
through Argo CD manifests in this repository. The cluster runs user-facing
apps, shared platform services, observability, and storage.

![ARM-based k3s cluster of 4 OrangePi 5 nodes](https://andreybondarenko.com/wp-content/uploads/2024/01/413937478_7239783166042743_857868293349421697_n-1024x768.jpg "My ARM64 cluster made of 4 OrangePi 5")
![Cluster in the rack](https://andreybondarenko.com/wp-content/uploads/2024/10/4000-3000-max-1536x1152.jpg "Now in the rack")

Older photo:

![ARM-based k3s cluster of 4 OrangePi 4LTS nodes with power supply](https://andreybondarenko.com/wp-content/uploads/2023/07/image-1536x1152.png "My ARM64 cluster made of 4 OrangePi 4LTS")

## Current stack

Core platform:

- k3s
- Traefik
- Argo CD
- External Secrets
- Vault
- Longhorn

Data and messaging:

- PostgreSQL
- MySQL
- Redis (operator + app-specific instances)
- SeaweedFS (S3-compatible object storage)
- Elasticsearch (ECK operator + stack)

User-facing apps:

- Mail (Postfix + Dovecot + Rspamd)
- Bitwarden
- Nextcloud + Collabora
- Synapse (Matrix messaging server)
- Mastodon
- WordPress
- Plex
- Minecraft
- Keycloak
- Dawarich
- Karakeep
- Your Spotify
- Year calendar
- ConvertX
- Stirling PDF
- UniFi
- Home Assistant

Observability and security:

- Prometheus + exporters
- Thanos
- Loki
- ClamAV
- Connectivity exporter
- CA scanner UI (`canitiser/`)

## Repository layout

- `argocd/`: Argo CD `Application` manifests (main deployment entrypoint).
- `argocd-deploy/`: Argo CD post-install cluster manifests (ConfigMap and Ingress).
- `<service>/`: Namespace-scoped manifests/charts for each service.
- `DEPRECATED/`: Old manifests kept for reference.
- `k3s-config.yaml`: Baseline k3s server config used by this cluster.

## Bootstrap flow

1. Prepare Linux sysctl settings on all nodes.

```bash
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.ipv6.conf.all.accept_ra = 2
vm.swappiness = 10
```

2. Install the first (server) node.

   Update `tls-san` in `k3s-config.yaml`, copy it to
   `/etc/rancher/k3s/config.yaml`, then install:

```bash
curl -sfL https://get.k3s.io | \
  INSTALL_K3S_EXEC="server --cluster-cidr=10.42.0.0/16,2001:cafe:42:0::/56 \
  --service-cidr=10.43.0.0/16,2001:cafe:42:1::/112 \
  --flannel-ipv6-masq --disable traefik" sh -s -
```

These would result the config:

```bash
write-kubeconfig-mode: "0644"
tls-san:
  - "w386.k8s.my.lan"
  - "localhost"
cluster-cidr: "10.42.0.0/16"
cluster-cidr-ipv6: "2001:cafe:42:0::/56"
service-cidr: "10.43.0.0/16"
service-cidr-ipv6: "2001:cafe:42:1::/112"
flannel-backend-type: "vxlan"
flannel-ipv6-masq: true
no-deploy:
  - traefik
```

3. Join worker nodes.

```bash
cat /var/lib/rancher/k3s/server/node-token
curl -sfL https://get.k3s.io | \
  K3S_URL=https://master.k8s.my.lan:6443 K3S_TOKEN=<node-token> sh -
```

4. Configure local `kubectl` access.

```bash
cat /etc/rancher/k3s/k3s.yaml > ~/.kube/config
chmod 600 ~/.kube/config
```

5. Install and bootstrap Argo CD.

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -f argocd-deploy/config-map-argocd-cmd-params-cm.yaml
kubectl apply -f argocd-deploy/ingress-argocd-ingress.yaml
```

Apply all Argo CD Applications from this repo:

```powershell
Get-ChildItem .\argocd\*.yaml | ForEach-Object { kubectl apply -f $_.FullName }
```

## Useful operations

Container image cleanup:

```bash
docker system prune -a
crictl rmi --prune
```

## Dockerfiles

Custom images used by this cluster are in
[shaman007/Dockerfiles](https://github.com/shaman007/Dockerfiles). They are
mainly used when upstream images do not support `aarch64` or are missing
required features.

## Deprecated manifests

Historical manifests are kept under [`DEPRECATED/`](DEPRECATED/README.md).

## License

[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s.svg?type=large)](https://app.fossa.com/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s?ref=badge_large)
