# Filesystem trim coverage

`recurring-jobs-proposed.yaml` is active configuration included by the
`longhorn-custom` Argo CD Application, despite its historical filename.
The Longhorn Helm StorageClass selector assigns `trim-daily-a` to new volumes.

`trim-coverage-guard.yaml` reconciles existing volumes every 15 minutes. It adds
`trim-daily-a` only when no enabled direct or group assignment resolves to an
existing filesystem-trim RecurringJob. Existing trim cadences and backup labels
are preserved. When a PVC is the recurring-job label source, its missing trim
assignment is repaired first, copying the volume's existing trim cadence when
available. A failed repair does not prevent attempts on the remaining volumes,
but the overall Job fails if any repair fails. Resource versions guard against concurrent changes;
a conflict fails the run and is retried by the Job or next schedule. A missing
fallback RecurringJob fails the run, leaving restoration of that definition to
Argo CD self-healing. No PVC, volume, or replica data is deleted.

The guard needs get/list/patch on Longhorn volumes, get/list on recurring jobs,
and get/patch on PVCs to repair source labels. Kubernetes RBAC cannot restrict
patch permission to individual metadata labels; keep this service account limited
to this workload. API or permission failures fail the Job visibly.

The platform health report separately checks every PVC. Filesystem PVCs in the
`longhorn` StorageClass are checked against actual Longhorn volume labels and
live trim job definitions. Empty inventory, missing volumes, and missing
assignments fail. Other StorageClasses and raw block PVCs also fail with an
explicit-review message rather than silently disappearing from coverage.
The existing schedule-aware maintenance check detects missing, suspended, and
stale generated trim CronJobs. A separate guard check fails when the guard is
missing, suspended, or has not succeeded within one hour, or any of the five
GitOps trim job definitions is absent (even if no PVC currently selects it). Repository unit tests run in the existing CI job
and protect the Argo includes and new-volume StorageClass default as well as
coverage and repair behavior.

Longhorn filesystem trim does not cover raw block PVCs or local-path storage.
The live `plex/plex-lib` and `immich/immich-library-hdd` PVCs use local-path
on `/dev/sda1`, mounted at
`/var/mnt/storage` on `talos-d4h-k5m`. Read-only inspection on 2026-11-06 found
model `ST24000NM002H-3K`, rotational flag `1`, and both `discard_max_bytes` and
`discard_max_hw_bytes` equal to `0`. This device does not support discard, so a
host fstrim job cannot provide trim coverage. An explicit scope exception for
these PVCs remains pending user confirmation. No host configuration is changed.
See the [Linux block queue documentation](https://www.kernel.org/doc/html/latest/block/queue-sysfs.html).

Repository validation does not deploy this change. After authorized GitOps
publication/reconciliation, verify the guard completes, the coverage report passes
for all filesystem Longhorn PVCs, and trim CronJobs successfully execute on their
configured schedules. Longhorn CronJob success is schedule-level evidence; it is
not proof of the number of bytes reclaimed on each filesystem.
