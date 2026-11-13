# Remaining startup dependency coverage

Observed 2026-11-13. This is a structural census of **149 continuous workloads and
31 CronJobs in 54 namespaces**, followed by detailed checks of the candidates
below. It is not an assertion that every opaque Secret, chart, script and application
entrypoint has been semantically audited. The original census/preparation
was read-only; rollout status below is updated only after separately authorized
execution. Mastodon native cutover is now recorded as completed.

Reproduce the sanitized census (does not read Kubernetes Secret objects):

```sh
kubectl get deployments,statefulsets,daemonsets,cronjobs,services,externalsecrets -A -o json \
  | python3 tools/bootstrap/inventory_startup.py > /tmp/startup-reference-inventory.json
```

The inventory recognizes nested database URL names, `SERVER`, `ADDR` and
`ENDPOINT`, including `BW_DB_SERVER`, `SYNC_*__DATABASE_URL`, and `MONGO_ENDPOINT`.
It exports hostnames/references, never URL credentials, paths, query strings or
raw env values. ConfigMap/Secret `envFrom` and file content remain opaque to this
script; selected source configurations were reviewed separately. CronJobs are
included as scheduled consumers, not Service backends or reboot startup phases.
Completed one-off Jobs are excluded to avoid confusing historical work with boot.

## SQL gates deployed after the original census

* **Bitwarden:** dedicated PostgreSQL `bw` → Bitwarden Lite. Existing permissions
  init stays first, followed by authenticated read-only `SELECT 1`; original Lite
  entrypoint owns schema migration. No wait for SMTP, Yubico, public ingress or
  external installation services is introduced. Data and key PVCs are untouched.
  Source: `bitwarden/deployment-bitwarden.yaml`, `stateful-set-bitwarden-postgres.yaml`.
* **Firefox Sync:** MariaDB `syncstorage` **and** `tokenserver` → syncserver. Both
  schemas must accept read-only SQL as the existing app user. Credentials remain
  a reference to `firefox-sync-env/MYSQL_PASSWORD`, never root credentials. Original
  tokenserver migration flag and heartbeat probes stay unchanged. No wait for the
  external Mozilla Accounts/OAuth service or the public self URL is introduced.
  Source: `firefox-sync/deployment-firefox-sync.yaml`, `deployment-mariadb.yaml`.

All three exact native probes succeeded against current services, including both
Firefox databases, without writes. This does not prove future init Pod admission,
entrypoint migrations or actual login/vault unlock/bookmark sync after rollout.
Bitwarden namespace min memory32Mi was verified live; Firefox namespace currently
has no LimitRange. New gates request32Mi and limit128Mi. Existing Nextcloud gates
remain64Mi. Tests compare gate requests with tracked namespace minima.

`wait_mysql.sh` is separate so adding a MariaDB client does not alter shared
script checksums or restart the six already prepared/deployed app stacks. Existing
ConfigMaps/workloads outside Bitwarden and Firefox are unchanged in this package.
Native CLI login/query failures and wrong SQL replies keep the gate closed; logs
contain only fixed stage/result/duration. Each init name identifies the schema.

## Further dependency work: distinct from an unconditional SQL gate

