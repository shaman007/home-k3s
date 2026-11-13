# Thanos object-store configuration

All clients now use the internal SeaweedFS S3 Service. Store Gateway and Compactor
have independent ESO-derived config targets; sidecar retains the original target
name. All are transformed from the same unchanged OpenBao property using the
canonical guarded template in `tools/bootstrap/prepare_dependency_batch.py`.
Never hand-edit credential values in Git or patch the generated Secret data.

See [the staged transition and rollback record](../docs/startup/observability/EXECUTION.md).
Prometheus has no S3 init gate and its container was not restarted by the cutover.
