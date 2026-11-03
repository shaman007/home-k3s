# Remaining application non-root audit

Audit date: 2026-11-02. Scope: harden compatible applications and retain necessary
root exceptions, as requested. Changes are prepared in Git; production rollout
and final Kyverno report clearance require publication and reconciliation.
No admission enforcement, mutation policies, blanket exemptions, namespace
security labels, credentials, or persistent-data ownership were changed.

## Follow-up: Unbound and OpenBao capability guards (2026-11-03)

Published revision `d9c2d594` passed CI. Hister and Postfix replacement pods are
Ready with zero restarts and successful permission inits. Hister's capability
audit is Skip under its reviewed init exception; Postfix still fails the strict
capability audit because its main mail server has no drop list. The scheduled
Mastodon bookmarked-media job completed with zero capabilities in both roles,
1,387 downloads and 1,357 description updates without failures. Its optional
face-detection queue request returned HTTP 403 because it requires admin access;
credentials and permissions were not broadened.

The next prepared changes are:

* Unbound: remove CHOWN, retain only NET_BIND_SERVICE, and make its root filesystem
  read-only. Its direct binary invocation and configuration disable user changes,
  chroot, PID files, file logging and DNSSEC trust-anchor writes. An isolated run
  of the same image/configuration answered deterministic UDP and TCP DNS queries
  with the proposed guards; its capability bounding/effective sets contained only
  NET_BIND_SERVICE, with no-new-privileges and seccomp active.
* OpenBao: drop ALL capabilities through the pinned chart's server container
  security context. Existing production processes run as UID 100/GID 1000 with
  zero effective/permitted capabilities and SKIP_CHOWN=true. Isolated OpenBao
  2.7.2 started an uninitialized Raft server and served its health endpoint with
  zero bounding/effective capabilities. This does not test production TLS,
  unsealing or multi-node Raft behavior.

Reproduce with `python3 tools/security/test-service-capability-guards.py` using
rootless Podman. The probes use disposable storage, no production credentials,
no published ports and no external network. Both proposed workloads pass the
actual strict capability CEL policy without exceptions and Kubernetes schemas.

Unbound rolled at revision `4db46f06`: its replacement pod is Ready with zero
restarts, a read-only root mount and only NET_BIND_SERVICE in its effective and
bounding sets. Public and cluster DNS queries through its Service passed over
UDP and TCP; the capability policy reports Pass on the Deployment and Pod.
OpenBao's live template has drop ALL, but its existing pods are unchanged.
OpenBao retains its OnDelete update
strategy: reconciliation updates the template but existing pods retain their
current bounding sets until an explicitly authorized, one-at-a-time maintenance
replacement. Check readiness and DNS after Unbound rolls; verify OpenBao's actual
bounding sets and audit results only after its controlled replacements.

## Prepared application changes

### Backup SSH and Collabora follow-up (2026-11-03)

Backup SSH now declares drop ALL with only CHOWN, DAC_OVERRIDE, FOWNER, SETGID,
SETUID, SYS_CHROOT and NET_BIND_SERVICE. These retain startup ownership/user
setup, OpenSSH privilege separation, authenticated user switching and port 22.
No host storage, authorized keys, existing host keys, rsync restrictions or
no-escalation settings are changed. The image's actual entrypoint and repository
key-copy hook passed startup plus key-authenticated rsync upload/download of a
file and symlink in disposable storage with exactly that bounding/effective set,
no-new-privileges and seccomp. The probe never mounts production backup data or
credentials. Strict capability auditing still fails because the required
additions exceed NET_BIND_SERVICE; no main-container exception was introduced.

Collabora now explicitly declares UID/GID 1001 and privileged=false, matching
the running production container's identity. Retain CHOWN, FOWNER, SYS_CHROOT
and allowPrivilegeEscalation=true for its file-capability document-jail helper.
The same image started as 1001:1001 under the existing capability restrictions,
served WOPI discovery and created a spare document-jail child in an isolated
probe. Opening/saving a production document remains a rollout follow-up.
Existing narrow escalation exceptions remain unchanged; the capability audit
finding remains visible.

Reproduce with `python3 tools/security/test-backup-collabora-guards.py` using
rootless Podman. Test SSH identities are generated in a temporary private
directory and removed on exit. Both manifests passed chart/schema validation;
publication and live replacement verification remain required.

| Workload | Identity and change | Verification |
| --- | --- | --- |
| Connectivity exporter | UID/GID 65534; require non-root | Published image already runs as 65534; isolated probe read code and mounted configuration |
| Year | UID/GID 101, fsGroup 101; require non-root | Isolated startup with emptyDir writable paths served HTTP successfully |
| WordPress daily report | UID/GID 65534; require non-root | Probe parsed report script and checked CA trust and service-account token readability; report/email not executed |
| Nextcloud cron | UID/GID 33; require non-root; prohibit escalation; execute PHP directly instead of sudo | Probe checked PHP syntax, config readability and config/data directory write access on existing PVC; cron not executed |
| Your Spotify FerretDB PostgreSQL | UID/GID 999; require non-root; retain existing fsGroup | Production postmaster already runs as 999 and data/socket directories have matching ownership; isolated emptyDir instance started and passed SELECT 1 |
| Collabora | Require non-root through chart container securityContext | Running container identity and published image metadata confirm UID/GID 1001; chart render confirms guard reaches container |

