Install chart:

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