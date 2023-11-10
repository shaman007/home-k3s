# k3s-local


Here are notes not to forget how it is installed.

Sysct:

```
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.ipv6.conf.all.accept_ra = 2
vm.swappiness = 100
```

On master node options:

```
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --cluster-cidr=10.42.0.0/16,2001:cafe:42:0::/56 --service-cidr=10.43.0.0/16,2001:cafe:42:1::/112 --flannel-ipv6-masq --disable traefik" sh -s -
```

Token:

```
cat /var/lib/rancher/k3s/server/node-token
curl -sfL https://get.k3s.io | K3S_URL=https://master.k8s.my.lan:6443  K3S_TOKEN=K10e::server:1397 sh -
```

To make helm functional:

```
cat /etc/rancher/k3s/k3s.yaml > ~/.kube/config
chmod 600 ~/.kube/config
```

NFS:

```
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm install nfs-subdir-external-provisioner nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
    --create-namespace \
    --namespace nfs-provisioner \
    --set nfs.server=rapi.my.lan \
    --set nfs.path=/storage/k8s
```

Letsencrypt

```
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.12.0/cert-manager.yaml
```

NGINX ingress

```
helm upgrade --install ingress-nginx ingress-nginx \
    --repo https://kubernetes.github.io/ingress-nginx \
    --namespace ingress-nginx --create-namespace
```

Dashboard

```
GITHUB_URL=https://github.com/kubernetes/dashboard/releases
VERSION_KUBE_DASHBOARD=$(curl -w '%{url_effective}' -I -L -s -S ${GITHUB_URL}/latest -o /dev/null | sed -e 's|.*/||')
sudo k3s kubectl create -f https://raw.githubusercontent.com/kubernetes/dashboard/${VERSION_KUBE_DASHBOARD}/aio/deploy/recommended.yaml
```

Postgres

```
helm install postgres oci://registry-1.docker.io/bitnamicharts/postgresql
```

TT-Rss

```
helm repo add k8s-at-home https://k8s-at-home.com/charts/
helm install --create-namespace --namespace tt-rss may-tt-rss k8s-at-home/tt-rss -f ./values.yaml
```

Collabora:

```
helm repo add collabora https://collaboraonline.github.io/online/
helm install --create-namespace --namespace collabora collabora-online collabora/collabora-online -f my_values.yaml
```

Registry:

```
upgrade registry twuni/docker-registry -f ./values.yaml  --namespace=registry
```

Mail:

```
kubectl expose service postfix-tls --port=587 --target-port=587  --name=my-mail --type=LoadBalancer --namespace=mail
kubectl expose service dovecot-tls --port=993 --target-port=993  --name=imap-tls --type=LoadBalancer --namespce=mail
kubectl get secret letsencrypt-prod --namespace=default -o yaml| sed 's/namespace: .*/namespace: mail/'|kubectl apply -f -
```


Docker:

```
docker system prune -a
```


Rancher:

```
crictl rmi --prune
```