| Stack | Source-grounded dependency | Correct next step |
| --- | --- | --- |
| Mastodon | PostgreSQL + Valkey, pre/post-upgrade migration hooks; chart1.2.8 has no init/command extension | Native cutover completed with web-init migration owner and schema gates; initial schema was already applied. Legacy chart is retained only for rollback review. |
| Karakeep | Local SQLite (`/data/db.db` present), separate Meilisearch; Chrome in same Pod; Ollama and OIDC integrations | Check search indexing/worker retry semantics separately. An init waiting for same-Pod Chrome deadlocks, because ordinary containers start after all init containers. Gate Chrome-dependent worker entry only if required, not the entire Pod. |
| Mail | Valkey → Rspamd state/greylisting; Unbound → DNS consumers; Postfix → Rspamd milter and Dovecot LMTP | Separate mail readiness/failure-policy work. `mail/config-map-main-cf.yaml` currently has `milter_default_action=accept`; a startup-only check cannot prevent filtering bypass after a later Rspamd outage. Do not silently change accept/reject or delivery policy. |
| Matrix/Synapse | SQLite `/data/homeserver.db`; nginx serves well-known discovery | No external SQL gate. Nginx contains stale upstream `matrix:6167`, but Service exposes8448→6167. Live requests from nginx:6167 fails,8448/health=200. Public `/_matrix/client/versions`=200 because ingress routes API directly to Service8448. Fix/remove stale unused proxy separately; no current public API outage inferred. |
| Open WebUI | Local data PVC; Ollama, SearxNG, ComfyUI, terminal integrations | Preserve UI startup and test each feature's unavailable-provider behavior; no global model/server barrier from configuration presence alone. |
| Immich ML | ML is separate HTTP service; manifest copies DB/Redis envs, but current ML config module has no such settings | Do not infer an ML SQL dependency solely from copied envs. Server is already gated; ML availability is a feature check. |
| Loki / Thanos / Grafana | Loki source points to S3; caches, object storage, query components and data sources have different availability needs | Audit component-specific readiness/backoff separately. Logging/metrics consumers must not become prerequisites for the providers they observe. |
| Other scheduled consumers | DB/API/backup and indexer prerequisites per CronJob | Retries/deadlines per execution, not a cluster-wide reboot phase. |

No new external DB dependency was established for Matrix/Synapse, Karakeep,
SearxNG or Open WebUI. This does not assert all their integrations are optional:
for example login may require Keycloak even while the web process can start.
Remaining opaque application configs need targeted inspection before a hard gate.

## Complete namespace census

Counts are continuous / scheduled. “Structural review only” means inventory of
workloads, declared images and object references; it is not proof of independence.
“Active gate” describes the previous rollout, not a fresh cold-start test here.

