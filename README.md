# k3s-local

![K3s](https://img.shields.io/badge/K3s-lightweight%20Kubernetes-blue?logo=kubernetes&style=flat-square)
![Helm](https://img.shields.io/badge/Helm-package%20manager-blue?logo=helm&style=flat-square)
![Longhorn](https://img.shields.io/badge/Longhorn-storage-orange?logo=longhorn&style=flat-square)
![Prometheus](https://img.shields.io/badge/Prometheus-monitoring-orange?logo=prometheus&style=flat-square)
![Grafana](https://img.shields.io/badge/Grafana-visualization-yellow?logo=grafana&style=flat-square)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s?ref=badge_shield)

Here is my pet-project of home/small-office cluster that can handle everything you purchase as a service from the Google or Microsoft, but with significantly more pain and fun. On the other hand, this would be enough for 20-30 employees at 1000 USD setup and easy to scale. K3S is used because it's much simplier to install and I don't really need all that cloud provider's drivers since the goal was to be self-sustainable.

![alt arm based k3s cluster of 4 orangePI 5 nodes](https://andreybondarenko.com/wp-content/uploads/2024/01/413937478_7239783166042743_857868293349421697_n-1024x768.jpg "My ARM65 cluster made of 4 OrangePI 5")
![alt in the rack](https://andreybondarenko.com/wp-content/uploads/2024/10/4000-3000-max-1536x1152.jpg "Now in the rack!")

Old foto:

![alt arm based k3s cluster of 4 orangePI 4LTS nodes with power supply]( https://andreybondarenko.com/wp-content/uploads/2023/07/image-1536x1152.png "My ARM65 cluster made of 4 OrangePI 4LTS")

## Works

* Mail with Dovecot + Postfix + Rspamd. SIEVE is not automated, because Mozilla is too lazy to fix Thunderbird plugin
* Bitwarden self-hosted. Beware of extreme memory usage!
* Tiny-Tiny RSS for old skulls (OBSOTELE)
* Minecraft for resource consumption
* Nextcloud with Collabora and everything needed for the quality life with various photo-related extensions of the Nextcloud
* Matrix message server that actually works
* Infrastructure things like Redis, MySQL, PostgresQL
* Storage is Longhorn with the NFS as a backup
* Backup of mail, databases, Minecraft and redis
* Mongodb without auth, is needed for Spotify stats application
* Spotify stats application
* Clamav that sits on  clamav.clamav.svc.cluster.local:3200/TCP
* UniFi console (OBSOTELE)
* Minio single drive, NFS volume as storage.
* Elasticsearch
* Mastodon
* Prometheus Thanos
* Graphana Loki for log aggregation
* Promtail for logs delivery
* Live RTSP viewer for the Foscam CCTV camera (OBSOTELE)
* FTP server for the Foscam CCTV camera (OBSOTELE)
* Plex
* Vault
* Argocd
* Dawarich to replace Google Maps Timeline
* Harbor as image registry
* Karakeep for bookmarks
* Connectivity checker

## TODO

* Network policies that make sence

## Dokerfiles

Here are [Dockerfiles](https://github.com/shaman007/Dockerfiles) that I am using on my cluster. Usually the main reason fot the own Dockerfile is that the official one either has no aarch64 support or lack some features I want.

### Cluster installation

Sysct сhanges. The swap is incompatible with the K8S, we need to turn on IP forwarding.

```bash
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.ipv6.conf.all.accept_ra = 2
vm.swappiness = 10
```

On master node options are:

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --cluster-cidr=10.42.0.0/16,2001:cafe:42:0::/56 --service-cidr=10.43.0.0/16,2001:cafe:42:1::/112 --flannel-ipv6-masq --disable traefik" sh -s -
```

These would result the config:

```bash
write-kubeconfig-mode: "0644"
tls-san:
  - "mster.k8s.my.lan"
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

Getting token, and then using it on the worker nodes:

```bash
cat /var/lib/rancher/k3s/server/node-token
curl -sfL https://get.k3s.io | K3S_URL=https://master.k8s.my.lan:6443  K3S_TOKEN=K10e::server:1397 sh -
```

To make helm functional:

```bash
cat /etc/rancher/k3s/k3s.yaml > ~/.kube/config
chmod 600 ~/.kube/config
```

Dashboard deployment is optional. I use Mirantis Lens, still, anyway:

```bash
GITHUB_URL=https://github.com/kubernetes/dashboard/releases
VERSION_KUBE_DASHBOARD=$(curl -w '%{url_effective}' -I -L -s -S ${GITHUB_URL}/latest -o /dev/null | sed -e 's|.*/||')
sudo k3s kubectl create -f https://raw.githubusercontent.com/kubernetes/dashboard/${VERSION_KUBE_DASHBOARD}/aio/deploy/recommended.yaml
```

This would copy TLS certificates from the wordpress namespace to the mail namespace, so it would be used by the Postfix and Dovecot:

```bash
kubectl get secret letsencrypt-prod --namespace=wordpress -o yaml| sed 's/namespace: .*/namespace: mail/'|kubectl apply -f -
```

Docker clenup:

```bash
docker system prune -a
```

Rancher cleanup:

```bash
crictl rmi --prune
```


## License
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s.svg?type=large)](https://app.fossa.com/projects/git%2Bgithub.com%2Fshaman007%2Fhome-k3s?ref=badge_large)
