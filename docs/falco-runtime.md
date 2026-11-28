# Falco runtime detections

Falco captures container syscalls on every node with the modern eBPF driver.
Falcosidekick forwards selected events to the existing Alertmanager routes
(Telegram and email) and Loki. It does not block or terminate processes.

## Scope

Only these upstream rules from `falco-rules:5.2.0` are enabled:

| Rule | Detects | Coverage limit |
| --- | --- | --- |
| Terminal shell in container | Shell started with a terminal | Does not cover every non-interactive shell |
| Drop and execute new binary in container | Execution from the container overlay upper layer | Not a general inventory of new scripts, mounted volumes or all executable changes |
| Redirect STDOUT/STDIN to Network Connection in Container | stdin/stdout duplicated onto a network socket | A reverse-shell signature, not every reverse-shell technique |

All three have warning priority. Outputs contain executable/parent names,
container/image, Pod/namespace, node and UID; command arguments and environment
are excluded. Talos host processes identified by the CRI sentinel
`container.id=runtime` are excluded: without this, host CNI execution produces
container alerts with missing Kubernetes metadata. Actual CRI container IDs
remain covered. There are no namespace-wide exclusions.

## Safe redirect diagnostics

The redirect rule additionally emits `proc.pid`, `thread.tid`, `evt.type`,
`evt.rawres`, `fd.num`, `fd.type` and `fd.name`. The socket name contains the
connection endpoints; the syscall result identifies the resulting descriptor
(0/1/2 for this rule). Missing process metadata can still appear as `<NA>`.
No command arguments, environment or generic syscall argument dump is emitted.
The three security detections retain Warning priority. Reviewed pre-exec stdin
exceptions are described below; neither shell nor new-binary detection is excluded.

Sidekick retains every field in Loki JSON and the event text in notification
annotations. These per-event diagnostic fields have empty Alertmanager label
overrides, like the timestamp, so changing PID/TID, syscall result, descriptor
or connection does not create a new fingerprint. Rule, executable, parent,
container/Pod and UID still distinguish events. All detailed events remain
available for comparing repeated Git launches against suspected redirections.

## Automatic repo-server fd context

`Argo repo-server safe process lifecycle` is an additional **Notice** diagnostic
rule, scoped to namespace `argocd`, Pod prefix `argocd-repo-server-` and image
repository `quay.io/argoproj/argocd`. It records clone/fork, dup/dup2/dup3, exec
and process-exit events continuously, so the next Warning can be compared with
its preceding fd setup and the executable that follows. This is diagnostic
context, not proof that every incoming RPC socket is benign. Only the reviewed
pre-exec tuples below are excluded from Warning. Unknown Kubernetes/image metadata
can cause context to be absent.

Both the Warning and diagnostic context include host PID/TID, parent PID,
container PID/TID, process age in nanoseconds and the numeric `oldfd` syscall
argument. Context also includes clone/dup flags. These are explicit field
allowlists: no command arguments, environment, generic syscall argument dump,
I/O buffers or payloads are collected in the output. Fields unavailable for a
particular syscall can be `<NA>`; the failed ten-minute reproduction is not
evidence that the original network descriptor was harmless.

Sidekick sends Notice to Loki only; Alertmanager remains at Warning. Only the
scoped Argo and FRR lifecycle diagnostic rules have Notice priority. Additional Warning fields are
removed from Alertmanager identity, preserving grouping. There is no additional
BPF process, host mount, credential, or automatic refresh. Scope this temporary
investigation rule back out once the cause is established; check event volume
and sensor/Sidekick drops after deployment. Loki's existing retention applies.

When the next redirect arrives, use its node, container ID, host PID/TID and
event time to query context in the same time window (including after the alert):

```logql
{job="falco"} | json | rule="Argo repo-server safe process lifecycle"
```

Compare `oldfd` with the resulting fd (`evt.rawres`), clone/parent lineage and
subsequent exec for that PID. Use process age/time to avoid PID reuse; do not
infer the child command from the parent process name. Compare the Warning's
socket endpoints with this sequence and Argo RPC logs. If context is missing or
contradictory, keep the security event visible rather than broadening exceptions.

Native routing tests verify Notice reaches only Loki, Warning annotations retain
safe details, and changed parent/PID/fd fields do not split alert fingerprints.
Local validation does not prove runtime collection: after publication, verify
Argo sync, rule loading, actual Notice records in Loki, and no delivery drops.

## Reviewed Go pre-exec stdin exceptions

