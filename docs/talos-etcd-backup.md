# Talos etcd backup

## Storage and scope

The `talos-etcd` SeaweedFS bucket stores encrypted, zstd-compressed etcd
snapshots under `home-k8s`. SeaweedFS data lives at
`/var/mnt/storage/k8s/seaweedfs` on `talos-d4h-k5m`, on the same disk as
Plex videos. Read-only checks on 2026-10-10 found approximately 10 TiB free.
This is a local recovery copy: loss of that disk also loses these snapshots.

Snapshots contain Kubernetes API state, including Secrets. They do not contain
PVC contents, hostPath data, Talos machine configuration, or recovery keys.
Keep existing Longhorn backups and media backups. Keep Talos recovery material
and the age private key securely outside the cluster and outside this disk.

## Prepared, not activated

The Argo application uses manual sync and the hourly CronJob is suspended.
No bucket, credentials, keys, Talos permissions, or live resources have been
created by preparing these manifests. The Talos ServiceAccount CRD is currently
absent; enable the Talos API integration before syncing the application.

Activation requires separately authorized live changes:

1. Merge `talos/etcd-backup-api-access.yaml` into the effective machine configs
   on all three control-plane nodes. Preserve any existing API roles/namespaces;
   list patches can replace existing entries. Verify the Talos controller creates
   the `serviceaccounts.talos.dev` CRD.
2. Create the dedicated `talos-etcd` bucket and a bucket-scoped S3 identity with
   upload access. Configure a 30-day bucket lifecycle expiry and verify it is
   enforced by this SeaweedFS version. This retains hourly snapshots for 30 days;
   no backup deletion permission is needed by the snapshot job.
3. Generate an age key pair using a trusted workstation. Store the private key
   securely outside the cluster; verify its recovery copy. Never put it in Git,
   Kubernetes, command output, or logs. Only the public recipient belongs in the
   backup job configuration.
4. Provision Secret `talos-backup-config` in namespace `talos-backup` through the
   secret-management workflow. Required keys: `AWS_ACCESS_KEY_ID`,
   `AWS_SECRET_ACCESS_KEY`, and `AGE_RECIPIENT_PUBLIC_KEY`. Do not reuse the
   SeaweedFS administrative credentials.
5. Reconcile SeaweedFS's new ingress policy and manually sync the backup
   application. Verify Talos generates Secret `talos-backup-secrets` with the
   restricted `os:etcd:backup` role.
6. Run a one-off job from the suspended CronJob. Confirm Job completion and a
   new, nonempty object in `talos-etcd/home-k8s`. Download it without printing its
   contents, decrypt with age, decompress with zstd, and inspect the etcd snapshot
   using a compatible `etcdutl snapshot status` binary.
7. Rehearse restoration on an isolated disposable Talos cluster using the
   version-matched disaster-recovery guide. Never restore onto the production
   cluster as a test. Document the tested snapshot, versions, and result without
   secret data.
8. Add alerts for job failures and absence of a new object for more than two
   hours. Verify bucket expiry and failure notification before setting
   `suspend: false` in Git and syncing. Alerting is not included in this initial
   manifest set.

## Recovery when Kubernetes is unavailable

The S3 service runs inside Kubernetes. To recover after complete control-plane
loss, recover the video disk and bring up compatible SeaweedFS master, volume,
filer, and S3 components against a copy of its data on a separate recovery host.
Retrieve and validate a snapshot before bootstrapping replacement Talos nodes.
Keep a copy of the SeaweedFS configuration and the needed images available
outside the cluster. This disk-level retrieval procedure still needs a rehearsal;
an S3 download while Kubernetes is running does not prove disaster recovery.

An additional encrypted copy on a separate disk or remote object store would
remove the shared-disk failure risk.

References: https://github.com/siderolabs/talos-backup and the version-matched
Talos disaster-recovery documentation.
