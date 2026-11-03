# CrowdSec capability restrictions

Prepared 2026-11-03 for chart 0.24.2 / CrowdSec v1.8.1. Agent, LAPI and
`wait-for-lapi-and-register` now drop ALL Linux capabilities. This supersedes the
initial conservative six-capability allowlist, after an isolated startup test
proved all three roles work without it for this configuration.

Root execution remains an explicit application exception. Staged image
credentials have root ownership and mode 0600, and the chart startup command
creates a configuration symlink under `/etc`. A UID/GID 1000 probe failed on
staged credential reads. Clearing the root finding needs a rootless image and
entrypoint/volume design; merely adding runAsNonRoot would break startup.

Existing no-escalation, non-privileged and RuntimeDefault controls remain.
Registration, acquisition, selective Traefik enforcement, service accounts,
credentials and production PVCs are unchanged. All inspected production
configuration/data files were root-owned; no ownership migration was performed.
Changing GID/ownership behavior or upgrading the image requires revalidating the
zero-capability startup assumption.

An isolated temporary instance with emptyDir storage and generated ephemeral
credentials passed LAPI startup, agent registration and authentication, and both
metrics endpoints. Effective/bounding capabilities were zero and NoNewPrivs=1.
It had no production credentials, PVCs, service-account token or Service labels.
It did not test production Kubernetes log acquisition or bouncer decisions.
The temporary workloads were removed.

After publication, verify both `crowdsec` and `crowdsec-config` Argo Applications,
init completion, readiness, actual capability sets, continuous Traefik log
acquisition and bouncer connectivity against existing PVC contents. The root
Kyverno finding intentionally remains visible. See the
[full compatibility audit](../docs/security-exception-follow-up.md) for exact
validation, limits and other application exceptions.
