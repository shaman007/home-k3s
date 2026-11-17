# Kyverno warning review — 2026-11-17

The live event snapshot contained exactly 42 Warning objects, all emitted by
kyverno-admission. These are repeated notifications, not 42 independent security
issues: the same violation is recorded against a ValidatingPolicy and against its
resource, and repeated admission evaluations create further events.

Seven resource/policy pairs explain this snapshot:

| Resource | Findings |
| --- | --- |
| metallb-system/metallb-frr-k8s DaemonSet | escalation, capabilities, root, seccomp |
| metallb-system/metallb-frr-k8s-statuscleaner Deployment | root, seccomp |
| mail/rspamd-spam-trainer Job/Pod | capabilities |

The complete report inventory also includes historical zero-replica ReplicaSets,
completed Jobs, unscheduled GPU DaemonSets and image-builder. Those are a separate
inventory; clearing these seven pairs does not establish cluster-wide compliance.
Do not delete retained resources or suppress all Kyverno events to clear a count.

## FRR restored for active BGP

FRR was retired when MetalLB used only L2, and later restored for BGP. The current
chart 0.16.2 creates frr-k8s v0.0.27 / FRR 10.6.2 without the earlier reviewed
helper guards. BGP is active; the old retirement instructions do not apply.

Restore the exact-contract native infrastructure mutation and sequential backfill
for the DaemonSet and statuscleaner. Commands, arguments, mounts, volumes, service
account, inventory, images and rollout strategy are pinned to the inspected live
workloads. A changed contract must remain unmodified and visible in the audit.
The chart has no security-context options for most of these helper roles.

- statuscleaner: UID/GID 1000, no escalation, drop ALL, RuntimeDefault.
- cp-frr-files: UID 100 / GID 101, drop ALL, no escalation, RuntimeDefault.
- other copy init roles: UID/GID 1000, drop ALL, no escalation, RuntimeDefault.
  The root-owned destination emptyDirs are mode 0777; the actual copy commands
  passed as UID1000 without capabilities, so these roles need no root exception.
- metrics/status: UID 100 / GID 102, drop ALL, no escalation, RuntimeDefault.
- reloader: UID 0 / GID 102, drop ALL plus DAC_OVERRIDE, no escalation,
  RuntimeDefault. It reads owner-100 mode-0600 configuration and shares the
  root controller's signal identity.
- controller: retain NET_RAW and drop ALL; make its root identity and
  RuntimeDefault explicit. Other existing guards remain unchanged.
- routing daemon: retain the upstream capability declaration (NET_ADMIN,
  NET_RAW, SYS_ADMIN, NET_BIND_SERVICE), default runtime capabilities and
  read-only root filesystem; add explicit UID/GID 0 and RuntimeDefault.
  This is a retained routing requirement, not a claim of least privilege.
  Its exception pins this exact declaration and companion guards. Adding drop ALL
  to this role without a complete FRR startup/routing review is not justified.

Only root and capabilities receive new FRR exceptions. Escalation and seccomp
must actually pass. The routing capability exception is restricted in the
exception generator to this exact namespace/DaemonSet/container/repository and
reviewed guard contract; it cannot be reused for another role. Root/capability
exceptions require all reviewed companions to retain their guards. Ephemeral and
unexpected containers receive no exemption. Existing exception expiry is retained.

`tools/security/test_frr_helper_guards.py` passed against the current images:
real VTY queries, DAC_OVERRIDE-only reload and syntax checks, SIGHUP/lock/status,
UID-100 authenticated metrics and status caches. It uses disposable configuration,
no kernel routes, no BGP listener and a mock Kubernetes API. statuscleaner also
executes `--help` as UID1000 with no capabilities and read-only root. This does
not prove its real cluster startup, webhook certificate access or BGP recovery.
Prior helper contracts and filesystem rationale are in
[GPU/FRR helper hardening](gpu-frr-helper-hardening.md).

## Spam trainer

The private Dovecot master/auth service requires root to switch to its mail/auth
users and isolate auth processes. The trainer previously inherited the runtime's
broad default capabilities. Drop ALL and retain only CHOWN, DAC_OVERRIDE, KILL,
SETGID, SETUID and SYS_CHROOT, with UID/GID 0, no escalation, non-privileged mode,
read-only root and inherited RuntimeDefault. The capability exception pins the
exact six-capability set and this workload identity. The existing root exception
now also requires those guards.

`tools/security/test_spam_trainer_guards.py` passed with the actual Dovecot image,
configuration and training script, using a disposable synthetic mbox. It verifies
successful learning followed by expunge, and failed learning retaining the message.
Only curl's remote response is stubbed; real Dovecot master/auth/doveadm and mbox
access execute with the proposed capabilities. Network is disabled. No production
mail or Rspamd state is touched; actual Rspamd delivery remains a rollout check.

## Publication and verification

These changes are local preparation. Publishing/reconciling infra-guards will
replace the FRR Pods sequentially (maxUnavailable=1) and the statuscleaner Pod.
Obtain authorization for that BGP maintenance before publication/reconciliation.
Use narrowly scoped maintenance silences as required by AGENTS.md. Capture BGP
peers/routes, FRRConfiguration state and representative LoadBalancer connectivity
before and after; generic Pod readiness alone does not establish BGP recovery.
The hook's existing readiness/storage/GPU gates do not check BGP sessions.

After publication, confirm infra-guards/kyverno-exceptions/mail are Healthy/Synced,
the exact guards are present, and BGP sessions, announcements, IPv4/IPv6 ingress
and backup SSH work. Check the next naturally scheduled trainer result without
submitting or deleting real mail as a test. Confirm the fresh policy results are
Pass for corrected guards and Skip only for reviewed requirements. Existing
Warning events and historical reports may remain until expiry/background refresh;
absence of fresh violations is the relevant event check. Do not enable Deny.

## Local validation result

The full rendered CEL run passed 2348 expectations. A final focused run passed
134 expectations for the finished FRR/trainer contracts, including actual
admitted controller output and Pass expectations for corrected escalation,
seccomp and statuscleaner guards. Native mutation/scope/idempotence passed 103
cases. Relevant unit, optimized-guard rejection, runtime-contract and generated
bundle checks passed. Strict Kubernetes schema validation accepted 14 standard
resources; 137 custom resources/AppProject were skipped for missing schemas,
with CEL semantics checked by the pinned CLI. The broad Python suite was also
attempted: it needs unavailable AIY Python dependencies and socket access in
this sandbox. Its two task-related failures were fixed and their suites rerun
successfully; no claim that the entire repository suite passed is made.
