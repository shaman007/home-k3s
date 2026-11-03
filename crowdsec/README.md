# Rootless CrowdSec

Prepared 2026-11-03 for chart 0.24.2 / CrowdSec v1.8.1. Agent, LAPI, registration
init and database-preparation init use UID/GID 1000, runAsNonRoot=true, no Linux
capabilities, no privilege escalation and RuntimeDefault seccomp. There is no
root init container or Kyverno exemption.

The image recipe and reusable integration test live in the sibling
`Dockerfiles/crowdsec-rootless` checkout. The base image is pinned by digest;
the published reference is `harbor.andreybondarenko.com/library/crowdsec-rootless:v1.8.1-rootless.1`.
The image was published to Harbor and verified by digest before the GitOps
cutover. Both image references in the values are pinned to that digest.
The built image is tested on AMD64; all three current nodes are AMD64.

## Image startup

Application staging/data paths belong to UID 1000. The image keeps `/etc` owned
by root, changes only its group to 1000, and sets mode 1775. This lets the chart
create its `/etc/crowdsec` entry while the sticky bit protects existing root-owned
entries from removal. Existing `/etc` files remain root-owned and unwritable by
the application. The writable container layer is intentional: making it
readOnlyRootFilesystem would require a different startup design.

The chart commands and upstream entrypoints are retained. Registration tokens,
LAPI secret, bouncer keys, machine credentials, selective enforcement, log
acquisition and service-account/RBAC settings are unchanged.

## Existing SQLite data

fsGroup=1000 makes legacy files accessible by group, but CrowdSec explicitly
chmods its database and cannot do that on a root-owned inode. A non-root init
uses SQLite's read-only backup API to create
`/var/lib/crowdsec/data/crowdsec-rootless.db`, owned by UID 1000. The runtime
configuration selects that same path. The backup API includes committed WAL
contents; this is not a plain copy of a possibly incomplete database file.

LAPI remains one replica with explicit Recreate strategy, so the old writer is
stopped before migration. The helper verifies the copy and atomically publishes
it without replacing an existing target. It rejects corrupt input, symlink
paths, and invalid/empty or wrongly owned existing targets. A valid existing
rootless database is checked and reused on later restarts. The legacy
`crowdsec.db` stays in place. Configuration/database PVCs are retained; no root
chown job, database deletion, account reset or new production credential is used.
The observed legacy database was about 10 MiB with over 900 MiB free, sufficient
for the additional copy.

**Rollback:** after the rootless instance accepts writes, the retained legacy
file is an old snapshot. Do not revert db_path to it and silently discard newer
registrations, events or decisions. Any return to a stock root image must use
the current database and a separately coordinated offline ownership/permission
plan. Prefer fixing/rolling back the UID-1000 image while keeping the current
rootless database path.

## Validation and publication

The actual rootless Podman image passed three phases: fresh startup; restart
against root-owned/group-accessible simulated legacy files; and an idempotent
subsequent restart. Registration, agent authentication and both metrics endpoints
passed. Pre-migration agent credentials still authenticated after migration.
Runtime UID was 1000, permitted/effective/bounding capabilities zero,
NoNewPrivs=1 and seccomp filtering active. Corrupt-source, empty-target,
existing-target preservation and symlink rejection checks also passed. Test
containers and credential-bearing temporary volumes were removed.

An isolated Kubernetes Pod also verified registry pull and the same four roles
under the actual cluster runtime (without production PVCs or credentials).
That Pod produced passes for all three Kyverno policies. It was removed after
authentication, metrics and UID/capability verification.
Both rendered Deployments pass the repository's Restricted-context checks and
server admission dry runs, including all four application/init containers.
No namespace enforcement labels were changed. Resource checks and the full
repository suite passed; a regression test checks that migration/runtime paths,
image versions, one replica and Recreate remain aligned.

The previous security wave is live at `7572bc7e`: Plex and Mastodon's current
controllers pass the escalation policy. Existing Mastodon Jobs retain their old
templates; that is not evidence of the next new-template execution.

After image publication and the user's Git push, verify both Argo Applications,
init completion, UID/capability state, all three current-controller Kyverno
results, Traefik acquisition, LAPI/bouncer connectivity and the new database.
Production fsGroup migration, live credentials and end-to-end detection remain
rollout checks; the isolated tests did not read production credentials/data.
