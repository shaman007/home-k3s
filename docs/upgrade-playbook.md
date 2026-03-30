# Upgrade Playbook

This repo already validates Kubernetes schema with `kubeconform`. That catches
broken YAML, but it does not catch runtime contract drift after upstream image
or chart upgrades. Recent follow-up fixes landed in these areas:

- probe endpoints were valid YAML but poor health checks
- startup flags changed across versions
- secret wiring needed to move behind stable `ExternalSecret` targets
- observability add-ons gained new cluster or egress dependencies

Use this playbook before merging Renovate or manual version bumps.

## Per-workload checklist

### Web apps behind Nginx, Traefik, or a custom HTTP server

- Confirm liveness and readiness use a cheap route meant for automation.
- Prefer a dedicated `/health` style endpoint over heavy diagnostics or
  user-facing routes.
- Do not probe `/metrics` unless upstream explicitly documents it as a health
  endpoint.
- If the app is fronted by Nginx, verify the probe route still reaches the real
  backend after config changes.

### Exporters and agents

- Prefer `tcpSocket` probes when the process only needs to accept a connection
  and does not expose a dedicated health route.
- Re-check CLI flags against the upstream release notes for renamed or removed
  options.
- Review outbound dependencies after upgrades. Telemetry agents often gain new
  HTTPS destinations or APIs that NetworkPolicies must allow.

### Stateful services and embedded startup logic

- Keep startup configuration idempotent.
- If startup logic is more than a trivial command, move it into a mounted script
  or a clearly delimited block instead of a long inline shell fragment.
- Avoid inline JSON heredocs in manifests when quoting is fragile; write an
  explicit file first or use an encoded payload that is decoded at runtime.
- Verify any startup-time API calls have bounded retries and do not block the
  main container forever.

### Argo CD, External Secrets, and identity wiring

- Applications should reference stable secret names rather than direct ad hoc
  secret generation.
- `ExternalSecret` resources should always define `spec.target.name` and
  `spec.target.creationPolicy`.
- If a secret key is consumed by another app, make the mapping explicit in the
  `ExternalSecret` template or `data` block rather than relying on inherited
  upstream key names.

### Cluster add-ons and controllers

- Check whether the upgrade introduces new CRDs, controllers, RBAC, or sidecars.
- Confirm Argo CD has an application path for every new cluster-scoped
  dependency.
- If manifests are vendored from upstream, note the upstream source and version
  in a local `README.md`.

## Minimal smoke-test standard

Before merging an upgrade, verify the affected workload has a clear answer for
these runtime checks:

- the workload becomes Ready
- liveness and readiness probes pass with the intended probe type
- required `ExternalSecret` targets exist with the expected secret keys
- outbound egress still matches the workload's real dependencies
- new controllers or CRDs required by the upgraded app are present in Git

## Repo guardrails

CI now runs `tools/ci/validate-runtime-contracts.py` in addition to
`kubeconform`. The validator is intentionally narrow and currently blocks:

- HTTP probes against `/metrics`
- HTTP probes against `/wp-json/wp-site-health/v1`
- deprecated node-exporter `--collector.filesystem.ignored-mount-points`
- `ExternalSecret` manifests without explicit target name and creation policy

When a new regression pattern shows up more than once, add it there instead of
keeping the fix as tribal knowledge.
