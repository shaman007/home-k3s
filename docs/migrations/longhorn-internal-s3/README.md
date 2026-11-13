# Direct Longhorn backup-store endpoint

Status: **direct endpoint active**, 2026-11-13. The separately authorized
endpoint-only cutover and signed acceptance are recorded in [EXECUTION.md](EXECUTION.md).
One subsequent explicitly authorized GeoIP-PVC full backup completed successfully.
No backup was deleted, and no restore or rollout was performed.

The live default BackupTarget is `s3://backup@us-east-1/`, using Secret
`longhorn-system/longhorn-backup-s3`. Its `AWS_ENDPOINTS` previously pointed to
`https://s3.andreybondarenko.com`. That public route requires Traefik, whose
`traefik-geoip-rwx` PVC is on Longhorn. Restoring that PVC through the same
route can block recovery.

It now uses the existing ClusterIP Service directly:

```text
Longhorn manager / backup engine → CoreDNS + Cilium
  → http://s3.seaweedfs.svc.cluster.local:8333 → SeaweedFS S3
  → existing filer/volume/master and hostPath on talos-d4h-k5m
```

This path needs no public DNS, Traefik, GeoIP database, CrowdSec, public TLS or
Harbor images. Existing volumes still attach independently of this backup target.
SeaweedFS core images are pinned upstream. Its S3 container already waits for
master/filer and configures identities before serving traffic.

## Transport and bootstrap boundary

**The proposed internal connection is HTTP, not TLS.** S3 SigV4 authenticates
requests but does not encrypt backup contents or access-key identifiers. The
secret signing key is not sent over the wire. This is an explicit transport
tradeoff for the cluster-only backup path, not an equivalent replacement for
HTTPS. Deployment approval must include accepting it. If internal encryption is
required, stop here and prepare native SeaweedFS TLS with Service SANs and
independent trust; do not disable certificate verification or reuse a certificate
whose SANs do not cover this Service.

There is no new VIP, ingress, DNS override, sidecar, CA or certificate. The public
S3 and media-cache routes stay as they are. The existing SeaweedFS NetworkPolicy
allows longhorn-system to TCP8333. Observed managers use ClusterFirst DNS and
ordinary Pod networking; engine/instance-manager paths must also be verified at
cutover. Namespace policies alone may not cover future hostNetwork consumers.

Retain independent recovery copies of the existing `s3-admin` identity and
`longhorn-backup-s3` credentials, outside the failed storage/OpenBao system,
encrypted under the established age custody procedure. This preparation neither
exports nor recreates those secrets. Their independent recoverability has not
been demonstrated. SeaweedFS hostPath/node loss remains a separate recovery risk.

## Prepared change

`endpoint.json` contains public routing metadata only. The local helper generates
an atomic JSON Patch with name, namespace, resourceVersion and old-endpoint tests.
It replaces only `data.AWS_ENDPOINTS`, preserving all credential keys, region,
CA fields, Secret metadata and type. It never contacts Kubernetes or reads
credentials. The Secret is currently manually managed; this is a scoped runtime
configuration transition, not a Secret value added to Git.

The existing `longhorn/backup-target-seaweedfs-patch.json` does not need changing:
the bucket, region and credentialSecret name remain identical. No backup object
is copied, renamed or deleted. Any existing `AWS_CERT` may remain untouched; it
does not turn an HTTP endpoint into TLS.

## Transition after separate live authorization

Steps 1–5 below were completed for the endpoint-only transition. One small-PVC
backup was subsequently authorized and completed. The isolated restore in Step 6
still requires separate authorization. This remains the reusable procedure,
not an instruction to reapply a patch or overwrite a working volume.

1. Confirm Git/CI, Argo health, Longhorn volumes and the default target. Record
   numeric backup-volume/object counts and freshness; do not persist raw Secret
   manifests. Defer while backup/restore operations are active. Record the
   next backup schedules and choose a quiet window. Longhorn RecurringJob CRs do
   not expose `suspend`; their generated CronJobs are controller-owned, so a
   manual CronJob pause may be overwritten. Do not assume such a pause is stable.
   If a quiet window cannot be secured, defer the switch and prepare a separately
   reviewed scheduling change; never suspend trim or unrelated tasks.
