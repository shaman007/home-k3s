# First live stage for review

This stage builds and publishes only the new solver image, provisions its scoped
OpenBao read access, and installs the staging solver/canary. Production ingress
and backend cutover are later stages. No commands below have been run.

## Image delivery

`tools/godaddy-webhook/prepare-build.py` generates a one-off Job manifest under
`/tmp`, bundling exactly Dockerfile, go.mod, go.sum and main.go in a ConfigMap.
The source archive hash selects the Job name and image tag. The Job runs the
same privileged Podman image as the existing image-builder CronJob, inherits its
network-policy labels, and uses the existing Harbor builder credential Secret.
It has no Kubernetes API token. It builds AMD64 and publishes
`harbor.andreybondarenko.com/library/godaddy-webhook:<source-hash-prefix>`.
The output includes the pushed image digest. The build Job has no automatic retry.

After approval, submit the generated ConfigMap and Job with `kubectl create -f`
(not `kubectl apply`), monitor that exact Job, inspect build logs, and obtain the
pushed digest. A failed Job is investigated rather than automatically recreated.
The temporary source ConfigMap can be deleted after successful delivery.

## Scoped OpenBao role

Inspect for existing policy/role names before writing. Using an already
authenticated administrative vault CLI, create:

```sh
vault policy write godaddy-dns-read tools/godaddy-webhook/openbao-policy.hcl
vault write auth/kubernetes/role/external-secrets-godaddy \
  bound_service_account_names=godaddy-vault-auth \
  bound_service_account_namespaces=cert-manager \
  audience=vault \
  token_policies=godaddy-dns-read \
  token_ttl=1h \
  token_max_ttl=1h
```

The policy only permits reading `kv/data/godaddy`. Do not print or change its
secret value. The role must not overwrite an unrelated existing role.

## Solver and canary

Render/lint the chart with the real image digest and existing public CA bundle
from an OpenBao SecretStore. Install a new Helm release `godaddy-webhook` in
`cert-manager` using these values. This installs 18 objects including an
unconsumed staging Certificate. `productionEnabled` stays false.
Do not use a placeholder image digest or test CA value from local render tests.

Validate APIService Available, SecretStore Ready, ExternalSecret Ready and the
staging Certificate Ready. Inspect Order/Challenge events without exposing token
Secrets. Independently query authoritative GoDaddy nameservers for the canary
TXT during issuance and its cleanup afterward. Confirm the resulting Secret
contains a staging-issued certificate for the exact canary SAN. Exercise renewal
and cleanup after a solver restart before enabling production issuance.

Rollback removes only this release and its scoped policy/role after its staging
challenges are cleaned up. Never remove pre-existing TLS Secrets, issuers, roles,
PVCs or backend trust while rolling back this stage.
