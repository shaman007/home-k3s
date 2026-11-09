# Firefox Sync 0.24.1: MySQL → MariaDB preparation

Prepared and executed 2026-11-09. **Production now runs on MariaDB 12.3.3.**
See [execution results and GitOps handoff](EXECUTION.md). The initial live cutover
preceded publication; reconciliation must resume only against the final MariaDB manifests. All YAML here
is outside the Argo Application source (`firefox-sync/`); do not point Argo at this
directory or submit the entire directory as Kubernetes resources (it includes
strategic merge patch fragments).

## Compatibility evidence

The running server and GitOps manifest both pin `syncserver-mysql:0.24.1` at
`sha256:9ca8df54026925f88c443e9cd3a26a0f0bdac055cde47ff181497526566992a6`.
The migration source was MySQL 8.4.13 with a separate 5 GiB Longhorn `mysql-data` PVC.
Argo reported Synced/Healthy before maintenance.

- The [0.24.1 changelog](https://github.com/mozilla-services/syncstorage-rs/blob/0.24.1/CHANGELOG.md)
  includes the MariaDB compatibility fix released in 0.22.0, commit
  [b1ca7b32](https://github.com/mozilla-services/syncstorage-rs/commit/b1ca7b32deeb4b5a6d32d875ebfbc8b5e2924629).
  [The pinned read-lock implementation](https://github.com/mozilla-services/syncstorage-rs/blob/0.24.1/syncstorage-mysql/src/db/db_impl.rs)
  uses `LOCK IN SHARE MODE`, addressing the earlier `FOR SHARE` incompatibility.
- All six Syncstorage and nine Tokenserver `up.sql` migrations in the pinned
  release were inspected: ordinary InnoDB tables, indexes, a temporary stored
  procedure, and DML; no evident MySQL-only blocker was found. This is a source
  review; all migrations subsequently executed successfully during rehearsal.
- Existing storage tables use `latin1_swedish_ci`; Tokenserver uses a mixture of
  `utf8mb4_0900_ai_ci` and `utf8mb3_general_ci`. Preserve these definitions and the
  Diesel migration history by logical dump/import of **both** databases.
- Target: `mariadb:12.3.3` (LTS), official multi-platform manifest digest
  `sha256:d46e102fa8b9b72bfcdeb56f9dd538742092119dc8b11f31fe662605cd234cd9`,
  resolved read-only with skopeo on 2026-11-09. The Harbor proxy pull and non-root
  startup passed during rehearsal. [Official image source](https://github.com/MariaDB/mariadb-docker/blob/bdfe641466a5312bb97d06a1a4e1fb411c49e6b6/12.3/Dockerfile)
  identifies this release as Stable / Long Term Support.
- MariaDB [supports `utf8mb4_0900_ai_ci` as an alias](https://mariadb.com/docs/server/reference/data-types/string-data-types/character-sets/supported-character-sets-and-collations)
  for `utf8mb4_uca1400_nopad_ai_ci`. This is Unicode 14 rather than MySQL's
  Unicode 9 sorting semantics. Import must pass all unique constraints; row-value
  comparison and application tests remain mandatory. Do not blindly replace
  collations in SQL dumps.

The MySQL protocol URLs, application image, OpenBao keys, signing secrets,
credentials, public node URL and client settings stay the same. The candidate
uses MariaDB environment variable names referencing the existing Secret keys.
The MySQL-specific `--mysqlx-socket` option is removed. Its socket and PID live in
writable `/tmp`; root filesystem remains read-only and UID/GID remains 999.

## Artifacts

- `candidate.yaml`: new MariaDB Deployment and independent `mariadb-data` PVC.
  It references the existing `mysql-init` ConfigMap to grant access to Tokenserver.
- `network-policies.yaml`: additive access rules for production Sync to MariaDB;
  existing DNS policy already covers all pods.
- `rehearsal.yaml`: separate fresh MariaDB/PVC, private Service, isolated Sync
  0.24.1 Deployment and its access policies.
  Its labels cannot match the production HTTP Service. Only its database URLs
  differ; no public Ingress is added. This tests fresh migrations and synthetic
  writes without populating the real import target.
- `service-cutover.patch.yaml` / `service-rollback.patch.yaml`: reviewed selector
  changes for the existing `mysql` Service. These are patch fragments, not objects.
- `tools/firefox-sync/migrate-mariadb.py`: no-op plan by default; explicit
  `--import-data` streams both schemas to an empty candidate and compares them.
  `--verify` repeats only the read-only comparison. SQL stderr is suppressed so
  failed INSERT statements cannot expose records. It never changes cluster
  control state, retrieves credentials, or writes a dump file.

## Execution runbook (requires authorization for live changes)

1. Record current Deployment replicas, Service selectors, Argo auto-sync settings,
   active sync operation, image digests and PVC bindings. Pause Firefox Sync
   Application auto-sync and prevent its parent Application from restoring it;
   wait for any active Argo sync operation to finish. Do not publish a cutover
   selector while automatic reconciliation can race the migration.
2. Provision **only** `candidate.yaml` and `network-policies.yaml` using an approved
   GitOps or explicitly authorized live-create workflow. Keep the existing
   Service selecting `app: mysql`. Wait for MariaDB readiness, then confirm
   version, collation availability and non-root startup. Confirm the mounted PVC
   is `mariadb-data`, not `mysql-data`. Never mount the MySQL datadir into MariaDB.
   Separately provision `rehearsal.yaml` and wait for its two Deployments. Check
   that all fresh Diesel migrations succeed, then port-forward
   `deployment/firefox-sync-mariadb-check` local port 18000 to pod port 8000.
   Check both heartbeat endpoints and the expected unauthenticated Tokenserver
   401. Run `python3 tools/firefox-sync/verify-storage.py` against its default
   local URL: this authorized rehearsal writes/reads/deletes synthetic records
   only in `mariadb-rehearsal-data`. Require a passing result before downtime.
   Stop the rehearsal Sync Deployment after testing and retain its volume.
3. Stop production Firefox Sync and wait for all its pods to disappear. MySQL
   remains running. With application writers stopped, take a recoverable backup
   of the original PVC using the existing approved backup mechanism and confirm
   it completed. Preserve the corresponding OpenBao secret through its normal
   protected backup process; do not export it to this repository or logs.
4. Run `python3 tools/firefox-sync/migrate-mariadb.py --import-data` only after
   authorization to write candidate data. It checks that auto-sync is paused,
   no sync operation is active, production Sync has no pods, the Service still
   selects MySQL, the PVCs are distinct, versions match and the target has no
   tables. It dumps only `syncstorage` and `tokenserver`, including
   `__diesel_schema_migrations`; it does not copy MySQL system accounts.
   Both dump and import exit statuses must succeed. A partial import is a stop
   condition: do not retry on the same populated candidate, drop databases,
   delete PVCs or resume Sync automatically.
5. The helper checks identical table inventories and column names, exact row
   counts and SHA-256 fingerprints of every column value in every table,
   including Tokenserver IDs, nodes and both migration histories. NULL and empty
   values are distinct, and row hashes are sorted before aggregation. Only table
   names/counts are printed. All tables must match before starting a writer.
6. The fresh-schema rehearsal from step 2 must already have passed. Confirm the
   rehearsal Sync has stopped and its pods have disappeared. Keep its database
   separate from the imported candidate; do not redirect its URLs to the latter.
7. Repeat `--verify` before cutover. Never waive a data mismatch without
   identifying its cause. Keep the imported candidate free of writers until this
   check has passed. Do not run the verifier through public HTTPS yet: it still
   routes to production.
8. Prepare the final GitOps state while auto-sync remains paused: copy the two
   candidate objects and the two production MariaDB policies to `firefox-sync/`;
   change `service-mysql.yaml` selector to `app: mariadb`; set the old MySQL
   Deployment replicas to zero, retaining its manifest and PVC. Preserve the
   existing app, secret and init manifests. Do not publish rehearsal resources.
   Add `renovate-rule.json` to the root Renovate `packageRules` to keep this new
   MariaDB Deployment on `12.3.x`; do not merge PR #1117 as part of this migration.
9. Switch the existing Service to the imported MariaDB and verify its ready
   EndpointSlice points only to the MariaDB pod. Resume production Sync with its
   original replica count. Verify schema startup, public HTTPS heartbeats,
   expected unauthenticated 401 and the existing synthetic verifier through HTTPS.
   Then sync a fresh test bookmark between two Firefox profiles and inspect
   client sync errors. Heartbeats or a successful import alone do not establish
   compatibility. Watch Tokenserver enrollment, batch writes and lock errors.
10. After approved publication/reconciliation of the final GitOps state, restore
    the original Argo sync policy, verify Synced/Healthy and arrange recurring
    backups plus a restore test for `mariadb-data`. Keep the old MySQL PVC through
    the agreed soak period; this preparation never authorizes its deletion.

### Rehearsal data and rollback

Fresh-schema rehearsal uses `mariadb-rehearsal-data`; import uses `mariadb-data`.
The helper deliberately rejects populated import targets. Rehearsal workloads
have unique labels, so production Services cannot route to them. The public node
URL in the rehearsal database is intentionally preserved, but do not sign real
Firefox clients into the rehearsal: issued tokens would direct them to the public
production endpoint. The local synthetic verifier supplies its own local node URL.
Do not delete test artifacts automatically.

Before production writes to MariaDB, rollback is straightforward: stop rehearsal
and production Sync, restore the Service selector from the rollback patch, ensure
MySQL is ready, and resume Sync at its original replica count. Restore the old
GitOps state before re-enabling auto-sync. No source rows or source PVC changed.

After production writes to MariaDB, the old MySQL is stale. Do not blindly switch
back: stop writers and plan a verified reverse logical transfer or explicitly
accept the loss of post-cutover writes. Preserve both volumes and signing secrets.

## Validation status

Fresh migrations, frozen-data import, all-table value comparison and the expanded
Hawk API suite passed on MariaDB, including public production HTTPS. The user
chose to verify actual Firefox sign-in and two-client sync themselves. A physical
backup restore remains untested. See [execution details](EXECUTION.md) for retained
volumes, backup completion and the temporary GitOps reconciliation pause.
