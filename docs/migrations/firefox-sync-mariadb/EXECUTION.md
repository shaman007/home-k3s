# MariaDB migration execution — 2026-11-09

Production Firefox Sync 0.24.1 now uses MariaDB 12.3.3 LTS. The user authorized
the stand, transfer and cutover while retaining the old MySQL PVC; they explicitly
deferred actual Firefox login and two-client browser verification to themselves.

## Verified

- Official pinned MariaDB image pulled through Harbor; non-root startup with a
  read-only root filesystem passed. All 6 Syncstorage and 9 Tokenserver initial
  migrations passed on the separate rehearsal volume.
- Two independently Hawk-authenticated API clients passed cross-client write/read,
  invisible staged batches, batch commit, collection timestamps and cleanup.
  The same suite passed through trusted public production HTTPS after cutover.
- Public heartbeats returned 200/200; an unauthenticated Tokenserver request
  returned the expected 401. Mozilla OAuth JWKS access from the production Sync
  container returned 200 with one key. This is not proof of a new Mozilla OAuth login.
- With production Sync stopped, both databases were streamed into a new empty
  MariaDB volume. All 10 tables matched by counts and sorted SHA-256 column-value
  fingerprints, including 14,530 BSO records, 15 collections, 20 user-collection
  rows, 2 Tokenserver users, one node, one service and both migration histories.
  Batch tables were empty. Synthetic records created after comparison were cleaned
  up by the verifier; its bookkeeping tombstone can remain.
- The first comparison exposed different INFORMATION_SCHEMA name ordering across
  engines. The helper now sorts metadata in Python. Repeated comparison passed;
  no re-import or overwrite was used to resolve this comparison bug.
- Pre-migration Longhorn snapshot and full backup
  `firefox-sync-pre-mariadb-20261109` completed (100%). The existing destination
  was verified as the user's SeaweedFS at `s3.andreybondarenko.com` before upload.
  A physical backup restore has not been tested.
- Final targeted tests: 16 passed. Strict Kubernetes validation: 7 production
  resources valid. No credentials or database payloads were printed or saved.

## Retained storage and workloads

| PVC | Longhorn volume | State at handoff |
| --- | --- | --- |
| `mariadb-data` | `pvc-5915d987-e539-4285-96b8-ecf55f36ab63` | Attached, healthy, two replicas, production |
| `mysql-data` | `pvc-963b00fb-d6ac-4a18-9ebd-d088e34e7630` | Retained, detached; old MySQL scaled to zero |
| `mariadb-rehearsal-data` | `pvc-0c23621c-3abd-41a7-8818-497d449c5c9b` | Retained test volume; rehearsal workloads removed |

The production `mysql` Service selects only `app: mariadb`; its ready EndpointSlice
was verified against the MariaDB pod. Both source and target production PVC
manifests carry `Prune=false,Delete=false`. No PVC or replica data was deleted.
The active volume inherited daily trim but has no recurring backup assignment,
matching the previous database's coverage. The migration backup is not an ongoing
backup schedule.

## GitOps handoff

At the initial live-migration handoff, source changes were local and uncommitted.
No push or PR had been performed at that point. The user subsequently authorized
commit/push and removal of the temporary guard after publication.
Parent `argocd-applications` was restored to its original policy, including
`enabled: true`, `prune: false`, `selfHeal: true`, without any new ignore rules.
Its normal reconciliation restored the child's original `selfHeal: true` policy.
At that handoff, Firefox Sync alone was temporarily held with:

```yaml
argocd.argoproj.io/skip-reconcile: "true"
```

Keep that annotation until the remote `main` manifests include the new MariaDB
Deployment/PVC/policies, the changed Service selector, stopped MySQL and source-PVC
protection. Otherwise Argo would restore the old MySQL configuration. Publish the
local changes through the normal authorized Git workflow first, then remove the
temporary annotation:

```sh
kubectl annotate application firefox-sync -n argocd argocd.argoproj.io/skip-reconcile-
```

Verify actual Synced/Healthy reconciliation and adoption after publication.
The cached Application status while skipped is not evidence of deployment.
Renovate is limited to MariaDB `12.3.x` for this Deployment.

After real client writes to MariaDB, the old MySQL is stale. Preserve both PVCs;
do not switch back blindly without stopping writers and verifying a reverse
transfer or explicitly accepting loss of post-cutover changes.
