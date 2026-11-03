# Application security exception follow-up

Prepared 2026-11-03. This wave hardens Collabora, Plex, RIPE Atlas, Mastodon's
bookmarked-media job and CrowdSec. It preserves the previously agreed boundary:
retain necessary root/helper exceptions rather than break application behavior
or disable isolation to clear audit results. No Kyverno PolicyExceptions,
namespace exemptions, policy suppression or enforcement-mode changes are added.

## Changes and expected policy outcomes

| Workload | Prepared change | Finding expected after publication |
| --- | --- | --- |
| Plex | Set allowPrivilegeEscalation=false | Escalation finding should clear; root s6 startup remains |
| Mastodon bookmarked-media-sync | Set allowPrivilegeEscalation=false on fetch init and upload container | Escalation finding should clear; runtime package installation still uses root |
| CrowdSec agent, registration init and LAPI | Drop ALL capabilities, removing the previous six-capability allowlist | Existing escalation/privileged checks stay compliant; root finding remains |
| Collabora | Drop ALL, retaining only CHOWN, FOWNER and SYS_CHROOT; explicitly document required escalation | Escalation finding remains because the document sandbox uses file capabilities |
| RIPE Atlas | Drop ALL, retaining nine capabilities for bootstrap, signal handling, identity transitions and raw measurements | Escalation/root findings remain because the upstream helper requires a setuid transition |

These are findings on whole workload templates, including init containers. A
non-root application process alone does not make a root-bootstrap template pass.
Historical ReplicaSets and completed Jobs can retain earlier results after the
current template is fixed.

## Compatibility evidence

### Plex

A temporary instance of the exact current image started with no-new-privileges,
reached readiness and served `/identity`. Its custom init hook completed. The
fixture used fresh emptyDir configuration/media, no claim token and no GPU;
it did not read the production library or preferences. Production root s6
startup, PUID/PGID, GPU resources, advertisement URLs, volumes and custom init
hook are retained. Existing-library startup, clients and GPU transcoding remain
post-publication checks. LinuxServer documents no-new-privileges as compatible
with root startup, with extra `/run` ownership requirements for non-root startup:
[upstream guidance](https://docs.linuxserver.io/misc/non-root/).

### Mastodon bookmarked-media job

An isolated Pod completed the actual tool-installation steps with escalation
disabled: Alpine packages and kubectl in the fetch init container, plus pinned
Immich CLI 3.0.2 and upload/post-processing packages in the Node container. No
application credentials, Kubernetes service-account token or user media were
mounted. No Mastodon fetch, Immich upload, description mutation or face-detection
request was executed. The next normal scheduled job must verify the complete
workflow after publication. Removing root here requires prebuilt tooling images;
this wave does not change the existing runtime-installation model.

### CrowdSec

LAPI, registration and agent startup passed with zero capabilities, using the
pinned chart's scripts and image. Registration completed, agent authentication
to LAPI succeeded and both metrics endpoints responded. Runtime effective and
bounding sets were zero, with NoNewPrivs=1. Current production config/data trees
contained no files owned by users other than root, supporting this narrower
capability set for the existing volume contents. Future GID/ownership or image
changes need revalidation; this is not a general promise that chown works without
CAP_CHOWN. See [CrowdSec details](../crowdsec/README.md).

A separate UID/GID 1000 probe failed reading the image's root-owned mode-0600
staged credentials before normal startup. The current chart also creates its
configuration link under root-owned `/etc`. Setting runAsNonRoot alone would
break this image/entrypoint. Clearing this finding needs a rootless image and
startup/volume design, not a false compliance flag. Production acquisition and
bouncer behavior were not exercised by the isolated test.

### Collabora

The exact installed image was tested in isolation. Disabling escalation caused
`coolforkit-caps` to report missing CHOWN/FOWNER/SYS_CHROOT and terminate. Supplying
those capabilities explicitly while keeping no-new-privileges still failed to
supply the helper's required capabilities. Restoring required escalation with
only those three capabilities allowed conversion of synthetic text into a valid
PDF (HTTP 200). No user document, production WOPI access or admin credential was
used. The fixture used its default self-signed TLS listener; the loopback test
client accepted that test certificate. Production TLS settings are unchanged.

The sandbox remains enabled; neither `security.capabilities=false` nor disabling
seccomp is used. The [official source mirror's configuration](https://github.com/CollaboraOnline/online.mirror/blob/main/coolwsd.xml.in)
warns that changing isolation defaults can remove document isolation. The
current runtime failure, rather than assumptions about a newer implementation,
is the reason escalation stays an explicit exception. Real Nextcloud WOPI
editing remains a rollout check.

### RIPE Atlas

A read-only helper invocation under no-new-privileges failed with
`evping: setresuid: Operation not permitted`. Without that flag, the helper
successfully transitioned identities and reached Atlas's deliberate rejection of
the loopback target. No public measurement or probe registration was performed.
This demonstrates why the flag cannot simply be enabled on the installed setuid
measurement helper. This behavior follows the kernel's
[no-new-privileges semantics](https://docs.kernel.org/userspace-api/no_new_privs.html).

An isolated emptyDir bootstrap passed with a nine-capability bounding set:
CHOWN, DAC_OVERRIDE, FOWNER, FSETID, KILL, SETUID, SETGID, SETPCAP and NET_RAW.
Its real bootstrap ran, but a mounted test shim replaced the control daemon to
prevent a new probe registration. It reached UID 998 with NET_RAW effective and
ambient, and the measurement-helper identity check passed. NET_BIND_SERVICE,
SYS_CHROOT, MKNOD, AUDIT_WRITE and SETFCAP are removed. KILL remains for Tini's
cross-UID signal forwarding. Existing probe identity, spool data, host networking
and the separate measurement user remain unchanged. Actual scheduling, IPv4/IPv6
measurements and transfer progress still require production rollout verification.

## Validation and cleanup

All five affected Argo Applications rendered. Resource checks passed for their
17 containers using namespace defaults; all six proposed controller patches
passed API-server dry runs. Repository tests passed: 256 run, 16 skipped. Diff
whitespace checks passed. Remaining Restricted warnings are expected for the
explicit root/capability/escalation exceptions.

All temporary probe Pods, the RIPE test-shim ConfigMap and the loopback port
forward were removed. Tests used ephemeral data, with no production controller
patches or restarts. Publication is still required. Monitor replacement pods,
application functions and current-controller policy reports after reconciliation;
do not claim the three retained exception categories are cleared.
