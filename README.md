# k3s-local

Here is my pet-project of home/small-office cluster that can handle everything you purchase as a service from the Google or Microsoft, but with significantly more pain and fun. On the other hand, this would be enough for 20-30 employees at 1000 USD setup and easy to scale. K3S is used because it's much simplier to install and I don't really need all that cloud provider's drivers since the goal was to be self-sustainable.

![alt arm based k3s cluster of 4 orangePI 4LTS nodes with power supply]( https://andreybondarenko.com/wp-content/uploads/2023/07/image-1536x1152.png "My ARM65 cluster made of 4 OrangePI LTS")

## Works

* Mail with Dovecot + Postfix + Rspamd. SIEVE is not automated, because Mozilla is too lazy to fix Thunderbird plugin
* Bitwarden self-hosted. Beware of extreme memory usage!
* Tiny-Tiny RSS for old skulls
* Minecraft for resource consumption
* Nextcloud with Collabora and everything needed for the quality life with various photo-related extensions of the Nextcloud
* Cluster-related things like trivial log aggregation and metrics collection
* Matrix message server that actually works
* Infrastructure things like Redis, MySQL, PostgresQL
* Storage is NFS and it surprisingly reliable
* Backup of mail, databases, Minecraft and redis
* Mongodb without auth, is needed for Spotify stats application
* Spotify stats application
* Clamav that sits on  clamav.clamav.svc.cluster.local:3200/TCP

## Dokerfiles

Here are [Dockerfiles](https://github.com/shaman007/Dockerfiles) that I am using on my cluster. Usually the main reason fot the own Dockerfile is that the official one either has no aarch64 support or lack some features I want.

### Cluster installation

Sysct сhanges. The swap is incompatible with the K8S, we need to turn on IP forwarding.

```bash
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.ipv6.conf.all.accept_ra = 2
vm.swappiness = 100
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

Installation of the NFS volume provisioner. NFS server hostname and exported path is needed:

```bash
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm install nfs-subdir-external-provisioner nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
    --create-namespace \
    --namespace nfs-provisioner \
    --set nfs.server=rapi.my.lan \
    --set nfs.path=/storage/k8s
```

Letsencrypt deployment:

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.12.0/cert-manager.yaml
```

NGINX ingress deployment instaed of the Traefik:

```bash
helm upgrade --install ingress-nginx ingress-nginx \
    --repo https://kubernetes.github.io/ingress-nginx \
    --namespace ingress-nginx --create-namespace
```

Dashboard deployment is optional. I use Mirantis Lens, still, anyway:

```bash
GITHUB_URL=https://github.com/kubernetes/dashboard/releases
VERSION_KUBE_DASHBOARD=$(curl -w '%{url_effective}' -I -L -s -S ${GITHUB_URL}/latest -o /dev/null | sed -e 's|.*/||')
sudo k3s kubectl create -f https://raw.githubusercontent.com/kubernetes/dashboard/${VERSION_KUBE_DASHBOARD}/aio/deploy/recommended.yaml
```

Postgres deployment from the Helm chart:

```bash
helm install postgres oci://registry-1.docker.io/bitnamicharts/postgresql
```

TT-RSS deployment from the Helm chart

```bash
helm repo add k8s-at-home https://k8s-at-home.com/charts/
helm install --create-namespace --namespace tt-rss may-tt-rss k8s-at-home/tt-rss -f ./values.yaml
```

Collabora deployment from the Helm chart:

```bash
helm repo add collabora https://collaboraonline.github.io/online/
helm install --create-namespace --namespace collabora collabora-online collabora/collabora-online -f my_values.yaml
```

Registry deployment from the Helm chart:

```bash
upgrade registry twuni/docker-registry -f ./values.yaml  --namespace=registry
```

This would copy TLS certificates from the wordpress namespace to the mail namespace, so it would be used by the Postfix and Dovecot:

```bash
kubectl get secret letsencrypt-prod --namespace=default -o yaml| sed 's/namespace: .*/namespace: mail/'|kubectl apply -f -
```

Docker clenup:

```bash
docker system prune -a
```

Rancher cleanup:

```bash
crictl rmi --prune
```