| Namespace | Count | Classification | Decision / remaining work |
| --- | --- | --- | --- |
| argocd | 8 / 0 | Infrastructure | GitOps control plane; structural review only. |
| backup-rsync | 1 / 0 | Persistent backup service | Deployment, not a CronJob; backup target access is task-specific. |
| bastioncam | 1 / 0 | App | Structural review only. |
| bitwarden | 2 / 0 | App | Active PostgreSQL gate; no Valkey configured. |
| ca-scanner | 1 / 0 | App | Structural review only. |
| cert-manager | 4 / 0 | Infrastructure | Certificate management; structural review only. |
| clamav | 1 / 0 | Infrastructure | Antivirus; structural review only. |
| comfyui | 1 / 0 | App | Structural review only. |
| connectivity-exporter | 1 / 0 | Infrastructure | Monitoring; structural review only. |
| convertx | 1 / 0 | App | Structural review only. |
| crowdsec | 2 / 0 | Infrastructure | Security; structural review only. |
| dawarich | 4 / 0 | App | Active gate. |
| external-secrets | 3 / 0 | Infrastructure | Secrets management; structural review only. |
| firefox-sync | 2 / 0 | App | Active read-only gates for both MariaDB schemas. |
| gpu-operator | 10 / 0 | Infrastructure | Hardware/Node management; structural review only. |
| harbor | 9 / 0 | Infrastructure | Container registry; structural review only. |
| headlamp | 1 / 0 | Infrastructure | K8s UI; structural review only. |
| hister | 1 / 0 | App | Structural review only. |
| i2pd | 1 / 0 | Infrastructure | Network; structural review only. |
| image-builder | 0 / 1 | Scheduled Job | Podman builder; structural review only. |
| immich | 4 / 0 | App | Active gate (server). |
| karakeep | 2 / 0 | App | Local SQLite + Meilisearch. Optional search/jobs must be audited before global gate. Init waiting same-Pod Chrome would deadlock. |
| keycloak | 2 / 1 | App | Active gate. |
| kube-system | 9 / 0 | Infrastructure | Core K8s components; structural review only. |
| kyverno | 2 / 0 | Infrastructure | Policy engine; structural review only. |
| lenka | 1 / 0 | Sandbox provider | Sandbox MySQL provider; no app consumer in inventory. |
| loki | 5 / 0 | Infrastructure | Observability; datasource readiness distinct from global app startup. |
| longhorn-system | 10 / 15 | Infrastructure | Storage/CSI; structural review only. |
| mail | 5 / 1 | App | Valkey->Rspamd, Unbound, Postfix/Dovecot. Audit failure/retry behavior separately; do not gate whole SMTP on feature dependencies. |
| mastodon | 5 / 2 | App | Native active with PostgreSQL/Valkey and schema gates; see mastodon-native/README.md. |
| matrix | 2 / 0 | App | SQLite; public API goes directly to Service8448. Nginx unused API proxy uses wrong6167. |
| mempalace | 1 / 0 | App | Structural review only. |
| metallb-system | 4 / 0 | Infrastructure | Load balancing; structural review only. |
| minecraft | 1 / 0 | App | Structural review only. |
| monitoring | 11 / 4 | Infrastructure | Grafana/Prometheus/Thanos; data sources and object store need component-specific readiness. |
| nextcloud | 4 / 1 | App | Active gate. |
| nllb | 1 / 0 | App | Structural review only. |
| ollama | 2 / 0 | App | Structural review only. |
| ooni | 0 / 2 | Scheduled Job | Network measurement; structural review only. |
| open-terminal | 1 / 0 | App | Structural review only. |
| open-webui | 1 / 0 | App | Local SQLite PVC. Ollama/search/ComfyUI/terminal integrations not unconditional boot. |
| openbao | 1 / 1 | Infrastructure | Secrets/Vault; structural review only. |
| opensearch | 1 / 0 | Infrastructure | Search/Logging; structural review only. |
| plex | 1 / 0 | App | Structural review only. |
| ripe-atlas | 1 / 0 | Infrastructure | Network measurement; structural review only. |
| searxng | 1 / 0 | App | No Redis configured; limiter disabled. |
| seaweedfs | 2 / 0 | Infrastructure | Object storage; structural review only. |
| spotify | 4 / 0 | App | Active gate. |
| stirling-pdf | 1 / 0 | App | Structural review only. |
| talos-backup | 0 / 1 | Scheduled Job | Backup task; structural review only. |
| traefik | 4 / 1 | Infrastructure | Ingress; structural review only. |
| unifi | 1 / 0 | Infrastructure | Network monitoring; structural review only. |
| wordpress | 4 / 1 | App | Active gate. |
| year | 1 / 0 | App | Structural review only. |

## Staged rollout and rollback

The Bitwarden/Firefox package described below has completed its gate rollout.
New inactive packages and remaining functional/deployment acceptance are indexed
in [NEXT-STEPS.md](NEXT-STEPS.md); the five new CronJob candidates are proposals,
not already-running gates.

Publish only after local review and green CI. Roll out Bitwarden first; observe
permissions init → SQL gate → Lite migration/startup, then authorized login/vault
unlock. Gate success alone does not prove these user operations. Then observe both
Firefox SQL gates → original migrations → heartbeat and an authorized sync check.
Bitwarden uses Recreate, so expect a short interruption. Never stop a live DB,
delete Secrets, inject failures or read vault data as part of this preparation.

Rollback only the added init/ConfigMap volume/checksum changes through Git/Argo,
retaining app entrypoints and any newer image/security changes. Remove orphaned
script ConfigMaps through their owner only after no Pod references them. No DB
restore, schema rollback, data deletion, PVC change or Secret rewrite is required.
Services can be satisfied by old Ready replicas during rolling updates; a warm
rollout is not a strict new-generation barrier or proof of a full cluster cold boot.
