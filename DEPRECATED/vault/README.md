# Vault token rotator

The token rotator was retired in August 2026. External Secrets uses Vault
Kubernetes authentication, so no static Vault token rotation is required.

The former CronJob and its unused RBAC/configuration manifests are intentionally
absent from the active `vault` Argo CD application. Git history retains their
previous definitions.
