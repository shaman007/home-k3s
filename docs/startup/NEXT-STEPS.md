# Prepared dependency packages

2026-11-13. **Local preparation only; no commit, push, live patch, rollout,
silence, Job cancellation or data change.** The reported unexpected reboot was
the workstation, not the Kubernetes cluster. Existing Longhorn and
report-gate preparation is retained and extended here.

The initial Longhorn/report-gate foundation is now present in repository HEAD
as `b25a12b9`. No Git mutation was performed by this preparation; the extensions
described here remain uncommitted. Do not revert or overwrite that foundation.

## Review artifacts and reproduction

```sh
python3 tools/bootstrap/prepare_dependency_batch.py --output /tmp/dependency-review-NEW
python3 tools/bootstrap/prepare_cron_gate.py --job all > /tmp/report-dependency-candidates.yaml
```

The batch output directory must be new and outside the repository. Each package
has complete candidate manifests at their eventual relative source paths;
`index.json` records original source hashes. Regenerate after any upstream source
change rather than copying an old full manifest over newer work. No generator
contacts Kubernetes, changes active files or stages Git changes. Script ConfigMaps
are immutable and content-addressed; retain old versions while any live Pod/Job
still references them, including during rollback.

Prepared local review tree: `/tmp/home-k3s-dependency-review-20261113`; report candidates:
`/tmp/startup-report-gates-final.yaml`. These `/tmp` artifacts are expendable;
tracked generators and tests are the reproducible source.

| Order | Package | Prepared behavior | Required decision/acceptance before deployment |
| --- | --- | --- | --- |
| 1 | [Longhorn direct S3](../migrations/longhorn-internal-s3/README.md) | Conditional endpoint-only Secret patch and inverse patch; existing Service/policy | Accept cluster-only HTTP; signed existing-bucket read/list; engine paths; disposable backup and isolated restore |
| 2 | `observability`: Loki | Direct S3 Service; narrowly scoped bidirectional policies; same bucket/schema/retention | Accept internal HTTP; historical queries, ingestion and object reads after rolling Loki |
| 3 | `observability`: Thanos | ESO template overrides only endpoint/insecure in the existing S3 config; original OpenBao source retained | Verify source type is S3, actual ESO rendering and signed access; separately authorize sequential client rollouts, including shared Prometheus Pod |
| 4 | `mail` | Existing permissions init → exact Valkey PONG → Rspamd; remove old Redis-shutdown wait from Valkey | Confirm legacy Redis absent; accept Rspamd remaining unavailable while Valkey is down; maintain explicit existing Postfix fail-open policy |
| 5 | `mail-training` | Wait up to 300 seconds for Rspamd HTTP200, then existing trainer; otherwise skip before starting private Dovecot/reading mail | Review one-hour deadline; observe next scheduled training without injecting mail or cancelling an active Job |
| 6 | `nextcloud-cron` + report gates | Native SQL/ACL-Valkey/maintenance checks for cron; Loki/Ollama API checks for three reports | Check stale-report detection, runtime limits and actual mounted-PVC permissions; no skipped run counted as useful completion |
| 7 | `karakeep` | s6 workers wait for Chrome and Meilisearch; no Pod init wait for same-Pod Chrome | Accept gating the entire worker service, not only crawler/search; validate s6 mount/startup and signal behavior in isolation first |

Do not combine these into one rollout. For each selected package, review source
diffs, publish only after the user requests a commit, observe CI/Code Scanning,
then perform only the separately authorized live transition. A local candidate
does not authorize a restart or even a server-side dry-run. Repository prohibition
on `kubectl apply` still applies.

## Observability details

Loki currently uses public S3 through Traefik. The candidate changes exactly
`loki.storage.s3.endpoint` and `insecure`, retaining all other values and the
existing Secret references. New egress and SeaweedFS ingress rules permit only
selected Loki/Thanos Pods to TCP8333. Existing public-route policy remains during
transition for straightforward rollback; the configured client has no fallback
endpoint. NetworkPolicy source IP behavior must be checked from actual clients.

