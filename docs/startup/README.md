# Startup dependencies and readiness contract

Status: **Dawarich pilot source prepared for GitOps rollout**, 2026-11-13.
User authorized publishing the active pilot through ArgoCD; rollout verification
is pending their push. No manual cluster writes, global startup controller,
sync-wave changes or failure injection were performed.
The machine-readable [graph](dependencies.yaml) records provider → consumer
edges, criteria and source evidence. Its phases describe a possible partial
order, not an enforced cluster-wide barrier. Scope is core bootstrap and five
database-backed stacks: Dawarich, Immich, Mastodon, Nextcloud and Keycloak;
the remaining Applications are not audited exhaustively.

A broader read-only structural inventory covered **149 live workloads in 51
namespaces and 51 ExternalSecrets**. It records required Secret/ConfigMap/PVC
references, image origins, and literal service-host hints resolved through actual
Service selectors. The local report is `/tmp/startup-runtime-inventory.json`.
Reproduce it without exporting raw environment values or Secret contents:

```sh
kubectl get deployments,statefulsets,daemonsets,services,externalsecrets -A -o json \
  | python3 tools/bootstrap/inventory_startup.py > /tmp/startup-runtime-inventory.json
```

This inventory covers declared references across the cluster; it does not infer
mandatory process dependencies from opaque Secret/ConfigMap content, scripts or
third-party chart internals. Only five workloads expose service hints as directly
parseable literal environment addresses; the detailed graph supplements these
with inspected source for the selected stacks. Do not interpret missing hints as
proof of independence, or expand gates to all referenced services automatically.

## Main graph

```mermaid
flowchart TD
  API[Kubernetes API and node runtime] --> NET[Cilium and CoreDNS]
  NET --> LH[Longhorn and CSI]
  NET --> LB[MetalLB and FRR]
  CA[Original internal CA in etcd or independent backup] --> TLS[OpenBao backend TLS Secret]
  CM[cert-manager local CA issuer] --> TLS
  LH --> BAO[OpenBao Raft quorum and manual unseal]
  TLS --> BAO
  BAO --> SECRETS[Required missing application Secrets via ESO]
  LH --> HDB[Harbor own database and Redis]
  HDB --> H[Harbor core and registry]
  LB --> ING[Internal registry ingress on .212]
  ING --> ACCESS[Verified registry access]
  H --> ACCESS
  ACCESS --> DATA[Application DB and Valkey images on cache miss]
  LH --> DATA
  SECRETS --> DATA
  DATA --> APP[Application-specific startup gate]
  APP --> WEB[Web schema migrations and ready endpoint]
  WEB --> WORKER[Application worker]
```

External registry/DNS availability or preloaded bootstrap images are prerequisites
for the bootstrap components themselves. They must not wait for Harbor. Secret
materialization requires ESO/OpenBao **only when required target Secrets are
missing**; a normal restart with persisted Secrets does not need to wait for a
fresh ESO refresh. The diagram collapses per-namespace Secret nodes for clarity;
the implementation must never wait for every ExternalSecret in the cluster.

## Criteria, not just process counts

| Provider | Criterion to release its consumer | What is insufficient |
| --- | --- | --- |
| Kubernetes | API usable, etcd quorum, intended node schedulable | One answering API endpoint |
| Cilium/CoreDNS | Intended nodes Ready; target-namespace DNS and service/policy path work | DaemonSet desired count alone |
| Longhorn | CSI/manager available; required volume attaches and mounts | PVC `Bound` alone |
| OpenBao TLS | Original trust retained; backend leaf Secret valid with required SAN/key | Certificate object exists |
| OpenBao | Raft quorum, active leader, required members unsealed, verified internal health | TCP 8200 or Pod Running |
| ESO | Required Secret/keys exist; if absent, its own store and ExternalSecret reconcile | All ESO Pods Ready |
| Harbor access | .212 TLS/SNI, token exchange and authenticated private-image pull | `/v2/` HTTP response alone |
| Application PostgreSQL/MariaDB | Authenticated read-only `SELECT 1` against the configured DB | TCP connect or `pg_isready` |
| Application Valkey | Protocol PING → PONG with configured authentication | Open port 6379 |
| Schema | Application-owned schema/data migrations complete | Successful `SELECT 1` |
| Web | App-specific ready endpoint checks its essential services | Process started |
| Worker | Entry starts after local web/schema barrier; actual worker heartbeat/queues verified at rollout | Web readiness alone |

The generic criteria are design requirements, not a claim that every application
currently enforces them. Required DB usernames, databases and Secret references
must come from each application's actual configuration.

## Application branches verified in source and runtime

| Stack / namespace | Database Service | Cache Service | Additional functional dependencies |
| --- | --- | --- | --- |
| Dawarich | `dawarich-postgres:5432` | `valkey-dawarich:6379` | Photon geocoding; Keycloak login |
| Immich | `immich-postgres:5432` | `immich-valkey:6379` | Separate machine-learning service |
| Mastodon | `mastodon-postgres:5432` | `valkey:6379` with auth | SeaweedFS media; OpenSearch search; Keycloak login |
| Nextcloud | `mysql-nextcloud:3306` | `valkey:6379` | Collabora/antivirus/integrations need separate checks |
| Keycloak | `keycloak-postgres:5432` | No separate Valkey dependency found | Required for SSO feature of consumers |

These services and DB/cache manifests exist; readiness contracts outside the
pilot still need protocol-level validation. In particular, an environment
variable declaring an integration does not prove it is required for process boot.
Photon, ML, search and SSO are separate feature edges, not unconditionally global
startup gates. Whether a particular client performs blocking OIDC discovery
during initialization needs a separate check before treating SSO as optional.

