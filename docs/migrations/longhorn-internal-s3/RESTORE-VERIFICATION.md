# Isolated GeoIP restore verification — 2026-11-14

Executed with explicit authorization: restore a small Longhorn backup onto a
**new PVC**, inspect contents/errors, leave working data untouched. Times below
are Europe/Prague (CET). No backup/PVC/volume was deleted or restored over.

## Source and isolated target

| Item | Value |
| --- | --- |
| Source PVC | `traefik/traefik-geoip-rwx`, 1Gi RWX/ext4 |
| Source Longhorn volume | `pvc-ebe1aab2-d3fa-4710-9e78-5dcf04c5a1d0` |
| Backup | `backup-0dc70835650e4a37`, Completed, created 2026-11-13 21:29:35 CET |
| Backup URL | `s3://backup@us-east-1/?backup=backup-0dc70835650e4a37&volume=pvc-ebe1aab2-d3fa-4710-9e78-5dcf04c5a1d0` |
| Configured S3 endpoint | `http://s3.seaweedfs.svc.cluster.local:8333` |
| New namespace | `restore-verification` |
| New PVC | `geoip-restore-20261114`, 1Gi RWO/ext4 |
| New PV/Longhorn volume | `pvc-59fca1f0-b774-4642-9979-5db5b3a2d72b` |
| New StorageClass | `longhorn-restore-geoip-20261114`, reclaimPolicy Retain |
| Reader Pod | `geoip-restore-20261114-reader`, node `talos-qlw-pbh` |

Used CSI provisioning through a dedicated StorageClass `fromBackup` and the
existing default backup target, following the [Longhorn StorageClass contract](https://longhorn.io/docs/1.13.0/references/storage-class-parameters/).
Only the non-secret AWS_ENDPOINTS field was read to verify the internal route;
no credentials were exported. The test did not disable the public route or claim
an independently captured per-volume packet trace. Restored data were read using
the configured internal S3 target; a full cluster disaster was not simulated.

Created only five standalone objects: Namespace, default-deny NetworkPolicy,
StorageClass, new PVC and reader Pod. CSI provisioned the distinct new PV/volume.
These are not GitOps workloads or scheduled tests. No existing StorageClass,
source PVC/PV/volume, Deployment, backup target or global job setting was changed.

## Read-only data verification

The new filesystem was mounted with StorageClass `ro,noload`, a read-only Pod
volume and read-only container mount. `/proc/mounts` confirmed
`ro,seclabel,relatime,norecovery`. Reader ran UID/GID65532, no capabilities,
no service-account token, a read-only root filesystem and a namespace default-deny policy.
The reader only accessed the new restored filesystem. A SHA/size comparison
read the original GeoIP file through the existing Traefik Pod, without creating
another mount of the source PVC or writing to it.

| Check | Result |
| --- | --- |
| Restored path | `geoip/dbip-country-lite.mmdb` |
| File size | 8,515,063 bytes |
| SHA-256 | `145ce5dfb812d8de28547e6289bb5c5f8b3df2f1dea21d324d5b575e0431311f` |
| Content comparison | Restored SHA/size exactly match source-before and source-after |
| MMDB metadata | MaxMind.com metadata marker found near file end |
| Reader result | RESTORE_READ_ONLY_CHECK_OK; Succeeded, exit0, zero restarts |

Reader started at 01:09:11 CET and exited naturally at 01:11:12 CET after a
short bounded observation window. The application directory contained the one
expected GeoIP file. This is byte-level verification of that file plus its
metadata marker, not a database/application-level restore test for other PVCs.

## Restore and error checks

* New volume restoreRequired=false, restoreInitiated=true. While the reader was
  mounted, volume was attached/healthy with two running healthy replicas on
  `w386` and `talos-qlw-pbh`; both failedAt fields empty.
* Replica healthyAt was 01:08:09 CET; Restore condition cleared by 01:08:14 CET.
* Initial scheduler/CSI retries said PVC not yet Bound, restoration required and
  waiting for automatic detach. They resolved to SuccessfulAttachVolume, Pulled,
  Created and Started. No persistent restore, mount or reader I/O error remained.
* After reader completion the new volume detached normally. Detached robustness
  is reported unknown; it was verified healthy while attached.
* Source volume stayed attached/healthy, lastBackup unchanged. Its two public
  Traefik Pods remained Ready with zero restarts, and source SHA/size unchanged.

## Recurring jobs, alerts and retained artifacts

StorageClass has recurringJobSelector=[]; global restore-volume-recurring-jobs
was already false. Longhorn still auto-adds its default group label. Removing
that label was not persistent: the controller added it back. The new volume's
restoreVolumeRecurringJob was explicitly set disabled, and actual job selection
was checked: **zero existing jobs target the default group or this test volume**.
The source volume/job groups and all global schedules were untouched.

A single 20-minute silence matched only KubePodNotReady for the exact new reader
Pod/namespace. ID `e84a8f34-8c8c-484c-9a63-6b60a87f9a8b`, original expiry
2026-11-14 01:28:00 CET. It was explicitly expired after successful completion;
no related alerts remained. Restore/storage failure rules stayed active.

The completed reader, new PVC/PV, StorageClass and namespace are retained for
review. No test-volume cleanup/deletion was authorized or performed. Retain is
intentional: deleting the PVC alone would not delete its restored data. A future
cleanup must identify only the new PV/volume UUID above and leave the original
source, backup and production workloads intact. Re-evaluate job membership if
these retained resources remain when schedules are changed later.

Private workstation scratch `/tmp/longhorn-restore-20261114` contains the exact
create manifest, reader output and non-secret comparison/acceptance reports.
It is not a durable data backup. No plaintext credentials were stored there.
This successful isolated restore closes the prior data-recoverability check for
this backup, while full cold boot, empty image-cache bootstrap and independent
credential/CA recovery remain separate untested scenarios.
