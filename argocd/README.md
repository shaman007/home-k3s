# Argocd

Here we have some of services managed by the Argocd. If something is not here, that means I am not using it anymore or didn't have done it.

## Obsoleted

* camera
* UniFi controller
* TTRSS
* Dashboard
* Rsyslog

## TODO

* Mastodon. It has horrible helm chart. I am waiting for the new one that can use 'helm repo' command.

## Repos

```bash
argocd repo add registry-1.docker.io/bitnamicharts --type helm --name bitnami --enable-oci
argocd repo add https://charts.external-secrets.io --type helm --name external-secrets
argocd repo add https://helm.twun.io --type helm --name twuni
```
