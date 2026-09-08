# Deployment validation

`Validate Kubernetes` runs policy tests, runtime-contract checks and generated
NetworkPolicy checks, then renders every Application in `argocd/` from the current
checkout. Helm uses the application's pinned chart, destination namespace,
release name, `$values` files, inline values and parameter overrides. Kustomize
sources are built with `kubectl kustomize`; directory sources honor include,
exclude and recurse settings. Unsupported source options fail explicitly.

`tools/ci/validation-config.yaml` pins the target Kubernetes version. Update it
and the workflow's kubectl version with cluster upgrades. The kubeconform archive
is checked against the reviewed release SHA-256 before extraction; update both
its version and checksum when upgrading it.

All rendered manifests and tracked raw Kubernetes manifests are validated.
Talos machine configuration is excluded from Kubernetes manifest discovery. Kustomization
configuration is consumed by rendering, rather than passed to Kubernetes schema
validation. Built-in resources use strict kubeconform validation for the configured
Kubernetes version. Custom resources use schemas from the rendered controller
CRDs. CiliumNetworkPolicy's CRD is fetched from the Cilium application version
because Cilium installs its CRDs at runtime. Missing schemas fail validation.
CRD definitions receive explicit group/name, scope, version, storage-version and
OpenAPI schema-shape checks because kubeconform does not publish their schema.
OpenAPI nullable and int-or-string fields are translated to JSON Schema, and
Kubernetes Unicode regular-expression categories are supported, and
unknown properties are rejected except in maps or explicitly preserved fields.
Admission webhooks, CEL rules, cluster capabilities and runtime connectivity
still require deployment verification.

Local reproduction (Python with PyYAML, jsonschema and regex, Helm, kubectl, curl and
kubeconform required):

```sh
python -m unittest discover -s tests
python tools/ci/render-applications.py --output /tmp/home-k3s-rendered
python tools/ci/validate-rendered.py --rendered /tmp/home-k3s-rendered
```

Use an empty output directory. Rendered files can contain generated chart Secrets;
the directory is private and CI does not publish it as an artifact. Validation
errors show resource identities and failing constraint paths, not values. For
Helm diagnostics, reproduce the failing source locally and keep output private.
`--application NAME` supports isolated rendering; full validation requires the
complete application inventory.
