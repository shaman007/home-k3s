## Kubernetes Snapshot Controller

Vendored from `kubernetes-csi/external-snapshotter` release `v8.5.0`.

This directory installs the cluster-wide CSI snapshot CRDs and common snapshot controller.
Longhorn already provides the per-driver `csi-snapshotter` sidecar, so these manifests fill in
the missing cluster components required for `VolumeSnapshot` support.