All six Argo Applications rendered successfully. Their 24 rendered containers
passed resource-budget checks with namespace defaults. All six proposed changes
passed API-server strategic-patch dry runs. Admission still reports unrelated
Restricted warnings for missing capability drops/seccomp on several workloads,
and Collabora's escalation setting; this is a non-root wave, not full Restricted
compliance. Runtime probes were removed after verification; completed probe Jobs
use a short TTL. No production application deployment was changed directly.

## Retained root startup dependencies

These remain visible audit findings. They are documented operational boundaries,
not Kyverno PolicyExceptions or evidence that a rootless redesign is impossible.

| Workload/source | Current dependency | Review trigger |
| --- | --- | --- |
| backup-rsync | Root SSH master and multi-user privilege separation | Dedicated rootless backup transport/image |
| CrowdSec agent/LAPI and agent registration init | Stock image startup required root; replacement image and non-root SQLite migration are now prepared | See [rootless cutover](../crowdsec/README.md) |
| Mail Dovecot/Postfix, Postfix queue init | Master processes manage separate users and queue ownership | Vendor-supported rootless mail architecture |
| Mail Unbound | Direct resolver binary currently runs as root and binds DNS port 53; CHOWN removal is prepared | Verified rootless identity and bind configuration |
| Mail rspamd-spam-trainer | Starts private Dovecot master/auth services before mailbox operations | Separate privilege-safe training architecture; do not test by modifying mailboxes |
| Plex | Linuxserver s6 startup fixes ownership and drops to configured application user | Supported rootless image lifecycle |
| RIPE Atlas and prepare-atlas-runtime | Root bootstrap owns runtime directories, then drops to ripe-atlas with NET_RAW | Image/bootstrap redesign preserving raw-socket operation |
| Mastodon bookmarked-media-sync, both containers | Runtime apk/global npm installation in current stock images | Prebuilt tooling image, published and verified separately |

## Retained permission init containers

Application containers retain their existing non-root guards. Root is retained
only for the existing initialization role where applicable; no recursive chown
or data migration was introduced by this change. Revisit when storage is
provisioned with the required ownership or an image supports group-writable
startup without these helpers.

- Bitwarden `prepare-permissions`; Dawarich `prepare-writable-volumes`.
- ComfyUI `prepare-runtime-directories`; ConvertX `prepare-data`.
- Immich ML `prepare-cache`, server `prepare-library`, Valkey `prepare-data`.
- Karakeep `init-writable-paths`; Meilisearch `init-meili-data`.
- Rspamd `fix-perms`; Matrix `fix-permissions`; Hister `fix-data-permissions`.
- Prometheus `fix-perms`; Thanos compactor/store-gateway `volume-mount-hack`.
- NLLB `prepare-model-cache`; both Ollama deployments `prepare-ollama-data`.
- Open WebUI `prepare-data`; SeaweedFS `prepare-data-and-tmp`.
- PostgreSQL `volume-permissions` helpers for Bitwarden, Dawarich, Immich,
  Mastodon and Keycloak.


### PostgreSQL permission-init capabilities

The existing `volume-permissions` helpers for Immich, Keycloak, Dawarich,
Mastodon and Bitwarden now explicitly drop ALL capabilities and add only CHOWN
and DAC_OVERRIDE. CHOWN permits the existing ownership assignments; DAC_OVERRIDE
allows traversal of PostgreSQL-owned mode-0700 directories. The commands only
mkdir/chown, so FOWNER is not required. UID 0 and the current initialization role
remain necessary; the application containers keep their existing non-root guards.

The exact pinned BusyBox commands were tested independently for all five
manifests on disposable tmpfs data, with UID 0/GID 999 and supplemental GID 999,
only these two capabilities, no-new-privileges and default seccomp. Effective and
bounding masks were both `0x3`. Tests covered nonempty mode-0700 nested directories,
mode-0600 files, setgid directories, preserved contents and final UID/GID 999 ownership. Both the current Harbor mirror image and the cached image digest used by all
five live helpers were checked (the latter is
`docker.io/library/busybox@sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616`).
No production data or credentials were used. Reproduce with:

```sh
python3 tools/postgres/test-permission-init-caps.py
```

Only the init capability fields change. The existing commands still create
`/var/run/postgresql` in their container filesystem, so this wave does not add a
read-only root filesystem. Publishing these StatefulSet template changes rolls
the database Pods; verify each init completes, PostgreSQL becomes Ready and the
applications reconnect. Actual storage-backed startup is not proven by the tmpfs
probe and remains a deployment check.