The 2026-11-28 investigation found the same Go child-start pattern in Argo CD
and MetalLB: a new child still has the parent's short process name, no resolved
executable, and sets up fd 0/1/2 before `execve`. All three captured Argo Warning
PIDs executed `/usr/bin/git` 0.21–0.35 ms after the Warning and exited within a
few milliseconds; nearby Argo logs contain ordinary Git repository operations.
A separate authorized 60-second FRR trace captured 12 complete
`frr-metrics -> /usr/bin/vtysh` launches, including `oldfd=11 -> stdin=/dev/null`
and stdout/stderr pipes, with zero reported drops. The deployed exporter uses
Go `exec.Command(...).CombinedOutput()` without an explicit stdin, whose default
is `/dev/null`:

- [FRR metrics vtysh runner, v0.0.27](https://github.com/metallb/frr-k8s/blob/v0.0.27/cmd/metrics/vtysh/vtysh.go)
- [Argo command output setup, v3.6.3](https://github.com/argoproj/argo-cd/blob/v3.6.3/util/exec/exec.go)
- [Go child stdin setup](https://github.com/golang/go/blob/go1.27.3/src/os/exec/exec.go)

The normal process-launch paths are confirmed. The rare network type is
consistent with incorrect/incomplete descriptor attribution during that pre-exec
window; the specific internal Falco defect has **not** been isolated. No claim is
made that a particular upstream patch fixes these events. The exception is an
explicitly reviewed noise classification, not authentication or proof that every
connection from these workloads is safe.

The redirect condition excludes only `argocd_reviewed_preexec_stdin` and
`metallb_reviewed_preexec_stdin`, using the common guard
`reviewed_go_preexec_stdin_setup`: successful **dup3 to stdin (fd/result 0)**,
IPv4 TCP, **empty executable path**, process age **greater than 0 and less than
1,000,000 ns**. Missing metadata and an older process do not match. The duration
bound constrains the observed pre-exec shape; it does not predict the executable
that will run next. Parent name and container name are intentionally not trusted
because their metadata was absent/transient in the original events.

Every row also pins namespace, Pod prefix, image repository/tag, UID, short
process name, source fd, socket direction, client/server IP and server port:

| Workload | Image / UID / process | oldfd | Client -> server | Socket role |
| --- | --- | --- | --- | --- |
| `argocd/argocd-repo-server-*` | `quay.io/argoproj/argocd:v3.6.3`, 999, `argocd-repo-ser` | 17 | `10.42.1.220 -> 10.42.0.193:8081` | server |
| same | same | 17 | `127.0.0.1 -> 127.0.0.1:8081` | server |
| same | same | 16 | `10.42.0.193 -> 140.82.121.4:443` | client |
| `metallb-system/metallb-frr-k8s-*` | `quay.io/frrouting/frr:10.6.2`, 100, `frr-metrics` | 11 | `192.168.30.100 -> 192.168.30.100:9141` | client |
| same | same | 11 | `192.168.30.242 -> 192.168.30.242:9141` | client |

GitHub's published Git service ranges included the single observed
`140.82.121.4` address during review. The rule uses that exact IP, **not** a
GitHub CIDR or all HTTPS. Only the two observed FRR node pairs are excluded; a
third node, new Pod IP, changed image, new oldfd, different port/client/server,
stdout/stderr, another process or any non-empty executable remains alertable.
IP and image drift deliberately requires a new review instead of widening scope.
The existing backup SSH exception is unchanged.

Falco normally emits the first matching rule for an event. An excluded Argo
stdin event now falls through to `Argo repo-server safe process lifecycle`, and
an excluded FRR event to `FRR metrics safe process lifecycle`. Both are Notice,
Loki-only, without argv/env/buffer output. FRR diagnostics also keep clone/dup/
exec/exit context scoped to the FRR image/Pod/namespace and process names
`frr-metrics` or `vtysh`; do not discard this context before checking real
post-deployment events. Unexpected connections still hit the original Warning
rule before either diagnostic rule.

Validation distinguishes native compilation, boundary contracts and runtime
verification. Native Falco validates supported fields/operators. Unit boundary
contracts evaluate the reviewed predicate subset against the five observed
shapes, single-field mutations and missing metadata; their small test-only
predicate evaluator is **not** the Falco engine and does not prove live matching.
Native Sidekick tests prove Notice goes to Loki only and Warning fingerprinting
is unchanged. After publication, verify the exact Argo revision, loaded macros,
Loki Notice preservation and actual Warning suppression on ordinary activity.
A quiet interval alone is not proof that a rare event matched the exception.

## Talos compatibility and permissions

Verified on 2026-11-26: Talos 1.14.7, Kubernetes 1.37.1, kernel
6.18.65-talos, amd64, on `w386`, `talos-qlw-pbh` and `talos-d4h-k5m`.
All nodes expose `/sys/kernel/btf/vmlinux`; modern eBPF attached and processed
syscalls on all three. No Talos configuration change or kernel module is needed.

Pinned components: chart 9.2.2, Falco 0.45.2, container plugin 0.7.6,
falcoctl 0.14.3, Falcosidekick 2.35.1. Rule auto-follow is disabled.

The sensor is a trusted host component: UID 0, BPF/PERFMON/SYS_RESOURCE/SYS_PTRACE
capabilities, Unconfined seccomp, read-only host proc/etc/sysfs and access to the
root-owned containerd socket. It is not a privileged container, but the runtime
socket and capabilities still require a strong trust boundary. Do not copy these
permissions to application Pods. Neither component gets a Kubernetes API token
or RBAC. Sidekick is non-root, without host mounts or capabilities.

Per sensor: requests 100m CPU/512Mi memory, memory limit 1Gi. Sidekick has two
replicas, each requesting 10m/64Mi with a 256Mi memory limit. CPU is not capped.
At the initial measurement sensors used about 33–52m and 125–185Mi; reassess
under peak workloads. Artifact installation needs HTTPS to ghcr.io and
pkg-containers.githubusercontent.com. Network policies restrict sensor egress
to those registries, DNS and Sidekick; Sidekick can reach DNS, Alertmanager and
Loki gateway. Prometheus has narrowly scoped scrape access.

## GitOps ownership

`argocd/application-falco.yaml` combines the official Helm chart with
`falco/values.yaml` and the local accounts, Sidekick and runtime policies.
`application-project-observability.yaml` permits the chart repository.
The monitoring policy Application explicitly includes the Falco policy file;
the existing Loki policy Application includes its new ingress file.

Publish all related changes together. The initial live installation was tested
before publication; a healthy live DaemonSet alone does not prove Argo ownership.
After publication verify the Falco Application revision, Synced/Healthy state,
resource tracking and absence of repeated reconciliation changes. Check the
monitoring and Loki policy Applications too.

## Verification and delivery

```sh
kubectl get pods -n kube-system -l app.kubernetes.io/name=falco -o wide
kubectl logs -n kube-system -l app.kubernetes.io/name=falco -c falco --since=10m
kubectl logs -n kube-system -l app=falcosidekick --since=10m
python3 tools/ops/verify.py argocd
```

Expect one sensor per node, a successful modern BPF probe startup on each node,
increasing `falcosecurity_scap_n_evts_total`, and no sustained increases in
`falcosecurity_scap_n_drops_total` or
`falcosecurity_falco_outputs_queue_num_drops_total`. Prometheus jobs `falco` and
`falcosidekick` should have three and two healthy targets respectively.
Health rules: `FalcoNodeMissing`, `FalcoSyscallDrops`, `FalcoOutputDrops`,
`FalcosidekickDeliveryErrors`. Sidekick metrics are created lazily; no event
counter on an idle replica is expected. Delivery errors also handle the first
nonzero sample of a newly created error series.

Inspect Loki with `{job="falco"}` and match the rule, event time, node and Pod.
A Sidekick HTTP 200 from Alertmanager proves acceptance only. Check the matching
Alertmanager group and Telegram notification errors, and read the actual email
with `himalaya message read --preview` in `INBOX/K8S`. Sidekick sends to the
Alertmanager Service, not independently to every HA peer. Events expire after
900 seconds; this is an event notification path, not a durable delivery queue.

The initial end-to-end test used a temporary non-root, tokenless Python Pod
with no capabilities and a deny-all ingress/egress policy. Three harmless
operations triggered all rules: TTY `/bin/sh` printing a marker, copying busybox
to `/tmp/true` and executing `true`, and temporarily duplicating stdout onto a
TCP loopback socket inside the same Pod. No external reverse shell was opened.
Events at 17:49:56, 17:49:59 and 17:50:02 UTC on 2026-11-26 appeared in Loki,
were accepted by Alertmanager, and were received as email. Telegram transport
reported successful notifications with no errors during the test window;
reading the recipient's Telegram client is a separate confirmation.

For repeat tests use an explicitly approved temporary Pod with the same
restrictions, a short activeDeadlineSeconds, and remove both Pod and policy
when finished. Test a node at a time when changing Talos or Falco versions.
Do not send command lines, environment or test secrets to the notification path.

## Triage and rollback

Check the affected Pod's owner, image and Kubernetes audit exec event before
assuming a shell is malicious. Deployments that legitimately create binaries
may need a narrow rule exception based on a verified process/image pattern;
do not suppress an entire namespace to remove noise.

For probe startup failures inspect BTF, capabilities and read-only mount/socket
paths. For drops inspect node pressure and buffers before increasing limits.
For delivery errors check both sides of namespace policies and receiver logs.
If rolling back, revert the Falco Application/configuration and related policy
and Prometheus changes through GitOps. Removing only live objects while
self-heal is enabled is temporary. Do not remove shared Alertmanager/Loki routes.

## Stable alert identity and runtime package noise

Falcosidekick's Alertmanager-only `extralabels.evt_time` is an empty string.
This overrides the automatically copied per-event timestamp label, so repeated
instances of the same rule/container/process/user share a fingerprint. Pod,
container, image, executable, parent and UID labels are retained: a different
executable or identity still produces a distinct alert. Only Alertmanager label
identity is changed; event time, full sanitized output and every separate event
remain in Loki and in the latest alert annotations.

The Falco-specific Alertmanager route groups notifications by alertname,
priority, actual Kubernetes namespace and Pod, with a 30-second group wait.
Other jobs and the existing critical-priority route keep their current routing.
These controls aggregate repeat events; they do not exclude a namespace, image
or process from any of the three detection rules.

`mastodon/bookmarked-media-sync` now uses a shared, signed runtime image with
ca-certificates, coreutils, curl, jq, kubectl and Immich CLI 3.0.2 installed during
build. Runtime `apk add` and `npm install` were removed. Dependencies are in the
image's lower layer, so ordinary utility execution no longer resembles dropped
binaries. A genuinely copied executable in the writable layer still alerts.

Image source is `bookmarked-media-sync/Dockerfile` in the sibling Dockerfiles
repository. The existing weekly builder discovers it automatically. To prepare
an isolated signed build with the current local source:

```sh
python3 tools/bookmarked-media-sync/prepare_build.py --source ../Dockerfiles > /tmp/bookmarked-build.json
```

The renderer writes an inert Job only. Review it, then submit through the
repository's authorized build workflow. It inherits the existing builder's
credentials/signing references, privileges, architecture, resource limits and
network policy. The small source archive is embedded in the Job to avoid
requiring another ConfigMap; its hash names the build and immutable image tag.
Pin the verified published digest in both CronJob containers.

Publish source changes in both repositories. Argo must apply the CronJob,
Falcosidekick configuration and Alertmanager route. Existing Jobs retain their
old Pod specifications; do not modify a running import to test the new image.
After rollout check a newly scheduled Job and query Loki for its Pod. Historical
alerts remain until expiry. A native Sidekick fixture test confirms deduplication
across event times, distinct alerts for distinct executables, and lossless Loki
forwarding; an isolated tokenless Pod can test normal utilities and a harmless
copied `true` executable without touching Mastodon/Immich data.

### Backup SSH stdout exception

The redirect rule excludes only the confirmed OpenSSH `dup2` stdin/stdout events
for namespace `backup-rsync`, Pod prefix `backup-rsync-`, image
`harbor.andreybondarenko.com/quay/panubo/sshd:1.10.0`, UID 0, matching sshd or
sshd-session executable/parent pairs, IPv4 TCP server socket on port 22 and
client `192.168.30.79`. Review this tuple when the client address or image changes.
Only descriptors 0 and 1 are excluded; stderr and other descriptors stay visible.
Other clients, outbound sockets, processes and namespaces remain
covered. Shell/new-binary rules are unchanged. This exception suppresses these
Falco events before forwarding, so they no longer reach Loki or notifications;
SSH authentication logs remain available from the backup server.

### SSH exception verification status

A real read-only rsync probe after revision `10e182a8` still emitted both
stdin/stdout redirects despite the compiled exception. Do not consider the
exception effective based on syntax validation alone. The redirect output now
also includes image tag, socket server role, L4 protocol, client IP and server
port to identify the mismatching runtime constraint before changing scope. These
fields are excluded from Alertmanager identity, like the existing PID/fd details.
No exception constraint was removed or widened for this diagnostic change.

The failed early probe showed `container.name` equal to the container ID instead
of `sshd` immediately after sensor restart. Use the Deployment Pod prefix with
the exact namespace/image/process/socket constraints instead of this transient
container name. Do not whitelist a container ID or remove the workload scope.
Four later read-only probes emitted no events; the prefix correction protects
the same scope when container name metadata is incomplete.