2. Create narrowly matched, time-limited maintenance silences for affected backup
   target/freshness alerts; retain their IDs and expiry. Do not hide volume or
   replica failures unrelated to this route.
3. From every relevant Longhorn manager and backup-engine network path, verify
   Service DNS, TCP8333 and signed read/list of the existing backup bucket with
   the current identity **without modifying the shared Secret yet**. Use the
   native Longhorn backup-store client or a reviewed temporary diagnostic client;
   never print Authorization headers, credentials, URLs with signatures or object
   contents. Unsigned403 alone proves neither authentication nor backup access.
   Stop on signature/region, policy, redirect or missing-object errors.
4. Obtain only the Secret resourceVersion and prepare the patch outside Git:

   ```sh
   kubectl get secret -n longhorn-system longhorn-backup-s3 -o jsonpath='{.metadata.resourceVersion}'
   python3 tools/bootstrap/prepare_longhorn_s3.py --resource-version VERSION > /tmp/longhorn-s3-forward.json
   ```

   After reviewing it and receiving live authorization, execute only:

   ```sh
   kubectl patch secret -n longhorn-system longhorn-backup-s3 --type=json --patch-file=/tmp/longhorn-s3-forward.json
   ```

   A failed precondition means stop and re-inspect, not force/replace the Secret.
5. Longhorn polls the target every five minutes. Verify it consumes the updated
   endpoint and reports available; if it does not reload the Secret, stop and
   inspect the pinned version's behavior before authorizing any restart. Compare
   the existing backup inventory and run `python3 tools/ops/verify.py backups`.
6. Run one separately authorized disposable-volume backup and an isolated restore
   to a new volume/PVC; verify test data, backup time and successful completion.
   Never restore over a working volume, delete production data or use production
   database writes as a probe. Check actual manager/engine traffic uses the direct
   endpoint. Do not stop public Traefik merely to demonstrate independence.
7. Confirm the next intended backup succeeds, check Argo/alerts, and remove
   maintenance silences. Restore any scheduling settings explicitly changed by a
   separately approved maintenance plan.

Signed read/list, target reconciliation and direct controller traffic are verified.
One small existing-PVC full backup passed. The isolated-restore portion of Step 6,
the next scheduled backup, full cold boot and full disaster recovery remain
untested. A warm image cache is not
proof of upstream registry availability.

## Rollback

On new endpoint errors, secure a quiet window and wait for active operations
before changing it back. Read the **current** resourceVersion,
then generate `prepare_longhorn_s3.py --rollback --resource-version VERSION` and
use the same scoped `kubectl patch secret` operation. The rollback tests the
internal endpoint before restoring the original public HTTPS value. It restores
no old credentials and needs no workload restart by default.

Verify the old target is available with the same inventory, resume only jobs
paused by this work, remove silences, and report that the public-Traefik recovery
dependency is back. During a real DR outage that public route may be unavailable;
rolling back routing does not repair the outage. Keep backups and volumes intact.

## Local verification

```sh
python3 -m unittest discover -s tests -p 'test_longhorn_internal_s3.py' -v
python3 -m unittest discover -s tests -p 'test_cron_dependency_gate.py' -v
python3 tools/bootstrap/prepare_cron_gate.py > /tmp/logs-check-gated-candidate.yaml
```

Tests exercise conditional patch/rollback, credential preservation with synthetic
data, existing Service/policy consistency and the inactive per-Job gate. No live
Secret update, backup, restore, rollout or failure injection occurs.

Initial unsigned403 checks established only reachability. The subsequent signed
acceptance covered all managers and instance-managers and a complete metadata
catalogue comparison; see the execution record for scope and remaining limits.
