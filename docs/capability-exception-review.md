# Reviewed application capability exceptions — 2026-11-04

This batch changes audit classification, not workload privileges or runtime guards.
All five policies stay Audit/Ignore. This batch added no seccomp exceptions;
the subsequent privileged-runtime review adds narrowly scoped ones. These
new exceptions report Skip, not Pass, and retain the existing 2027-02-01 expiry.
No privileged-container or broad namespace exception is introduced.

| Workload | Required capabilities | Reason |
| --- | --- | --- |
| backup-rsync/backup-rsync | CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID, SYS_CHROOT, NET_BIND_SERVICE | SSH startup, key ownership, multi-user privilege separation and port 22 |
| mail/postfix | CHOWN, DAC_OVERRIDE, FOWNER, FSETID, KILL, SETGID, SETUID, NET_BIND_SERVICE | Multi-user mail master and privileged listeners; SYS_CHROOT remains removed |
| mail/dovecot | Postfix set plus SYS_CHROOT | Mail/authentication users and login isolation |
| plex/plex | CHOWN, DAC_OVERRIDE, FOWNER, FSETID, KILL, SETGID, SETUID | LinuxServer startup and transition to media UID 1000; no low-port or chroot capability |
| nextcloud/collabora-collabora-online | CHOWN, FOWNER, SYS_CHROOT | File-capability document-jail helper, UID 1001 and required escalation |
| ripe-atlas/ripe-atlas | CHOWN, DAC_OVERRIDE, FOWNER, FSETID, KILL, SETUID, SETGID, SETPCAP, NET_RAW | Bootstrap, identity transitions, raw measurements and signal forwarding |

Postfix queue init separately requires only CHOWN and FOWNER. RIPE runtime init
already drops ALL with no additions and needs no capability exception. No other
init or ephemeral container is excused by these application rules.

Fresh sanitized Deployment inspection confirmed these exact sets and images.
Earlier requirement evidence remains in `docs/security-exception-follow-up.md`,
`plex/README.md`, `ripe-atlas/README.md` and the existing disposable probes.
Fresh runs in this batch passed:

- Backup SSH entrypoint, key authentication and rsync round trip on disposable data.
- Collabora UID/GID 1001 startup, WOPI discovery and document-jail child.
- Dovecot TLS, fixture authentication, read-only mailbox selection and reload.
- Postfix PROXY protocol, EHLO, STARTTLS, fixture AUTH, NOOP and reload; no mail submitted.
- Plex offline startup, identity endpoint, UID 1000 software transcode and persistent preferences after restart.

No workload guards changed in this audit-classification batch. RIPE's existing
setuid helper requirement was reviewed from the documented failure under
no-new-privileges and successful reduced-capability bootstrap; no new production
measurement or registration was triggered. Plex GPU allocation and UDP configuration
are unchanged; this batch did not repeat GPU or LAN functional tests.

Application capability sets are independently bounded in the generator by exact
namespace/Deployment/container role. Catalog entries must also link to the
existing reviewed root or escalation role and same image. Generated CEL requires
exact additions (including cardinality), drop ALL, non-privileged mode, effective
UID and an explicitly present escalation value. Existing identity checks cover
namespace, owner/name, labels and service account; images match exactly. Added
noncompliant sidecars/init/ephemeral containers prevent the exception matching.
Commands and volume contracts still rely on repository review, as before. Images
specified by mutable tags retain the existing trust limitation; changing tag
contents does not invalidate a string-equality match.

Kyverno CLI 1.19.2 passed 119 positive and negative capability cases covering all
six workloads and Postfix init: changed image/UID/escalation, missing escalation,
privileged mode, missing drop, extra/duplicate capabilities, moved container
section, changed namespace/owner/account/labels, and new noncompliant sidecars or
ephemeral containers. Reordering the same capability set remains accepted.
Full repository policy cases were extended for both main and init roles.
Repository unit tests passed: 287 run, 16 skipped. Runtime-contract validation,
generated-bundle consistency and whitespace checks passed. The full rendered
cluster-policy suite was not rerun locally; CI remains the publication gate.

Publication and Argo reconciliation remain pending. After publishing, verify six
capability findings become Skip and all other unexpected deviations remain Fail.
No GPU or Longhorn exception was widened, and no live exception was patched.

## Postfix confirmation-expiry role — 2026-11-16

The newly added `mail/postfix` sidecar is a distinct reviewed role, not another
Postfix master. It uses the existing Postfix image, UID 0 and only DAC_OVERRIDE,
SETUID and SETGID for queue inspection and the Postfix administrative utilities.
Its script restricts deletion to revalidated, deferred Mastodon confirmation
messages; no message body or recipient is logged. Those commands and mounts remain
subject to source review; this classification does not authorize new queue actions.

The earlier root/capability exceptions deliberately rejected the unreviewed
sidecar, causing the real CEL CI assertions to fail. The catalog now names only
`confirmation-expiry` in that exact Deployment and image repository, with the
exact capability set, drop ALL, non-privileged mode, UID 0, no escalation,
read-only root filesystem and inherited RuntimeDefault seccomp. No other helper
or ephemeral role is allowed. Missing/replaced role, image, changed UID,
privilege escalation or extra capabilities must still fail the exception.
Existing expiry and audit-only/fail-open policy settings are preserved.

The current source already requests 32Mi memory for the helper. No workload
permissions, image, queue script or live Kyverno policy was changed by this
review. Publishing the generated exception is a separate GitOps step.

CI's checksum-verified Kyverno CLI pin, audit harness and benchmark now target
1.20.0 at the owner's request. Its archive SHA256 was checked against upstream
release checksums. This is a CLI validation upgrade; the installed cluster
controllers and the separate 1.19.2 provider-cache implementation are unchanged.

Kyverno 1.20 applies autogen path rewrites to exception match conditions. Our
conditions already normalize Pod, Deployment/ReplicaSet/DaemonSet and CronJob
paths explicitly, so rewriting `object.spec` again addresses a nonexistent nested
template. Native Pod cases continued to pass while 113 controller expectations
failed in the initial CLI 1.20 run. See the
[upstream rewrite implementation](https://github.com/kyverno/kyverno/blob/v1.20.0/pkg/cel/autogen/replacement.go)
and [upstream issue](https://github.com/kyverno/kyverno/issues/16952).

The generator now binds the original object through
`[object].exists(workload, ...)` and applies all existing identity, image, guard
and ownership predicates to that alias. This retains the original object rather
than allowing autogen to rewrite already normalized paths; no predicate is removed.
CEL string literals remain unchanged during rebinding, including literal values
containing `object` or `object.spec`. Real CLI tests cover both controllers and
Pods, original positive cases and all identity/security mutations.

Validation after rebinding: all 844 repository unit tests pass on Python 3.15
with 16 expected skips; all 28 focused Kyverno unit tests pass. The pinned CLI
1.20.0 completes the full prepared snapshot/identity/negative/audit suite with
**0 out of 2237 tests failed**, including the actual rendered Postfix Deployment
and 61 focused Postfix assertions. The input set uses reviewed snapshots for other
workloads, not a fresh full-cluster render. Generated-file consistency, full
Pylint on the changed Python modules, Ruff, runtime contracts, resource checking
with namespace defaults and whitespace checks pass. New GitHub Actions execution
and live exception reconciliation remain pending source publication.
