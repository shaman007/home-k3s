# CrowdSec startup capability restrictions

Prepared 2026-11-03 for chart 0.24.2 / CrowdSec v1.8.1. The agent, LAPI and
`wait-for-lapi-and-register` init container now drop ALL capabilities and add
back a conservative startup allowlist:

- CHOWN, DAC_OVERRIDE, FOWNER and FSETID for filesystem ownership/mode operations.
- SETUID and SETGID to preserve the current root image's user-management envelope.

This reduces the observed default set from 14 to six, removing NET_RAW,
NET_BIND_SERVICE, SYS_CHROOT, MKNOD, AUDIT_WRITE, SETFCAP, KILL and SETPCAP.
These containers have no inspected startup dependency on raw sockets, low ports,
chroot, device creation, file capabilities or changing capability sets. LAPI
listens on 8080 and metrics on 6060. The image scripts stage configuration, run
rsync/copy/install operations and optionally change database group ownership.
The retained six are a conservative compatibility boundary, not a claim that
all six are individually essential or the minimum possible set.

Root execution remains an explicit application exception. Existing
`allowPrivilegeEscalation: false`, `privileged: false` and RuntimeDefault seccomp
are preserved. Registration, acquisition, Traefik enforcement scope, secrets,
service accounts, storage and network policies are unchanged.

## Verification

- Pinned chart render confirmed the allowlist on all three intended containers.
- Rendered resource checks passed for five containers, using namespace defaults.
- Both production Deployment patches passed API-server dry runs. Remaining
  Restricted warnings for root execution/added capabilities are expected; this
  is not full Restricted compliance or clearance of non-root Kyverno findings.
- Repository suite passed: 256 tests run, 16 skipped. Diff whitespace check passed.
- An isolated temporary Pod ran LAPI, registration and agent startup with these
  security contexts. Registration completed successfully, agent authentication
  to LAPI succeeded, and both metrics endpoints responded. Runtime effective and
  bounding sets were `0xDB` (the six listed capabilities), with NoNewPrivs=1 and
  Seccomp=2.

The isolated fixture used emptyDir storage and generated its own ephemeral
credentials. It mounted no production PVCs, Secrets or service-account token,
and carried no production Service selector labels. LAPI and agent shared
loopback networking with separate metrics ports; test auto-registration allowed
loopback only. The fixture's initial key-strength failure was corrected before
the successful test. It exercised the image/registration lifecycle and metrics,
not production Kubernetes log acquisition, real bouncer decisions, or existing
PVC upgrades. The test Pod and its ephemeral storage were removed.

## Publication and rollout

Changes are prepared in Git, not patched into production. After publication,
check both Argo Applications (`crowdsec` and `crowdsec-config`) and both
Deployment rollouts. Verify registration/init completion, readiness, actual
capability sets, continuous Traefik log acquisition and LAPI/bouncer connectivity.
Existing configuration/database PVCs must be retained. A successful fresh
isolated startup does not prove restart against the production PVC contents or
end-to-end remediation behavior; those remain rollout checks.
