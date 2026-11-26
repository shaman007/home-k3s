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
Detection conditions, enabled rules, priority and exclusions are unchanged;
there is no Argo CD exception.

Sidekick retains every field in Loki JSON and the event text in notification
annotations. These per-event diagnostic fields have empty Alertmanager label
overrides, like the timestamp, so changing PID/TID, syscall result, descriptor
or connection does not create a new fingerprint. Rule, executable, parent,
container/Pod and UID still distinguish events. All detailed events remain
available for comparing repeated Git launches against suspected redirections.

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
