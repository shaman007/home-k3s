# Recurring-job hardening

The 14 RecurringJobs in `recurring-jobs-proposed.yaml` generate CronJobs through
Longhorn Manager v1.13.0. The pinned controller has no recurring-job security
context setting. Editing a generated CronJob alone does not cover its recreation.

`policy-recurring-job-security.yaml` uses the native Kubernetes v1
MutatingAdmissionPolicy API (available on this cluster), independently of
Kyverno. Kyverno's five validation policies remain Audit/Ignore. This native
policy is a narrowly scoped mutation, not an additional audit or deny policy.

The policy matches only the 14 reviewed names in `longhorn-system`, both
Longhorn generation labels, `longhorn-service-account`, one regular container,
no init containers, and the exact declared v1.13.0 image and recurring-job command.
The binding also selects only `longhorn-system`. The policy is fail-open and
sets only the regular container's security context:

```yaml
runAsNonRoot: true
runAsUser: 1000
runAsGroup: 1000
allowPrivilegeEscalation: false
privileged: false
capabilities:
  drop: [ALL]
seccompProfile:
  type: RuntimeDefault
```

This leaves schedules, concurrency, retention, group membership, volume mounts,
service accounts and existing Job/Pod objects alone. Future Jobs inherit the
hardened template. Image/command/container changes fall outside the reviewed
contract and require reviewing the policy before an upgrade; fail-open matching
allows Longhorn to continue scheduling when the contract changes.

## Compatibility evidence

The v1.13.0 source's `app/recurringjob` package implements snapshot, backup and
filesystem-trim through Longhorn/Kubernetes clients, without local host-command
execution or filesystem writes. The generated engine-binaries host mount remains
present; this change does not alter storage or ownership.

The exact image tested locally was
`docker.io/longhornio/longhorn-manager:v1.13.0`, resolved manifest digest
`sha256:dfe39d0ce270c68b333d8b32bec41ee540b7a099ccc598ea312337a85c20fd89`.
The policy matches the declared tag, not a resolved digest; review image changes.

A rootless Podman test ran the binary as UID/GID 1000 with no effective
capabilities, `NoNewPrivs: 1` and `Seccomp: 2`. Snapshot, backup and filesystem-trim
startup each exited successfully against isolated mock APIs, reading the
RecurringJob, updating its mock execution count, initializing the manager
client, reading the detached-volume setting and selecting zero mock volumes.
No production credentials or storage were used. This proves startup and API
client compatibility, not completion of a real snapshot, backup or trim.

Reproduce the isolated startup test on a host with Podman and OpenSSL:

```sh
python3 tools/longhorn/test-recurring-job-startup.py
```

The test uses only synthetic local authentication/TLS material and temporary
files. It needs the exact image locally and creates no Kubernetes resources.

## GitOps activation and backfill

`longhorn-custom` deploys the policy, binding and dedicated backfill RBAC before
its PostSync hook. The hook runs the program in
`tools/longhorn/backfill-recurring-security.py` (embedded in its ConfigMap).
Its service account may only get/patch the 14 named CronJobs in `longhorn-system`.
It cannot create Jobs, Pods, snapshots or backups, or modify other namespaces.

The backfill verifies actual Longhorn ownership and the reviewed command/image
contract, then server-dry-runs an annotation patch for every present target.
It requires admission to produce exactly the intended security-context changes,
with no other spec changes. Only after all preflights pass does it persist the
annotation patches. Each patch tests resourceVersion to reject concurrent edits,
and each persisted spec is checked by read-back. Already hardened jobs are
idempotent; absent jobs are covered when Longhorn creates them. A failed hook is
retained for inspection; successful hooks are removed. No recurring job is run
manually and no existing job is deleted.

The native policy's API validation is tested by server-side dry-run. CI also
runs the same CEL/JSONPatch through Kyverno 1.19.2's engine using a temporary
MutatingPolicy wrapper; the CLI does not directly load native mutation policies.
Positive, negative-scope and idempotence cases are covered. This offline wrapper
is not proof that the live native binding has activated: the hook's API dry-run
is the deployment gate for that.

After pushing, verify `longhorn-custom` is Healthy/Synced, the hook succeeded,
all 14 CronJob templates contain the fields above, and newly scheduled jobs
complete normally. Check all four relevant Kyverno policies: non-root,
escalation, capability drops and seccomp. Old completed Jobs keep their previous
specifications and may retain findings until ordinary history cleanup.

For rollback, remove the binding first to stop future mutations, then restore
only the security fields from reviewed CronJob snapshots. Removing the policy
alone does not revert already modified templates. Do not delete running jobs or
change backup/retention schedules to roll back security-context changes.

Sources: [pinned CronJob controller](https://github.com/longhorn/longhorn-manager/blob/v1.13.0/controller/recurring_job_controller.go),
[pinned recurring-job implementation](https://github.com/longhorn/longhorn-manager/tree/v1.13.0/app/recurringjob),
[native admission-policy documentation](https://kubernetes.io/docs/reference/access-authn-authz/mutating-admission-policy/).
