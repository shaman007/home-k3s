# Kubernetes audit detections

The `kubernetes-audit` Argo application runs one dedicated Grafana Alloy collector
per control-plane node in `kube-system`. It tails the existing Talos audit file,
exports bounded metrics to Prometheus, and sends selected, reconstructed records
to Loki. The four detection alerts use the existing email/Telegram receiver.
No Falco kernel probe, admission webhook server, Kubernetes API token, new Secret,
Talos machine-config change or API-server restart is required.

## Data and admission boundaries

Keep the existing Talos audit policy at **Metadata**. Three native
`ValidatingAdmissionPolicy` objects add only computed audit facts:

- `homelab-audit-bindings/grant`: role kind/name when a binding is created or its
  role/subjects change. Every such binding is reviewed, including bindings to
  arbitrary custom roles; role name alone cannot establish effective privilege.
- `homelab-audit-roles/dangerous`: changed roles containing wildcard verbs,
  resources or API groups, or `bind`, `escalate`, or `impersonate` verbs.
- `homelab-audit-pods/privileged`: a Pod has a privileged regular, init or ephemeral
  container. The policy also observes ephemeral-container updates.

All validations are literal `true`, bindings use only `Audit`, and failures are
ignored. They do not block, mutate, or grant access. PATCH requests are evaluated
against the resulting object, so strategic/merge/JSON patch formats do not need
separate body parsing. Unchanged RBAC role/subjects/rules do not generate facts.
The API server must support `admissionregistration.k8s.io/v1` native policies;
the deployed Kubernetes 1.37 API accepted the manifests in server dry-run.

The collector also reads PodSecurity `audit-violations` to recognize privileged
attempts rejected before native validation. Current Talos defaults enforce
baseline and audit restricted, with kube-system exempt; the native Pod policy
still observes kube-system. Rejections before either admission path cannot carry
these semantic facts. This is audit visibility, not proof of exploit success.
Static/mirror Pod creation and direct node actions do not establish who initially
started a host process; runtime detection remains a separate task.

Do **not** enable Request/RequestResponse auditing for Secrets or Pod bodies.
Only the following fields leave the collector: audit ID, audit timestamp,
detection, outcome, original/impersonated identity, resource/subresource,
namespace/name, verb, response code, and role reference. Raw request/response
objects, request URI, exec arguments, user agent and annotation contents are not
forwarded. Existing node audit files still contain the original Metadata events,
including request URIs; this collector does not expand their contents or copy
them into a second raw archive. Keep the node files restricted to root.

The collector mounts only `/var/log/audit/kube` read-only and a dedicated writable
cursor directory `/var/mnt/kubernetes-audit-positions`. It runs as UID 0 to read
root-owned audit files, with all capabilities dropped, no privilege escalation,
read-only root filesystem, RuntimeDefault seccomp, and no ServiceAccount token.
The cursor directory contains positions, not audit bodies. First installation
starts at EOF rather than paging on old history. Positions survive Pod recreation.
Corrupt positions are skipped instead of replaying the full audit history; the
stale telemetry alert then exposes the loss of collection. After downtime,
records still in the active file can be resumed; rotated-away backlog may be lost.

## Detection coverage

| Alert | Detection | Scope |
| --- | --- | --- |
| KubernetesUnexpectedSecretRead | `secret_read` | get/list/watch by an unexpected identity, plus failed access by expected identities |
| KubernetesDangerousRBAC | `dangerous_rbac` | new/changed bindings and dangerous role changes described above |
| KubernetesSensitivePodExec | `sensitive_exec` | exec/attach/portforward in openbao, keycloak, argocd, harbor, bitwarden, mail, monitoring; also Pod names matching postgres/postgresql/mysql/mariadb/redis/valkey components |
| KubernetesPrivilegedPod | `privileged_pod` | privileged containers reported by admission audit facts or PodSecurity violations |

Secrets exceptions are explicit identity + namespace + verb conditions in
`config-map-audit-alloy.yaml`. They cover observed controller caches and node
get/watch operations, not all `system:` identities. Cluster-wide controller
exceptions apply to list/watch only; direct gets remain visible. Namespace-scoped
exceptions do not apply across namespaces. Human administrators are not excluded.
Impersonated requests and failures never inherit these exceptions. Review changes
against actual audit metadata and RBAC; do not silence whole namespaces to remove
noise. These exceptions identify expected access, not protection from a compromised
controller abusing its existing cache.

