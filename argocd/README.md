# Argocd

Here we have some of services managed by the Argocd. If something is not here, that means I am not using it anymore or didn't have done it.

## Obsoleted

* camera
* UniFi controller
* TTRSS
* Dashboard
* Rsyslog

## TODO

* Mastodon main Helm release is still outside ArgoCD because the current vendored
  chart is ignored by Git in `mastodon/.gitignore`. Either track that chart in the
  repo or migrate to the newer official `mastodon/helm-charts` repo once it catches
  up with the app version we run and the migration cost is worth it.

## Repos

```bash
argocd repo add registry-1.docker.io/bitnamicharts --type helm --name bitnami --enable-oci
argocd repo add https://charts.external-secrets.io --type helm --name external-secrets
argocd repo add https://helm.twun.io --type helm --name twuni
```
