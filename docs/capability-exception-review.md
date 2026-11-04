# Reviewed application capability exceptions — 2026-11-04

This batch changes audit classification, not workload privileges or runtime guards.
All five policies stay Audit/Ignore; the seccomp policy has no exceptions. These
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