Open watches and streaming exec use ResponseStarted; other requests and errors
use ResponseComplete. This avoids double-counting each request when it finishes.
Denied exec attempts and admission rejections are useful signals too. HTTP 401/403
are `denied`; other errors (for example a nonexistent Secret) are `failed`. Dry-run
requests are explicitly marked `outcome="dry-run"`; they must not be described as
actual grants or running privileged Pods.

Each detection sets `homelab_audit_last_detection_timestamp_seconds` with its
actual audit timestamp. Prometheus alerts for fifteen minutes after a single event,
including a first-ever event; it does not rely on a lazily-created counter delta.
Related events are grouped into existing Alertmanager notifications. Counters are
also exported for volume. Metric labels contain detection/outcome/node/job, not
users, object names, namespaces or command arguments. Collector restart resets
its in-memory metrics; already stored Loki records remain available.

`KubernetesAuditTelemetryStale` checks real file activity, independent of whether
any detection fires. Missing metric for five minutes, or a heartbeat more than
five minutes old for another five minutes, raises a warning. `KubernetesAuditNodeMissing`
checks every control-plane against healthy targets; one healthy collector cannot
hide a missing sibling. Existing target/inventory alerts also cover scraping.
Loki delivery is separately observable through Alloy/Loki metrics: file activity
and a firing metric alone do not prove the record reached Loki.

## Validation and rollout

Local verification uses the installed production tools, without Docker builds:

```sh
python3 tools/audit/check_admission.py /path/to/kyverno
ALLOY_BINARY=/path/to/alloy python3 -m unittest tests.test_kubernetes_audit
python3 -m unittest tests.test_argocd_projects
python3 tests/run_monitoring_alert_tests.py /path/to/promtool
```

The real pipeline test uses only fabricated audit records and a loopback Loki sink.
It tests all four classifications, namespace-bound exceptions, impersonation,
streaming-stage deduplication, dry-runs, timestamp gauges and removal of fabricated
secret-bearing fields. It uses the host's existing `libsnappy` to inspect the
actual compressed Loki output. The CEL check evaluates the shipped annotation
expressions with Kyverno against normal/privileged regular, init and ephemeral
containers, empty/safe/dangerous roles, and custom-role bindings.

Publish all task changes together. The root Argo app first grants observability
permission to manage native admission policies, then discovers the new application.
Loki and monitoring network-policy applications own the two cross-namespace
NetworkPolicies in their existing directories. Prometheus discovers collectors
in kube-system by the exact app/port labels. Publishing the rules without the
collector intentionally raises missing-coverage alerts.

After publication verify:

1. The exact published revision is Synced/Healthy in kubernetes-audit,
   kubernetes-prometheus, loki-network-policy and monitoring-network-policy.
2. DaemonSet desired/current/ready match all control-plane nodes, each scrape is
   up, and audit heartbeat timestamps advance on every node.
3. All four detection rules plus both telemetry rules are loaded and healthy.
4. Perform a metadata-only lookup of a deliberately nonexistent Secret (no secret
   values), an innocuous version command via exec in monitoring, and server dry-run
   dangerous-role/binding and privileged-Pod requests. Never create an actual
   privileged Pod or grant actual rights merely to test monitoring.
5. Find the sanitized records in Loki, corresponding firing alerts in Prometheus
   and Alertmanager, and confirm Telegram acceptance plus actual email reception.
   A dry-run manifest validation before publication proves none of this runtime path.

For investigation use Grafana Explore, Loki query:

```logql
{job="kubernetes-audit", detection="secret_read"} | json
```

Change `detection` to `dangerous_rbac`, `sensitive_exec` or `privileged_pod` and
filter node/outcome as needed. The JSON contains actor, target, code and audit ID.

Rollback through GitOps by removing the new application, native audit policies,
collector/scrape/alerts and the two narrowly scoped network allowances together.
Leave the original Talos audit policy and existing monitoring components intact.
The cursor directory may be retained for a later re-enable; no raw logs are added
there. Removing audit-only policies changes visibility, not admission decisions.
