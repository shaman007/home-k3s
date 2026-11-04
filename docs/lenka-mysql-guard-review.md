# Lenka MySQL guard review

The existing `lenka/mysql` Deployment is unmanaged: the Lenka Argo Application
contains RBAC only. Do not put a partial Deployment into that auto-pruned directory.
`tools/security/lenka-mysql-security.patch.yaml` is a strategic merge patch prepared
for an explicitly authorized live patch, not an automatically deployed manifest.
It preserves the current image, environment, PVC and rollout strategy.

Runtime inspection found MySQL 9.7.2, PID 1 UID/GID 999, zero effective
capabilities, existing seccomp filter mode 2, and no no-new-privileges guard.
Every existing data-directory entry is UID 999; the directory root is 999:0 mode
0755. Runtime directories are already writable for UID 999. The official entrypoint
skips its root-only chown/gosu path when started as UID 999. No fsGroup, recursive
ownership change, root init container or credential change is needed.

The disposable probe uses the exact deployed image digest, network=none and a new
volume with matching root ownership. It checks new-database initialization, SQL
write/read, graceful restart and persistent data, plus UID/GID 999, zero capability
bounding/effective/permitted sets, NoNewPrivs=1 and seccomp mode 2. Podman's default
seccomp profile is compatibility evidence; Kubernetes RuntimeDefault still needs
verification after rollout on Talos. Production data is never mounted by this probe.
The root filesystem remains writable; this batch only introduces the requested guards.

Run the probe with `python3 tools/security/test-lenka-mysql-guards.py`.
A live rollout and cleared PolicyReports remain pending explicit cluster-change
approval. A Git push alone will not deploy this patch.

# Running Pods without a matching PolicyReport

Fresh snapshot: 31 Pods, all in deliberately excluded namespaces.
All five live ValidatingPolicies exclude `kube-system` and `kyverno` through their
namespace match conditions. These Pods are outside this audit's coverage, not
implicitly passing. The static control-plane Pods are included in this list.
No namespace exclusions were changed.

| Namespace | Pod |
| --- | --- |
| `kube-system` | `cilium-57cj9` |
| `kube-system` | `cilium-envoy-j6ckj` |
| `kube-system` | `cilium-envoy-s4s2q` |
| `kube-system` | `cilium-envoy-zcw5f` |
| `kube-system` | `cilium-fbsl8` |
| `kube-system` | `cilium-operator-8545f85bbb-7ldtz` |
| `kube-system` | `cilium-tqcd4` |
| `kube-system` | `coredns-f98564579-d27hb` |
| `kube-system` | `coredns-f98564579-fvbrm` |
| `kube-system` | `coredns-f98564579-l7lq7` |
| `kube-system` | `hubble-relay-8687757766-x95pk` |
| `kube-system` | `hubble-ui-647df7f64c-77kwc` |
| `kube-system` | `kube-apiserver-talos-d4h-k5m` |
| `kube-system` | `kube-apiserver-talos-qlw-pbh` |
| `kube-system` | `kube-apiserver-w386` |
| `kube-system` | `kube-controller-manager-talos-d4h-k5m` |
| `kube-system` | `kube-controller-manager-talos-qlw-pbh` |
| `kube-system` | `kube-controller-manager-w386` |
| `kube-system` | `kube-scheduler-talos-d4h-k5m` |
| `kube-system` | `kube-scheduler-talos-qlw-pbh` |
| `kube-system` | `kube-scheduler-w386` |
| `kube-system` | `kube-state-metrics-6f56876d8-b5247` |
| `kube-system` | `metrics-server-5c569d4d56-bhbx8` |
| `kube-system` | `snapshot-controller-54f79b9984-hcflv` |
| `kube-system` | `snapshot-controller-54f79b9984-ngd9j` |
| `kube-system` | `snapshot-controller-54f79b9984-pdcgx` |
| `kyverno` | `kyverno-admission-controller-67b656b54-2nfz9` |
| `kyverno` | `kyverno-admission-controller-67b656b54-5tgcs` |
| `kyverno` | `kyverno-admission-controller-67b656b54-6pjbn` |
| `kyverno` | `kyverno-reports-controller-74b5c566fd-btsg5` |
| `kyverno` | `kyverno-reports-controller-74b5c566fd-jfv29` |
