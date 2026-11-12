# Verifiable operational procedures

Run these from the repository root with Python 3, PyYAML and `kubectl` configured
for the cluster. PyYAML is also used by the repository tests. These procedures
only collect Kubernetes API data with bounded `kubectl get` requests; they do not
sync, refresh, pause, scale, restart, back up or restore anything.

```sh
python3 tools/ops/verify.py argocd
python3 tools/ops/verify.py backups
python3 tools/ops/verify.py baseline
```

The default context is explicitly pinned to `admin@home-k8s` on every request.
Use `--context NAME` to deliberately select another context. This bypasses neither
RBAC nor sandbox/network policy. The checks contain home-cluster expectations
(namespaces, backup schedule and the Lenka exception); changing context does not
make them generic checks for a different cluster. `--timeout 15` bounds each API
request; the subprocess deadline is five seconds longer. There is no polling.

Each valid invocation prints one JSON document to stdout:

| Field | Meaning |
| --- | --- |
| `format_version` | Output contract version, currently `1` |
| `procedure`, `context`, `checked_at` | Selected scope and UTC observation time |
| `status` | `passed`, `failed`, or `error` |
| `checks` | Individual decisions and selected evidence; inspect `review_details` or `details` for failures |
| `limitations` | What this procedure does not establish |
| `error` | Collection/input assessment failure without raw stderr or API bodies |

Exit codes: **0** = all checks in this procedure passed; **1** = checks found a
problem; **2** = collection or assessment could not complete. Invalid CLI options
also exit 2 through argparse, with usage on stderr rather than a JSON report.
An API/RBAC error, invalid response, timeout or empty required inventory never
passes. Do not ignore the exit code or interpret an empty report as success.

To retain a non-secret report outside Git:

```sh
umask 077
python3 tools/ops/verify.py baseline > /tmp/home-k8s-baseline.json
```

The output selects identities, counts, status and version fields. It excludes
Secret objects, environment values, pod specs, raw API responses and arbitrary
Argo condition messages. It still contains internal resource names; keep it
private. A failed collection produces an error report, not a complete snapshot.

## Argo CD reconciliation and revision gate

`argocd` reuses the pure assessment functions from the deployed
[platform health report](platform-health-checks.md), without loading its API,
ConfigMap-write or email-delivery functions. It requires Healthy/Synced status,
expected automation, no paused reconciliation, no conditions, no deletion and no
pending/running/failed operation. Lenka retains only its documented self-healing
exception. This does not request a controller refresh; status may be stale.

For a deployment handoff, select an application and an exact expected revision:

```sh
python3 tools/ops/verify.py argocd --app argocd-install --revision FULL_COMMIT_SHA
```

For a multi-source Application, identify the source position in its manifest
before checking it; the index is one-based:

```sh
python3 tools/ops/verify.py argocd --app longhorn --source-position 2 --revision FULL_COMMIT_SHA
```

The tool compares that specific source's observed revision, never just membership
in the list of all source revisions. A missing application/revision fails; an
ambiguous multi-source selection is an error. A Helm source expects its observed
chart revision rather than a Git commit. Read the app manifest to select the
appropriate source and expected revision.

Keep these handoff gates separate:

| Gate | Required evidence |
| --- | --- |
| Local change | Reviewed diff and relevant tests; not a deployment |
| Published change | Expected commit present on the configured remote ref; read with `git ls-remote` if needed |
| Reconciled change | This procedure passes for the selected app and exact expected source revision |
| Functional application | App-specific request or workflow succeeds against the intended endpoint |

This tool implements the reconciliation gate. It does not publish Git, resolve a
branch to a remote SHA or issue an application request. A Healthy/Synced result
without `--revision` is an inventory health observation, not proof that a new
change deployed. For application-specific probes, follow the app README and
[upgrade playbook](upgrade-playbook.md).

## Backup freshness and recovery gates

`backups` checks:

- Every Longhorn volume selected for backups has a Completed backup on the same
  target created within 24 hours, using `backupCreatedAt`, not `lastSyncedAt`.
  Trim-only volumes are outside that coverage; no expected volumes fails.
