# Talos etcd backup

## Active configuration

Hourly at minute 17 UTC, `talos-backup/talos-backup` takes an etcd snapshot,
compresses it with zstd, encrypts it with age and uploads to SeaweedFS bucket
`talos-etcd`, prefix `home-k8s/`. The CronJob is enabled. A 30-day lifecycle rule
was configured and read back from S3; its long-term expiry behavior has not yet
been observed.

The dedicated S3 identity has `Write` and `List` scoped to `talos-etcd`, not the
administrative credentials. SeaweedFS's coarse Write permission also covers
object deletion; this is not an append-only/immutable backup destination.
OpenBao KV `talos-backup` contains `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
and `AGE_RECIPIENT_PUBLIC_KEY`. The `talos-backup` policy and
`external-secrets-talos-backup` Kubernetes auth role restrict access to this KV
path and `talos-backup/vault-auth`. External Secrets reconciles
`talos-backup-config` every 15 minutes. No private age identity is in Kubernetes,
OpenBao, or this repository.

Talos API access is enabled on all three control planes, with the generated
`talos-backup-secrets` credential restricted to `os:etcd:backup`. The backup
connects through the generated `default/talos` service. Cilium requires the
additional host/remote-node entity allowance on TCP 50000: node ipBlock rules
alone timed out in the initial live test. The S3 ingress allowance is in
`seaweedfs/network-policy-seaweedfs-allow-ingress-from-talos-backup.yaml`.

Prometheus alerts on absence of a successful CronJob run for two hours and on
suspension. The existing KubeJobFailed rule handles failed jobs. Successful job
completion is the freshness signal; a separate S3 object inventory exporter is
not configured. Alert delivery uses the existing Alertmanager route and has not
been tested with an injected notification by this repair.

## Recovery key and independent copy

The dedicated workstation identity is stored with mode 0600 under
`/home/shaman007/.config/talos-backup/age-key.txt`, in a mode-0700 directory.
Its public recipient is in the adjacent `age-recipient.txt`. Keep an independent
offline copy of the private identity; copying it offline is still the owner's
outstanding step. The YubiKey-backed SSH signing key is not used for encryption.
Do not paste the private identity into chat, Git, logs, or cluster configuration.

A verified encrypted snapshot and non-secret `verification.json` are under
`/home/shaman007/.local/state/talos-backup/`, also protected with owner-only
permissions. This is an independent off-cluster copy taken during repair;
**automatic off-cluster replication is not configured**. Repeat the download
before disruptive cluster maintenance and retain the matching age identity.
Keep the snapshot checksum and verification metadata with the encrypted copy.

## Validation performed on 2026-10-26

- Scoped OpenBao auth, SecretStore and ExternalSecret reconciled successfully.
- S3 identity listed its own bucket; unrelated-bucket listing and anonymous object
  access were denied with HTTP 403.
- A one-off job and then a scheduler-created job completed after fixing the
  Cilium egress rule. The scheduled run completed at 15:18:50 UTC.
- Retrieved a nonempty `.snap.zst.age` object from S3 and verified age encryption.
- Decrypted on the workstation using its dedicated key, and decompressed with zstd.
  Decrypted snapshot data remained in memory, never in a persistent plaintext file.
- Checksum-verified upstream etcdutl v3.7.1 reported snapshot revision 123324221,
  6997 keys and size 1583857664 bytes for the first successful test snapshot.
- `etcdutl snapshot restore` succeeded in an isolated mode-0700 tmpfs directory;
  the temporary restored data was removed afterward. No production restore,
  reset, bootstrap, or etcd membership change was performed.
- Prometheus rules passed the running version's `promtool check rules`; both
  backup alerts loaded with health `ok`, state `inactive`, and live CronJob
  success and suspension metrics were present.

This validates encryption/decryption and etcd snapshot integrity/restoration.
It is not a full disposable Talos-cluster recovery rehearsal, and does not prove
recovery after loss of all hosts or the SeaweedFS disk.

## GitOps handoff

The repair temporarily set `argocd.argoproj.io/skip-reconcile=true` on only
`talos-backup` and `kubernetes-prometheus` to prevent old Git state undoing the
live fix. Repository manifests contain the matching schedule, secret integration,
network policy and alerts. Nothing was committed or pushed by the repair.
After these changes reach the configured Git revision, remove that annotation
from both applications and verify they reconcile Synced/Healthy. Do not remove
the pause while Git still contains the suspended schedule and old alert rules.

OpenBao KV/auth policies and SeaweedFS identities/lifecycle are external state:
restoring Kubernetes manifests alone does not recreate them. Preserve them in
secure recovery material. The filer persists the S3 identity; the S3 startup
script updates admin/anonymous identities without deleting the backup identity.

## Storage and disaster-recovery limits

SeaweedFS data lives at `/var/mnt/storage/k8s/seaweedfs` on `talos-d4h-k5m`,
on the same disk as Plex videos. Loss of that disk loses the local bucket copy.
Snapshots contain Kubernetes API state, including Secrets; they do not contain
PVC contents, hostPath data, Talos machine configuration, or recovery keys.
Keep existing Longhorn/application/media backups and complete Talos recovery
material independently of the cluster.

The S3 service runs inside Kubernetes. If only the bucket copy is available after
complete control-plane loss, recover a copy of the storage disk and compatible
SeaweedFS master, volume, filer and S3 components on a separate recovery host.
That disk-level retrieval procedure still needs a rehearsal. A downloaded,
verified off-cluster encrypted snapshot avoids relying on a running production
S3 service for that recovery attempt.

For full Talos recovery, follow the version-matched disaster-recovery procedure
in a disposable cluster first, including revision-bump/watch-cache requirements.
An etcdutl restore test alone is not a reason to bypass that rehearsal before
network renumbering.

References: https://github.com/siderolabs/talos-backup and
https://docs.siderolabs.com/talos/v1.14/disaster-recovery/disaster-recovery.
