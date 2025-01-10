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