- Longhorn backup/trim RecurringJobs have matching unsuspended CronJobs and recent
  successes for their schedules. It reuses the daily report's fixed-monthly
  schedule handling. Missing policies or generated CronJobs cannot silently pass.
- `talos-backup/talos-backup` is unsuspended and has a success within two hours.
- Backup and scheduler timestamps are not in the future.

No backup is triggered and no bucket contents are read. The hourly Talos threshold
and daily Longhorn backup-coverage threshold come from current repository policy;
review them when schedules change.

| Recovery gate | Required evidence |
| --- | --- |
| Freshness | This procedure passes, with the observation timestamp recorded |
| Independent artifact | Matching encrypted backup downloaded off-cluster, with nonempty size and recorded checksum |
| Integrity | Decryption/decompression and the format-specific integrity check succeed without persisting plaintext or keys |
| Restore | Isolated restore succeeds and the restored data/application is checked |

The executable freshness check does **not** pass the other gates. Use
[Talos etcd backup recovery](talos-etcd-backup.md) for its existing integrity and
isolated restore procedure. Application/PVC recovery needs its own matching
runbook, keys and storage. Do not restore production or create a test workload
merely to obtain a green report; those actions need scoped authorization.

## Maintenance baseline and Talos gates

`baseline` records/checks:

- Nonempty node inventory, Ready state and absence of active memory/disk/PID
  pressure, with running OS/Kubernetes version observations and scheduling state.
- Nonempty Deployment, StatefulSet and DaemonSet inventories, desired/ready counts,
  observed generations and deletion state. Original zero replica counts remain
  zero; StatefulSet PVC retention settings and resource UIDs are retained.
- Nonempty Longhorn volume inventory: attached volumes must be healthy; detached
  volumes may be healthy or unknown. Faults, degradation and transition states fail.

This is an initial observation, not a complete shutdown/restoration snapshot or a
rollout verifier. It does not inventory Jobs, CronJobs, HPAs, all custom controllers,
Longhorn disks/replicas, etcd quorum or Talos machine configuration. Ready counts
alone do not establish functional readiness or a running target release.

For authorized Talos maintenance, use these distinct stop/go gates in the
`cluster-reboot-upgrade` skill at
`/home/shaman007/.codex/skills/cluster-reboot-upgrade/SKILL.md`:

1. **Before changes:** run all three procedures. Investigate failures before
   proceeding. Verify etcd health, independent backup/recovery material, node disk
   identities, schematics/extensions and storage paths. Save the complete non-secret
   restoration state required by the skill, outside Git; the baseline alone is
   insufficient.
2. **Before the first reboot:** confirm GitOps/other reconcilers paused, Jobs and
   CronJobs suspended with originals recorded, application consumers stopped,
   volumes detached and engine/replica processes stopped. Detached/unknown is
   expected here; attached/healthy is not the shutdown criterion. The baseline is
   designed for before/after normal operation and is not this quiescence gate.
3. **Per-node return:** verify running target Talos version, Ready state, etcd
   quorum, extensions, physical disks and storage mounts. Stop on a failed gate;
   do not confuse successful image staging with activation.
4. **Recovery:** restore saved counts and controls, foundations before applications,
   with functional checks. Restore GitOps last, rerun the procedures and compare
   against the original restoration snapshot. Report remaining storage rebuilding
   independently of application recovery.

These commands never authorize or execute maintenance. Node upgrades, shutdown,
unsealing, restore drills and repairs remain separate scoped operations under the
project approval policy. Do not delete PVCs or replica data to force a gate green.

## Verification and extension

The wrapper and assessment functions are covered by repository tests:

```sh
python3 -m unittest discover -s tests -p 'test_ops_verify.py'
python3 -m unittest discover -s tests -p 'test_platform_health_report_logic.py'
```

When adding a procedure, define its inputs, read/write boundary, success and
failure criteria, output evidence, timeout and limits before adding commands.
Exercise failure cases as well as a live successful observation. Do not equate
schema validation, a successful API call or a passed metadata check with a
functional test.
