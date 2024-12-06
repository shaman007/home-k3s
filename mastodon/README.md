Install chart:

add

```
- name: common
  repository: oci://registry-1.docker.io/bitnamicharts
  version: 2.19.3
```
to che Chart.yaml and .lock

```
git clone https://github.com/mastodon/chart.git
cd Chart
helm dependency build
helm install --namespace mastodon mastodon ./ -f ../mastodon-values.yaml
```

To bring back disks:

```
kubectl annotate pvc mastodon-system meta.helm.sh/release-name=mastodon -n mastodon
kubectl annotate pvc mastodon-system meta.helm.sh/release-namespace=mastodon -n mastodon
kubectl label pvc mastodon-assets app.kubernetes.io/managed-by=Helm -n mastodon
kubectl label pvc mastodon-system app.kubernetes.io/managed-by=Helm -n mastodon
kubectl annotate pvc mastodon-assets meta.helm.sh/release-name=mastodon -n mastodon
kubectl annotate pvc mastodon-assets meta.helm.sh/release-namespace=mastodon -n mastodon
```
