# Prepared dependency packages

2026-11-13. **Local preparation only; no commit, push, live patch, rollout,
silence, Job cancellation or data change.** The reported unexpected reboot was
the workstation, not the Kubernetes cluster. Existing Longhorn and
report-gate preparation is retained and extended here.

The initial Longhorn/report-gate foundation is in `b25a12b9`; the preparation
extensions were subsequently committed and published as `69bc19bc`. Those commits
do not activate the candidate packages. Do not overwrite newer source changes
when promoting a generated candidate.

Subsequent update: the Longhorn endpoint-only cutover was separately authorized
and completed; see [the execution record](../migrations/longhorn-internal-s3/EXECUTION.md).
All other candidate packages remain inactive. New backup/restore testing is not
included in that completed authorization.

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
| 1 | [Longhorn direct S3](../migrations/longhorn-internal-s3/README.md) | Endpoint active; signed reads, full metadata match, controller polls and small GeoIP-PVC full backup passed | Isolated GeoIP restore to new PVC/hash comparison passed; full cold bootstrap remains untested |
| 2 | `observability`: Loki | Direct S3 Service; narrowly scoped bidirectional policies; same bucket/schema/retention | Active and accepted; publish matching sources and remove maintenance pause |
| 3 | `observability`: Thanos | ESO template overrides only endpoint/insecure in the existing S3 config; original OpenBao source retained | Active and accepted with isolated targets; Prometheus preserved; next natural upload pending |
| 4 | `mail` | Valkey + Unbound + ClamAV → Rspamd → Postfix; independent Dovecot provides SASL/LMTP | Superseded by [complete mail package](mail/README.md): deployed by 32517070 with tempfail/AV soft-reject policy; isolated SMTP failure tests pending |
| 5 | `mail-training` | Wait up to 300 seconds for Rspamd HTTP200, then existing trainer; otherwise skip before starting private Dovecot/reading mail | Review one-hour deadline; observe next scheduled training without injecting mail or cancelling an active Job |
| 6 | `nextcloud-cron` + report gates | Native SQL/ACL-Valkey/maintenance checks for cron; Loki/Ollama API checks for three reports | Check stale-report detection, runtime limits and actual mounted-PVC permissions; no skipped run counted as useful completion |
| 7 | `karakeep` | Prepared: separate Chrome Deployment/Service; s6 workers wait for Chrome and Meilisearch | Whole-worker tradeoff accepted; real s6 and separate-container CDP/DOM passed locally; publish and verify rollout next |

Do not combine these into one rollout. For each selected package, review source
diffs, publish only after the user requests a commit, observe CI/Code Scanning,
then perform only the separately authorized live transition. A local candidate
does not authorize a restart or even a server-side dry-run. Repository prohibition
on `kubectl apply` still applies.

## Observability details

The [runtime graph](observability/README.md) separates storage prerequisites from
optional query/delivery links. No application startup gate on Grafana/Loki/Thanos
was introduced. Stage-one policies were published and verified at `02452391`.

The [executed transition](observability/EXECUTION.md) moved Loki, store gateway,
compactor, then sidecar to direct SeaweedFS S3. Store/compactor have independent
ESO targets; the original shared target switched for sidecar only after those
clients were accepted. Actual ESO output changed only endpoint/insecure and kept
all credentials/other fields, with the original OpenBao source unchanged.

Only the sidecar process restarted in the shared Pod; Prometheus containerID,
start time and zero restarts were preserved, while sample counters increased.
Historical/fresh Loki reads and a four-day Thanos query passed. A new sidecar
block upload did not occur in the window and remains a natural follow-up check.

Source changes await publication. Only `loki` and `thanos` have temporary
skip-reconcile annotations; remove them after desired Git matches live. All
created maintenance silences were explicitly expired. Rollback order and
non-secret scratch evidence are documented in the execution record. Keep all
S3 objects, TSDB/WAL and PVCs; the old public route remains available for rollback.

## Mail details

The canonical [mail package](mail/README.md) replaces the earlier Valkey-only
proposal. It uses native Perl from each existing application image, with
protocol-level checks, consumer init and dependency-aware readiness. Local
liveness and all data/Secret mounts remain unchanged. The obsolete Redis shutdown
wait is removed from Valkey; Dovecot has no Valkey dependency.

The user explicitly selected temporary deferral without bypassing failed
filters. The prepared source therefore changes Postfix to milter tempfail and
adds Rspamd soft reject on CLAM_VIRUS_FAIL, preserving actual-virus reject.
The user chose automatic rollout for 32517070; these settings are now active.
See its execution record. The local diagnostic-loop fix is not yet deployed;
the reference staged plan remains available for later provider transitions.

The trainer uses its existing curl and image, does not follow redirects or use
environment proxies, and requires HTTP200 from the existing Rspamd ping endpoint.
This is availability, not proof that a learning request is authorized. Its original
training script continues to check actual operations before deleting learned
messages. No messages were read, submitted, learned or deleted during preparation.

Use the mail package rollback plan; do not silently restore fail-open or the
retired Redis wait. For CronJob rollback restore the original trainer command;
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
leaving web, migration service, SQLite/PVC, OIDC and Ollama configuration
unchanged. Chrome is prepared as a separate Deployment/ClusterIP Service. The native Node probe requires Chrome's JSON debugger URL and Meili's
`status: available`, bounds DNS/headers/body with a total request timer, then
execves the original worker process. Failure exits75 so s6 can retry this service.
Reinspect any changed imageID: a mutable tag or new chart may change s6 paths and
startup contracts. Source generation refuses a different version/entrypoint.

Tradeoff: one s6 service contains crawler, search, inference and other workers.
This proposal delays all of them while either selected provider is down; it does
not claim isolated per-queue gating. It adds no unconditional wait for Ollama/SSO.
The user accepted gating the whole worker pool. Full isolated s6 startup verified
that migrations and web start while providers are unavailable, one ready provider
does not release workers, both ready providers release the real worker process,
and s6 stops without SIGKILL. A separate-container Patchright CDP/DOM check also
passed. These are local checks; no Karakeep rollout has been performed.
See [the transition plan](karakeep/README.md).

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

## Mail package follow-up

The canonical [mail startup/readiness package](mail/README.md) supersedes the
narrow historical Valkey-only proposal above. The baseline was deployed by 32517070; see its execution record and the local
diagnostic-loop follow-up.
The controlled rollout must account for single-replica Recreate and ConfigMap
Reloader; publishing all changes without the planned SMTP window is not the
acceptance procedure.
