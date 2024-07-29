# Argocd

Here we have some of services managed by the Argocd. If something is not here, that means I am not using it anymore or didn't have done it.

## Obsoleted

* camera
* UniFi controller
* TTRSS
* Dashboard
* Rsyslog

## TODO

* Loki
* Mastodon
* Registry

## Repos

```
argocd repo add registry-1.docker.io/bitnamicharts --type helm --name bitnami --enable-oci
argocd repo add https://charts.external-secrets.io --type helm --name external-secrets
```