The initial capability-limiting wave retained the strict capability findings.
The following reviewed capability-exception batch covers these five helpers
without broadening their root exceptions. Kernel capability definitions are
in [capabilities(7)](https://www.man7.org/linux/man-pages/man7/capabilities.7.html).


## Reviewed permission-init capability batch

The next batch adds 25 capability exceptions for the existing reviewed root
ownership-init roles. It keeps the original 66 root/escalation/privileged
exceptions unchanged. Exact workload identities, service accounts, labels,
container roles/names and declared image references remain mandatory. Each
capability exception additionally requires declared UID 0, no privilege
escalation, non-privileged execution, exact drop ALL and the exact addition set.
Unexpected capabilities, missing guards, changed images or moved container roles
remain Fail; an init that stops needing additions reports Pass rather than Skip.
Main and ephemeral containers are never approved for capability exceptions.

| Exact capability set | Reviewed workload count | Purpose |
|---|---:|---|
| CHOWN | 13 | Existing ownership assignment helpers |
| CHOWN, DAC_OVERRIDE | 10 | Ownership assignment through private directories, including five PostgreSQL helpers |
| CHOWN, DAC_READ_SEARCH | 1 | Immich ML cache ownership with read/traversal bypass |
| CHOWN, FOWNER | 1 | Rspamd ownership followed by chmod |

The source of truth is [the reviewed catalog](../kyverno/exception-catalog.json).
This is an audit-report exception, not an execution privilege grant. No policy
is switched to enforcement, no namespace is broadly excluded, and unrelated mail,
GPU, storage or application capability requirements remain visible. Declared
image references are matched as strings; mutable tags are not resolved to digests
by the exception. Startup/storage changes require review even when names/images
stay the same, because commands and mounts are not pinned in these expressions.

This batch also tightens running helper declarations:

- Hister's ownership init drops ALL and retains only CHOWN/DAC_OVERRIDE, with a
  read-only root filesystem. The skipped manual reindex Job mirrors those init
  guards, adds a main-container drop ALL and declares RuntimeDefault seccomp;
  it is not run or activated by this change.
- Postfix queue ownership init drops ALL and retains only CHOWN/FOWNER, runs
  explicitly as UID/GID 0 and uses a read-only root filesystem. Its chown is
  non-recursive; chmod after changing ownership needs FOWNER.
- Both bookmarked-media-sync containers drop ALL without additions. Their
  existing root startup and no-escalation settings remain. Exact apk/npm install
  phases and client version commands passed locally with zero capabilities;
  no production fetch, login, upload, description update or face-detection API
  request was executed by these probes.

Hister and Postfix exact helper commands passed on disposable restrictive tmpfs
with the reduced effective/bounding sets (`0x3` and `0x9`) and read-only root
filesystems. Contents, ownership and modes were verified. Reproduce with:

```sh
python3 tools/security/test-permission-helper-guards.py
# Also exercise the public-package installation phases, without production jobs:
python3 tools/security/test-permission-helper-guards.py --installers
```

After publication, verify Hister/Postfix rollouts and the next normal media job.
The exception-only changes do not restart the other reviewed applications. Old
Pods/ReplicaSets may retain findings until report refresh and normal history
cleanup; never delete them merely to improve counts. The original exception
expiry and its documented runtime-verification limitation remain unchanged.

## Infrastructure and ownership boundaries

GPU device plugins, feature discovery, DCGM, MIG, validators and associated init
containers; Longhorn manager/engines/CSI and recurring jobs; MetalLB speaker/FRR
and helper init containers; and privileged image-builder build/checkout remain
vendor or infrastructure exceptions. A guard must not disable host-device,
network, storage or build operations without a component-specific redesign.

The GPU Operator controller already runs as UID/GID 1000 (chart v26.7.2), but
its explicit non-root guard remains a chart gap. Longhorn UI runs as UID 499/GID
486; explicit UI guards and capability/escalation/seccomp guards for the
non-privileged CSI clients are prepared in
[the reviewed component hardening](../longhorn/component-security.md).
The CSI clients retain UID 0 because their live root-owned 0755 Unix socket
requires owner write permission. These are verified socket-access requirements,
not a reason to add unreviewed namespace-wide exceptions.

Kube-system remains outside the existing audit-policy scope and under Talos/
bootstrap ownership; CoreDNS and kube-state-metrics already run non-root.
Lenka MySQL has no application manifest in this repository and remains an
owner-managed playground, explicitly outside the hardening feature in
[the specification](../specs/001-cluster-hardening-backlog/spec.md).

Reports were compared against current controller identities. Historical
ReplicaSets/Pods may retain findings after a controller is fixed; do not delete
resources merely to force aggregate counts to zero.

## Rollout follow-up

After publication, check Argo revision and health, replacement pod readiness,
actual identities and current-controller policy results for all six changes.
Year, exporter, Collabora and FerretDB templates cause replacement pods; monitor
FerretDB startup against its existing PVC without deleting or reinitializing it.
CronJob template changes affect future Jobs, so verify the next scheduled
WordPress report and Nextcloud cron separately. The safety probes deliberately
did not send report mail or execute production maintenance.

An accepted admission dry run or a successful isolated probe does not prove a
production rollout or all application functions. Check exporter metrics/checks,
Collabora document handling, Year HTTP, and Your Spotify database connectivity
following reconciliation. Remaining documented exceptions will continue to
produce non-root audit findings.
