# TT-RSS deployment from the Helm chart

```bash
helm repo add k8s-at-home https://k8s-at-home.com/charts/
helm install --create-namespace --namespace tt-rss may-tt-rss k8s-at-home/tt-rss -f ./ttrss-values.yaml
```