## Remaining cycles and bootstrap exceptions

* Ordinary Longhorn volume attachment does not require S3. S3 is needed for backup
  restore. The observed-runtime recovery ring is Harbor images → SeaweedFS →
  Longhorn backup restore → lost Harbor volumes → Harbor. On this observation,
  live SeaweedFS still used Harbor images; commit `6f6ac885` breaks that image edge
  in Git, but its runtime rollout was not observed here. See graph edge kinds
  `observed-image`, `image`, and `recovery` rather than confusing desired and live state.
* SeaweedFS data is hostPath-backed, not a Longhorn PVC. Its storage must survive
  on its pinned node, and S3 credentials must have an independent recovery path.
* Harbor's certificate remains ACME HTTP-01 via public Traefik. A valid persisted
  `harbor-tls` Secret supports normal boot; missing/expired TLS requires the
  public challenge path. The local OpenBao CA does not need GoDaddy or Harbor.
* GoDaddy webhook, snapshot-controller, reporting and housekeeping images in
  Harbor are not prerequisites for local CA signing or existing-volume attach.
* Kyverno resource checks currently use audit/fail-open behavior; do not turn
  signature lookup into a new Harbor/bootstrap admission dependency.

## Dawarich pilot

Observed workload: one `Deployment/dawarich`, ordinary containers `dawarich`
and `dawarich-sidekiq`; dedicated PostgreSQL StatefulSet and Valkey StatefulSet.
Both target ExternalSecrets and their stores reported Ready. The app's current
image includes Ruby 4.0.9, bundled `pg` (libpq 180001) and `redis` 4.8.1; plain
`ruby -rpg` fails, so the candidate uses **`bundle exec ruby`**.

Existing web entrypoint creates a DB if needed, runs `db:migrate`, `data:migrate`
and `db:seed`, then starts Rails. Sidekiq entrypoint only waits for SQL login;
it has no schema barrier. Existing `/api/v1/ready` code checks `SELECT 1` and
Redis PING without depending on a running worker. A read-only request returned
HTTP 200 with `Host: localhost`; the candidate preserves that Host header.

The active Dawarich source and its reproducible candidate add:

1. After the existing volume-preparation init, a same-image init checks the
   configured DB with the existing Secret reference and read-only `SELECT 1`,
   plus Valkey PING. It never loads Rails or runs migrations.
2. PostgreSQL and Valkey must pass in the same iteration. Each operation is
   bounded to 5 seconds and each gate invocation to 300 seconds, retrying every
   5 seconds. Logs contain only fixed stage/result names and elapsed time.
3. Web keeps its original entrypoint and migration/seed behavior. A readiness
   probe uses its actual `/api/v1/ready`, not a guessed endpoint.
4. The Sidekiq command waits for that endpoint on **localhost**, then `exec`s
   its original entrypoint. Waiting via the Service would deadlock: the Pod's
   web readiness may not be enough to publish a Pod with a waiting worker.

Render for review outside the repository:

```sh
python3 tools/bootstrap/prepare_startup_gate.py --output /tmp/dawarich-startup-candidate.yaml
```

The default output contains a ConfigMap and the modified Deployment only,
**not the full application**, and stays outside the repository. An explicit
`--write-source` updates the two active `dawarich/` files locally; `--check`
verifies those files and is included in CI. The generator never contacts
Kubernetes. `dawarich/config-map-startup-gate.yaml` and the Deployment are now
included by the existing directory-based Argo application. A script checksum in
the Pod template makes later script changes trigger a rollout. DB/cache manifests and NetworkPolicies
are preserved; init uses the same Pod labels and existing allowed service paths.

Init waits delay application processes, not Pod creation, image acquisition,
networking or volume attachment. A failed gate exits nonzero; Kubernetes retries
it with backoff, so 300 seconds bounds one invocation, **not the whole Pod's life**.
The worker may similarly restart while a long migration is still running. This
does not re-arm a gate when an individual main container restarts in a surviving
Pod, and cannot guarantee dependency availability after the initial check.

No schema version check is added: the existing web migration owner remains
authoritative. Parallel replicas/multiple migration owners need a separate design;
the current single-Pod `Recreate` arrangement is the pilot boundary. Avoid DB/cache
liveness checks in the web process that would cause restart storms during outages.

## Verification and future rollout gates

Local tests cover SQL/auth failure, Valkey failure, timeouts, recovery, resource
cleanup, JSON log sanitization, the web barrier, graph references/acyclic normal
startup edges and preservation of the original workload. They do not prove an
actual staged cold boot. No DB/Valkey was stopped and no Secret was deleted.

CI restores Ruby in the CodeQL matrix (`build-mode: none`). The validation job
explicitly installs `/usr/bin/ruby` and syntax-checks repository `.rb` files before
running the unit suite, so Ruby behavior tests (including the existing Mastodon
importer tests) cannot silently skip because the interpreter is missing. Local
CodeQL analysis was not run; its result requires publishing the workflow changes.

After the user publishes this reviewed source, observe Argo synchronization,
init dependency checks, web migrations/readiness, then worker startup and normal
queue behavior. Production fault injection is not authorized: test provider
unavailability and recovery in isolation before broadening this pattern. The production application uses `Recreate`,
so rollout causes a short app outage. Roll back by restoring the original
Deployment command/probes/init/volume configuration, then retiring the unused
ConfigMap through its owner. No DB restore or data deletion belongs in rollback.

Argo waves order sync operations, not reboot of existing workloads. The current
Argo source does not provide an Application health customization for app-of-apps
dependency waiting. Strict cluster-wide startup with no dependent Pods requires
separate orchestration and reconciliation rules; this pilot intentionally does
not pretend to install it.
