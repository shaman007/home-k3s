# Internal S3 cutover — 2026-11-14 (Europe/Prague)

User authorized signed access checks and sequential Loki → Thanos migration.
Stage-one policies were reconciled by all three owning Argo Applications at
`02452391`, Synced/Healthy, with the expected resource tracking annotations.

## Signed access and baseline

Using the installed AWS CLI signing implementation and current credentials only
in memory, performed bounded signed list+GET through both public/internal routes
from the actual client Pod networks. Loki used its existing Python rules sidecar
in the same Pod; Thanos used its existing wget. No ephemeral Pods/containers or
credential files were created. Object contents and credentials were not logged.

* Loki: two listed objects, 766-byte existing object sample, identical paths/read hash.
* Each Thanos client: two listed objects and existing block meta.json (7128 bytes),
  matching both routes. Large block chunks were not downloaded.
* Baseline: Loki mail logs two hours old; Thanos sum(up) at a fixed four-day-old
  timestamp returned 159 without warnings; current metrics returned 162.

## Ordered live changes

1. **Loki**: paused only its Argo reconciliation. Guarded JSON patches changed
   only common/ruler S3 endpoint+insecure fields and the matching StatefulSet
   Helm config checksum. Exact pinned-chart render had first matched live config
   and checksum. New Loki Pod became 2/2 Ready with zero restarts. Runtime /config
   confirms internal S3; identical historical query and fresh log query succeeded.
   Initial empty-ring/pattern-ingester startup delays recovered normally.

2. **Thanos Store Gateway**: paused only `thanos` Argo reconciliation. Created
   ESO target `thanos-store-objstore-internal` from the unchanged OpenBao property
   `monitoring/objstore.yml`. Real ESO output differs only in endpoint/insecure;
   credentials and all other settings are semantically identical. Switched only
   the store Deployment Secret reference, retaining its index PVC. New Pod Ready,
   S3 operation failure counter zero, four-day query unchanged (159/no warnings).

3. **Compactor**: independently derived `thanos-compactor-objstore-internal`,
   then changed only its Deployment Secret reference after store acceptance.
   New Pod Ready, S3 operation failure counter zero and four-day query unchanged.
   Bucket retention, delete delay, compaction settings and data PVC preserved.

4. **Sidecar last**: only after both previous clients used isolated targets,
   transformed the original shared ExternalSecret to internal S3. Verified real
   ESO output and waited for the mounted file projection. Sent SIGTERM only to
   the verified `thanos` PID1 in its separate container PID namespace. Kubelet
   restarted that sidecar once. No Prometheus Deployment/Pod-template change.

Prometheus retained Pod UID, containerID, start time (2026-11-13 09:31:03 UTC)
and restartCount=0. Its process start metric stayed unchanged; float/histogram
sample counters increased by 420351 during the final observation. Sidecar Ready,
S3 operation/upload failure counters zero; the historical query still returned
159 with no warnings. **No new block upload occurred after restart during this
window**; the next natural two-hour block upload remains a follow-up check. No
TSDB flush, forced block creation or ad-hoc S3 write/delete test was performed.

The public route remains usable: signed read/list repeated after cutover from
the new store/compactor Pods and sidecar matched internal access. All Loki cache,
gateway/canary and Thanos/Grafana Pods are Ready. Final Alertmanager inventory
had no related active alerts. Grafana and Querier were not restarted.

## GitOps handoff

Runtime/source changes are prepared locally, not yet committed/published. Only
Argo Applications `loki` and `thanos` have temporary skip-reconcile=true; their
auto-sync policy itself is unchanged. Keep these annotations until the user
publishes matching client-config sources, then verify exact desired config and
remove only those two pause annotations. Argo health/sync fields while paused
are stale evidence and do not replace the runtime acceptance above.

The standard read-only Argo verifier reports the expected skip-reconcile issue
for those two apps. No other application reconciliation was paused. Client
credentials remain in OpenBao; three runtime Kubernetes config Secrets are
ESO-owned. No OpenBao source or plaintext credential file was changed.

## Validation and maintenance

755 repository tests passed (16 skips), including per-client ESO/mount isolation
and canonical guarded transforms. Runtime contracts, Ruff/Pylint and strict
Deployment schemas passed. Local rendered Loki diff changes only four transport
fields; bucket/schema/retention/credentials/PVCs remain unchanged.

