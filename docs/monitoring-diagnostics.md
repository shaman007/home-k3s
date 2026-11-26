# Quiet read-only monitoring diagnostics

Use `python3 tools/ops/monitoring_api.py alertmanager` to inspect all running
Alertmanager replicas through Kubernetes HTTP pod proxy. Direct Sidekick alerts
are local to a replica, so querying only the load-balanced Service is incomplete.
The helper only invokes `kubectl get --raw`; it never uses exec, port-forward,
Secret reads or cluster writes. Summary output omits raw process arguments.

Run Grafana queries through the separate OpenBao consumer:

```
bao-desktop exec grafana -- python3 tools/ops/monitoring_api.py grafana /api/health
bao-desktop exec grafana -- python3 tools/ops/monitoring_api.py grafana /api/user
```

The `codex-diagnostics` Grafana service account must have Viewer role. Store its
token only at OpenBao `kv/desktop/grafana`, field `token`. The desktop ACL grants
only read of that exact path. Host profile/wrapper/restore instructions are in
`/home/shaman007/git/dotfiles/openbao-desktop/README.md`. Tokens are passed only
to the consumer environment, excluded from nested consumers, never put in argv,
files, shell startup or logs. The client refuses redirects and external URLs.
No normal diagnostic requires the administrative OpenBao session or the shared
monitoring KV. Rotate the bounded token before expiry and test Viewer access.

Talos API proxy traffic retains node identities in this cluster. The dedicated
Cilium policy selects only `app=alertmanager` and TCP 9093, permitting
kube-apiserver/host/remote-node identities. All three current nodes are control
planes. This allows node processes to connect to that port, not only the API
server process. Review this source scope before adding workers. Arbitrary Pod
identities and external addresses are not newly allowed; existing in-namespace
Alertmanager traffic remains managed by its existing policies.

Do not whitelist `admin` or disable audit/Falco rules. Existing audit alerts
expire after fifteen minutes without matching events. Verify both Loki detections
and Alertmanager state after switching workflows; do not mistake a live timestamp
window for fresh accesses. A broad admin exception would hide suspicious actions.
