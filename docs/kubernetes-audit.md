# Kubernetes audit detections

The `kubernetes-audit` Argo application runs one dedicated Grafana Alloy collector
per control-plane node in `kube-system`. It tails the existing Talos audit file,
exports bounded metrics to Prometheus, and sends selected, reconstructed records
to Loki. The four detection alerts use the existing email/Telegram receiver.
No Falco kernel probe, admission webhook server, Kubernetes API token or new Secret
is required. Talos kubelet mounts and the offsets directory-volume must be provisioned
using `talos/kubernetes-audit-mounts.yaml` on each control-plane before collection.

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
Apply the Talos patch one node at a time with `talosctl patch machineconfig
--nodes NODE --mode=no-reboot --patch @talos/kubernetes-audit-mounts.yaml`, verifying
node readiness and the ready directory-volume before proceeding. Existing kubelet
mounts are merged and must be preserved. This may restart kubelet, not the node.
Use scoped expiring maintenance silences and remove them after verification.

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
namespace/name, verb, response code, first source IP, and role reference. Raw request/response
objects, request URI, exec arguments, user agent and annotation contents are not
forwarded. Existing node audit files still contain the original Metadata events,
including request URIs; this collector does not expand their contents or copy
them into a second raw archive. Keep the node files restricted to root.

The collector mounts only `/var/log/audit/kube` read-only and a dedicated writable
cursor directory `/var/mnt/kubernetes-audit-positions`. Talos writes the audit files
as UID/GID 65534 with mode 0600, so the collector runs as that non-root identity,
with all capabilities dropped, no privilege escalation, read-only root filesystem,
RuntimeDefault seccomp and no ServiceAccount token. A root init container mounts
only the offsets volume and uses CHOWN/DAC_OVERRIDE to prepare its owner; it never
mounts audit or any other host directory. It does not follow symlinks. The Talos
patch exposes audit read-only to kubelet and provisions offsets as a directory-type
UserVolume on existing EPHEMERAL, without repartitioning or formatting disks.
Do not create arbitrary directories beneath the read-only `/var/mnt` mountpoint.
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

Secrets exceptions are reviewed entries in
`tools/monitoring/audit_secret_readers.json`, rendered into the actual Alloy
pipeline by `python3 tools/monitoring/generate_audit_exceptions.py`.
Do not edit the generated block or automatically learn exceptions from traffic.

- Every entry fixes an authenticated identity, namespace/scope and read verbs.
  Cluster informer exceptions cover only list/watch, not direct gets. Their
  required cluster-wide scope cannot distinguish abuse of that same informer.
- External Secrets direct gets are restricted to the exact namespace/name pairs
  of the reviewed ExternalSecret targets; namespace-local lists and the global
  list/watch informer are separate entries. New targets require an explicit
  source update. No resource permission is granted by an audit exception.
- Argo own-namespace informers, Kyverno reports, FRR, Traefik registry and Cilium
  operator use their exact deployed ServiceAccounts and observed scopes. Argo
  direct reads of the three Cilium/Hubble TLS Secrets are individually named.
- Denied/failed reads, impersonation, unknown identities and other direct target
  names remain visible. Ordinary human/admin reads are not excluded.

### Attribution of `talos:admin` backup reads

On 2026-11-26, audit showed a successful GET of
`talos-backup/talos-backup-secrets` every minute, followed by an update of the
same-named `talos.dev/v1alpha1 ServiceAccount`. Source
`fd74:67a:1fcf:4202::5a97` is the Cilium internal address of `talos-d4h-k5m`;
`w386` was the receiving API server, not the originating node.
Talos controller-runtime on `.242` logged `kubeaccess.CRDController` successfully
syncing that exact object at the same timestamps. The deployed Talos 1.14.7
[source](https://github.com/siderolabs/talos/blob/v1.14.7/internal/app/machined/pkg/controllers/kubeaccess/serviceaccount/crd_controller.go)
uses a one-minute informer resync and reads the Secret from the live API in
`syncHandler`. This is the OS controller maintaining the backup service account,
not a backup Pod running every minute. The backup CronJob runs hourly at :17.

The Talos direct-read exception fixes actor `talos:admin`, namespace, Secret name,
GET, successful response, no impersonation, observed Go HTTP client user agent
and an explicit set of Talos node source addresses. The same controller's global
list/watch informer has a separate exception with the same actor/source/client
constraints and no direct GET. The user agent is an additional constraint, not
an authentication credential. Review node IP changes rather than broadening to
an entire subnet. Other Talos identities/targets, off-node requests, kubectl
clients, impersonation and failures still alert. This does not protect against
an attacker already holding that identity and using the same expected path.

Open watches and streaming exec use ResponseStarted; other requests and errors
use ResponseComplete. This avoids double-counting each request when it finishes.
Denied exec attempts and admission rejections are useful signals too. HTTP 401/403
are `denied`; other errors (for example a nonexistent Secret) are `failed`. Dry-run
requests are explicitly marked `outcome="dry-run"`; they must not be described as
actual grants or running privileged Pods.

Each detection sets `homelab_audit_last_detection_timestamp_seconds` with its
actual audit timestamp. Prometheus alerts for fifteen minutes after a single event,
including a first-ever event; it does not rely on a lazily-created counter delta.
Related events are grouped into existing Alertmanager notifications.
The alert summary now explicitly names the receiving API server, not an affected
host. `namespace=kube-system` is a routing/collector label, not the target
namespace. The dashboard links to the 15-minute who/action/target table from Loki;
participant/target labels are not added to Prometheus metrics. Counters are
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

### Reviewed controller noise (2026-11-27)

Successful direct `get` is excluded only for cainjector reading
`cert-manager/cert-manager-webhook-ca` and platform-health-report reading
`mail/mail-tls` to inspect the public certificate. Other Secrets, namespaces,
identities, impersonation and failed reads remain detected.

GPU Operator's `create`/HTTP 409 retries are excluded only in `gpu-operator`,
for the reviewed NVIDIA RoleBinding/ClusterRoleBinding name and matching roleRef
pairs in the Alloy configuration. Successful grants, denied requests, changes,
other roles and impersonation remain detected. These no-op events remain in the
source Kubernetes audit files but are not forwarded as selected Loki detections.
Falco has no new exception. The overnight BGP outage coincided with a router
update confirmed by the operator; no permanent network-alert suppression was added.