All 13 scoped 30-minute silences were explicitly expired after stage acceptance.
Unexpected S3/WAL/compaction/upload failure rules were not disabled.

| Scope | Silence ID | Original expiry (Europe/Prague) | Final state |
| --- | --- | --- | --- |
| Loki internal S3 endpoint cutover | `94cf8af8-c337-4340-85e2-be697ce44553` | 2026-11-14 01:03:44 CET | expired |
| Loki internal S3 endpoint cutover | `fd76e5de-832a-430a-840e-1484dfa95223` | 2026-11-14 01:03:44 CET | expired |
| Loki internal S3 endpoint cutover | `8be4b838-97d8-408d-9327-bd2c89434488` | 2026-11-14 01:03:44 CET | expired |
| Loki internal S3 endpoint cutover | `9cf95719-a6a7-4545-8f54-e616c7d448bc` | 2026-11-14 01:03:44 CET | expired |
| staged Thanos internal S3 transition | `4c5da578-9b0e-4c9d-9160-10964ec7c798` | 2026-11-14 01:05:53 CET | expired |
| thanos-store-gateway isolated internal S3 switch | `bdb8be5a-06a4-43d0-b44a-2a4f5980867d` | 2026-11-14 01:06:24 CET | expired |
| thanos-store-gateway isolated internal S3 switch | `7c20354f-4710-4208-9fb0-2150c36e7e3c` | 2026-11-14 01:06:24 CET | expired |
| thanos-store-gateway isolated internal S3 switch | `14527263-97ba-4f9f-997b-df8e1cc23291` | 2026-11-14 01:06:24 CET | expired |
| thanos-compactor isolated internal S3 switch | `92cb5cd0-a573-4f2e-820e-2b0bec409537` | 2026-11-14 01:07:10 CET | expired |
| thanos-compactor isolated internal S3 switch | `847a7bd1-5cc0-4035-987a-771503f3b817` | 2026-11-14 01:07:10 CET | expired |
| thanos-compactor isolated internal S3 switch | `343d54a6-f850-4896-9cb0-93d0307cf461` | 2026-11-14 01:07:10 CET | expired |
| Thanos sidecar-only internal S3 restart | `baecf10f-87e4-4e2a-a180-1b3b975bc765` | 2026-11-14 01:08:20 CET | expired |
| Thanos sidecar-only internal S3 restart | `92363a8a-0571-4f46-90e9-ba07f1ef6494` | 2026-11-14 01:08:20 CET | expired |

## Rollback prepared (not needed/executed)

Non-secret pre-change snapshots, guarded rollback scripts and read-only evidence
are in `/tmp/observability-cutover-02452391` (workstation scratch; not a durable
backup). Git `02452391` retains original declarative sources. No Secret payload
was written there.

Reverse order if rollback is needed:

1. Restore the original shared ESO data mapping/template first, wait for public
   target+mounted projection, then restart only the sidecar as above. Verify
   Prometheus container/start remains unchanged and both recent/historical queries.
2. Restore compactor and then store gateway Secret references to the original
   `thanos-objstore-secret` only after that shared config is public again. Wait
   for each rollout and verify before proceeding. Do not switch them to a shared
   file that still contains the internal endpoint.
3. Restore the old Loki config and exact prior checksum, verify /ready, historical
   and fresh ingestion. Keep old route permissions, bucket contents and all PVCs.
4. Restore the corresponding local/Git declarations; remove maintenance pauses
   only once desired Git and live state agree. New unused ESO targets can remain
   for review; no cleanup/deletion is required for restoring traffic.

Example prepared scripts (mutating; execute only within authorized rollback):

```sh
python3 /tmp/observability-cutover-02452391/rollback_sidecar.py
python3 /tmp/observability-cutover-02452391/rollback_thanos_deployment.py thanos-compactor
python3 /tmp/observability-cutover-02452391/rollback_thanos_deployment.py thanos-store-gateway
python3 /tmp/observability-cutover-02452391/rollback_loki.py
```

Re-create narrowly scoped expiring maintenance silences if an authorized rollback
is actually undertaken. Never delete S3 objects, reinitialize buckets, alter
retention or start competing TSDB writers as part of this endpoint rollback.
