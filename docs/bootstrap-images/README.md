# Bootstrap images independent of a running Harbor

`images.lock.json` is the reviewed 2026-11-14 linux/amd64 snapshot: required
image references + observed digests, CRI/system namespaces and three target
node addresses. Includes API/controller/scheduler, kubelet/etcd/pause, Cilium,
CoreDNS, Longhorn engine/CSI/share-manager, MetalLB/FRR, OpenBao/ESO,
cert-manager + GoDaddy webhook, SeaweedFS core, Harbor and registry ingress,
and ArgoCD. Optional monitoring jobs/media-cache are not S3 bootstrap providers.

No Secret values are collected. Source versions and lock must be reviewed and
updated together when infrastructure images change. The lock is an observed
operational inventory, not a promise that mutable tags never change upstream.

```sh
# Read-only: require original references and expected digest on every node.
python3 tools/bootstrap/bootstrap_images.py check
# Explicitly mutating: pull missing references, no deletions/restart/config patch.
python3 tools/bootstrap/bootstrap_images.py preload
# Independent copy OUTSIDE the cluster and repository; requires skopeo/talosctl.
python3 tools/bootstrap/bootstrap_images.py bundle \
  --output /path/to/new-bootstrap-image-bundle
python3 tools/bootstrap/bootstrap_images.py verify-bundle \
  --output /path/to/new-bootstrap-image-bundle
```

Native Talos output normalizes `busybox` and `tag@digest`; checks normalize names
without accepting different content. Unexpected existing digest drift is reported
and never overwritten by the tool. Pulls use current declared references and
verify the resulting digest, not just successful CLI exit. Registry metadata
must match the lock before bundle creation. Review any mismatch rather than
updating the lock blindly. `check` proves metadata presence, not intact layers;
recovery-bundle checksums detect subsequent file corruption. Acceptance also verifies
the locked manifest, original tag alias and complete linux/amd64 config/layer
closure against content digests, not merely filenames or CLI success.

The flat image bundle is readable using native `talosctl image cache-serve`.
Store it on independent storage and copy it to separate removable/offsite media.
It must not live only in SeaweedFS/Longhorn/Harbor. A workstation copy protects
against cluster loss, not simultaneous workstation disk loss. Preserve original
registry names, tag mappings and digests; verify before serving. Emergency mirror
endpoints, TLS, firewall and node RegistryMirrorConfig require separate scoped
execution review, not an automatic insecure/LAN-wide listener from this script.

**Ordinary containerd cache can be garbage-collected.** `preload` improves next
restart but is not a permanent pin, nor a new empty-node boot proof. The independent
bundle is the recovery source if cache entries disappear. ArgoCD source now uses
IfNotPresent so preloaded images can be used without a registry lookup; Harbor's
BusyBox init is pinned to the same digest as SeaweedFS's bootstrap BusyBox.
These source changes still need publication/reconciliation before claiming active.

Do not enable `ImageCacheConfig.local.enabled` on current machines without
prepared cache media/partition: Talos can block boot waiting for it. Native
persistent cache requires prepared boot/secondary media and suitable IMAGECACHE
storage. No disk repartitioning, machine upgrade or permanent mirror was made.
See [Talos image cache documentation](https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/images-container-runtime/image-cache).

Recovery artifacts are container images, not secret data or installed host
configuration. CLI prerequisites: talosctl, skopeo, Python/PyYAML and requests.
No new daemon/package/service is installed on the workstation.

## Executed acceptance — 2026-11-14

All **52** locked images passed the native Talos reference/digest check on
`192.168.30.100`, `.209`, `.242` after preloading missing images. No node config,
image deletion, reboot or application rollout was performed by preload.

The independent flat-cache bundle is stored on the workstation at:
`/home/shaman007/.local/share/home-k3s/bootstrap-images/2026-11-14` (about 3.3GiB).
The initially attempted all-images export failed; the successful retry uses
bounded native per-image exports, a reusable layer cache and conflict-checked
merge of native files. No image is rebuilt/repacked and no digest is rewritten.
The acceptance command verifies SHA256SUMS, locked manifest identity, tag aliases
and all required linux/amd64 layer/config content. Git lock and embedded lock
match. External registry signatures are retained when the native exporter finds
them; admission and verification policies are unchanged.

Layer-download scratch resides in the adjacent `layers` directory; it is not
required when copying the completed bundle. The bundle has no running service
and no user authentication or runtime Secret payload. Copy the complete bundle,
including `SHA256SUMS.json` and `bootstrap-images.lock.json`, for independent
recovery. Native persistent Talos cache activation and a fresh empty-node boot
were deliberately not performed.

Loopback-only native cache-serve acceptance returned HTTP200 for the pinned
GoDaddy webhook manifest and a real layer; both response digests matched the
bundle. No Harbor credentials were needed and no node mirror was changed.
The test server was stopped. CLI's automatically generated loopback mirror
example was moved out of Git to workstation scratch; it was never applied.
This does not claim Harbor was shut down or that a fresh node was booted offline.
