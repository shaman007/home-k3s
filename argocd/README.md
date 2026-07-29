# Argocd

Here we have some of services managed by the Argocd. If something is not here, that means I am not using it anymore or didn't have done it.

## Obsoleted

* camera
* UniFi controller
* TTRSS
* Dashboard
* Rsyslog

## Mastodon

* `application-mastodon.yaml` manages the official Mastodon Helm chart from
  `https://mastodon.github.io/helm-charts`.
* `application-mastodon-custom.yaml` manages the local companion manifests:
  ExternalSecrets, Postgres, ingress, network policies, and the bookmarked media
  sync job.

## Projects

`application-project-workloads.yaml` defines the first least-privilege Argo CD
project. Applications assigned to `workloads` may deploy namespaced resources
from this repository only, to an explicit list of application namespaces in the
local cluster. They cannot create cluster-scoped resources.

Platform controllers, observability components, third-party Helm charts, and
applications that require cluster-scoped resources remain in `default` until
their permissions and rendered manifests are split into dedicated projects.
Keep the project manifest on an earlier sync wave than its Applications so a
fresh app-of-apps sync creates the project first.

## Repos

```bash
argocd repo add registry-1.docker.io/bitnamicharts --type helm --name bitnami --enable-oci
argocd repo add https://charts.external-secrets.io --type helm --name external-secrets
argocd repo add https://helm.twun.io --type helm --name twuni
```
