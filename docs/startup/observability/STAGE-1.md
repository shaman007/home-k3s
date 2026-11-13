# Stage 1: internal S3 network permissions only

Stage-one policies were published as `02452391` and verified Synced/Healthy in
all three owning Argo Applications. Signed access and the separately authorized
client cutover are recorded in [EXECUTION.md](EXECUTION.md). This first-stage
commit itself changed no endpoint, credential, bucket, retention or Pod template.

## Review scope

| File | Argo owner | Permission |
| --- | --- | --- |
| `metrics/network-policy-monitoring-allow-egress-thanos-s3-internal.yaml` | monitoring-network-policy | Selected Prometheus/sidecar, Thanos store and compactor Pods → SeaweedFS S3 TCP8333 |
| `loki/network-policy-loki-allow-egress-s3-internal.yaml` | loki-network-policy | Loki single-binary instance only → SeaweedFS S3 TCP8333 |
| `seaweedfs/network-policy-seaweedfs-allow-ingress-observability-s3.yaml` | seaweedfs | Matching namespace+Pod peers above → S3 TCP8333 |
| `argocd/application-monitoring-network-policy.yaml` | existing Application | Add only the new monitoring policy filename to its explicit source include list |

All namespace and Pod selectors are in the same peer expression (AND). Loki is
restricted by component, name and instance labels. Monitoring selection includes
`prometheus-server` because its Thanos sidecar shares the Pod network; Kubernetes
NetworkPolicy cannot grant this permission to just one container. Querier,
Grafana, gateways and cache Pods receive no new direct S3 permission.
Existing public-route policies remain, so the current clients continue to work.
Selectors and the `seaweedfs/s3` Service port were checked against live resources.
This is not proof of connectivity before policies have actually reconciled.

Reproduce an exclusive inactive review tree:

```sh
python3 tools/bootstrap/prepare_dependency_batch.py --package observability \
  --network-only --output /tmp/observability-network-UNIQUE
```

Unlike the full observability proposal, this mode emits exactly three policies
and their Argo allowlist change. Tests reject unrelated packages in network-only
mode and ensure it cannot export Loki/Thanos client configurations or workloads.

## Publication and acceptance

1. Publish only after the user requests a commit/push. Ordinary Argo reconciliation
   will create additive policies; no workload restart is needed. Observe the root
   Application update as well as all three policy-owning Applications.
2. Verify each policy is present, tracked by its intended Argo Application and
   matches current Pods. Do not count an unselected file as deployment success.
3. After separate authorization, perform bounded DNS/TCP/HTTP checks from the
   actual selected Loki and Thanos/sidecar Pods. Any HTTP response alone does not
   prove credentials, signed bucket access or object reading work. No test Job,
   temporary container or credential export is authorized by this document.
4. Before switching a client endpoint, verify signed read/list against its own
   existing bucket/credentials, without logging secret values or changing objects.
   Recheck current ingress routes and all existing collection/ingestion paths.
5. End this stage with existing Loki/Thanos endpoints still in use. Switch Loki
   and then Thanos clients only under separately reviewed later stages.

Creating these additive unused permissions does not justify silencing unrelated
alerts. If later authorized maintenance affects an active component, use only
its narrowly scoped expiring silence per AGENTS.md and remove after verification.

## Rollback

Before any client switches to internal S3, restore the prior Argo include list
and remove only the three new policies through the usual authorized GitOps flow.
Some Applications lack automatic prune: verify ownership and deletion behavior
rather than assuming file removal deletes a live policy. Never remove a policy
already used by a switched client until that client has returned to its old
endpoint and that path has been verified. Keep all data, Secrets, PVCs and public
route permissions intact. This first stage changes no data or credentials.