Promotion order is explicit because these files belong to different Argo apps:
publish/deploy **only the three new NetworkPolicies first**, verify the direct
path from current client namespaces/Pod labels, then promote Loki's values and
accept it before touching the Thanos ExternalSecret. An app-of-apps sync does not
provide a cross-Application readiness barrier. Do not copy the entire candidate
tree into active sources and assume apply ordering will make it safe.

Thanos `monitoring/thanos-objstore-secret` is ESO-owned. Do **not** patch its data
directly: ESO would overwrite that change. The candidate keeps remote property
`monitoring/objstore.yml`, renames the intermediate fetched key to `source`, and
uses v2 `fromYaml`/`set`/`toYaml` to preserve the complete config while changing
the S3 endpoint and HTTP flag. `mergePolicy: Replace` exports only `objstore.yml`,
not the intermediate raw key. No source credentials are read, saved or rewritten
by this preparation. A synthetic fixture is rendered by real Helm Go/Sprig to
check semantic credential preservation, including quoting/newlines and unrelated
options. **This is not a live ESO engine test.** Confirm current source type S3
and schema before enabling; malformed/mismatched source is a stop condition.

ESO documents the v2 functions and missing-key behavior in its
[official templating guide](https://external-secrets.io/latest/guides/templating/).
Its `fail` helper is unavailable, so the candidate does not use Helm-only `fail`
or `required` functions. Real reconciliation must be observed before rolling
clients. A non-S3 or non-mapping source is deliberately rejected using a fixed
`mustFromJson` error (ESO lacks `fail`), so it cannot silently publish a malformed
replacement config. The Go/Sprig test includes those rejection cases. Never print
rendered Secret data or template debug values.

Thanos clients do not gain a new mandatory startup gate. Prometheus must continue
collecting when S3 is unavailable. Updating a mounted config does not demonstrate
the running client has reloaded it: verify store gateway, compactor and sidecar
individually. Sidecar shares `prometheus-deployment`; a restart interrupts local
monitoring and needs an explicit maintenance window. Do not automatically restart
all three or add Reloader triggers that defeat staged acceptance. Querier does not
read S3 directly and gets no S3 policy/dependency.

The objstore Secret is shared by all three clients: its projection can update
all mounted files, even without a rollout. Verify each binary's reload behavior
and any existing Reloader/watch annotations before promoting that template. The
proposal does not promise a per-client switch barrier for a shared live Secret.
If that is required, prepare per-client config Secrets first in a separate step.

Rollback Loki by restoring its two transport values; rollback Thanos by restoring
the original ExternalSecret source mapping/template, waiting for the old target
Secret to reconcile, and rolling only clients already switched. Keep credentials,
bucket contents, local TSDB/WAL and index/data PVCs. Remove new policy permissions
only after all consumers use the old route and acceptance succeeds. The public
route remains usable unless the original underlying DR failure is still present.

## Mail details

The Valkey candidate removes **only** `wait-for-redis-shutdown`; all main
containers, volumes, Service and persistence args remain. Rspamd uses the already
required Valkey image as its native CLI init, not a new bootstrap image. The
current image contains `valkey-cli`, `timeout` and `sh`; the gate requires exact
PONG plus exit0 and suppresses driver output. Each invocation is bounded to 300 seconds
plus process termination overhead; Kubernetes can retry failed init indefinitely.

Postfix/Dovecot/Unbound entrypoints and configuration remain unchanged. In
particular `milter_default_action=accept` is a Postfix setting and is not changed
to reject/defer. A startup-only Valkey check does not prevent filtering bypass on
later Rspamd failure. That ongoing mail acceptance/delivery policy needs a separate
explicit decision; do not silently harden it while deploying a gate.

The trainer uses its existing curl and image, does not follow redirects or use
environment proxies, and requires HTTP200 from the existing Rspamd ping endpoint.
This is availability, not proof that a learning request is authorized. Its original
training script continues to check actual operations before deleting learned
messages. No messages were read, submitted, learned or deleted during preparation.

Roll back through Git to the original Rspamd/Valkey/trainer commands and mounts;
leave all mail/queue/Valkey PVCs and Secrets intact. Old script ConfigMaps are
removed only after no referenced Pod/Job remains. Never cancel a running training
or bookmark-sync Job as part of this transition without separate authorization.

## Karakeep details

Observed image: `karakeep:0.34.1`, web imageID
`sha256:69ae5315c618b7c14c1af3e34c6e211acdb231793af424ecd1cab0b70691d987`.
Its Node 24.22.1 supports `process.execve`. Inspected s6 worker runner:

```sh
#!/command/with-contenv sh
cd /app/apps/workers;
exec node dist/index.js
```

The candidate replaces only that worker-service run file with a ConfigMap mount,
leaving web, migration service, Chrome, SQLite/PVC, OIDC and Ollama configuration
unchanged. The native Node probe requires Chrome's JSON debugger URL and Meili's
`status: available`, bounds DNS/headers/body with a total request timer, then
execves the original worker process. Failure exits75 so s6 can retry this service.
Reinspect any changed imageID: a mutable tag or new chart may change s6 paths and
startup contracts. Source generation refuses a different version/entrypoint.

Tradeoff: one s6 service contains crawler, search, inference and other workers.
This proposal delays all of them while either selected provider is down; it does
not claim isolated per-queue gating. It adds no unconditional wait for Ollama/SSO.
User approval of that tradeoff and an isolated full s6 startup test remain pending.
Without that acceptance, keep the original worker runner and rely on existing
per-job retries; do not deploy the candidate merely because HTTP unit tests pass.

Rollback the worker Deployment to the previous mounts/template, retain database
and service state, and retire only unused script ConfigMaps. Do not clear or
requeue existing tasks, repair bookmarks or restart a healthy provider as a test.

## Work deliberately left for authorization or a separate design

* All live endpoint changes, patches, restarts, silences, signed backup tests,
  restore tests, and commits are untouched. Independent recovery copies of S3
  credentials/CA material remain unverified; no sensitive export was attempted.
* [CronJob catalogue](cronjobs/catalog.yaml) covers the 31 observed schedules.
  Backup, token-renewal and safety jobs retain fail/report behavior. OONI must
  measure outages rather than wait for Internet health. No controller-owned
  Longhorn CronJob is rewritten.
* `bookmarked-media-sync` has real work in an init container and another ordinary
  container. A shared skip marker plus guards on **every** subsequent work stage,
  or a single coherent runner, needs separate design. A successful init alone
  must never release uploads after a dependency failure.
* Matrix's unused nginx API proxy still points at Service port6167 instead of
  exposed8448. Public ingress already sends API traffic directly to8448. A
  cleanup/removal choice can eliminate that unused startup edge, but no active
  route is changed here.
* Open WebUI/SSO and optional integrations need outage/retry checks; no global
  model/identity barrier is inferred merely from env configuration. Prometheus's
  shared sidecar/Secret coupling needs a separate design before true independent
  monitoring bootstrap can be claimed.
* A read-only Argo snapshot showed five Healthy/OutOfSync apps whose only drift
  was retired `vault-pki-renewer` RBAC/CronJob requiring prune. This was not caused
  by a cluster reboot and is unrelated to these candidates; no resource was
  deleted and no automatic prune/cleanup was requested.

## Local checks

The repository unit suite includes native PHP/Node/shell fixtures, real HTTP
failure/redirect/body-timeout cases, SQL/Valkey fixture checks, original work exit
status, no-work-on-skip, current conditional DR cycle and proposed acyclic route,
versioned ConfigMap references, no active-source writes, preserved app entrypoints
and synthetic Thanos credential preservation. Native/local checks do not prove
live admission, login, mail delivery, backup validity or a full cluster cold boot.

Final local acceptance: **731 tests, OK with 21 skips**; Ruff, Pylint and Bandit
passed on the changed Python sources/tests. Native PHP/Node/shell syntax checks
passed. The candidate trees contain 21 Kubernetes documents:19 stock objects pass
strict kubeconform schemas, and the two CRD objects pass the currently installed
Application/ExternalSecret schemas read without mutation. Resource checks cover 13
containers with tracked namespace defaults and no new errors. Pinned Loki
chart 7.6.0 was rendered locally and both common/ruler S3 configurations resolve
to the direct HTTP endpoint. No published CI/Code Scanning run exists for these
uncommitted extensions, and none of these checks substitutes for live acceptance.
