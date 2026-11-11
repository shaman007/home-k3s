## To revive index, do

```
curl -X PUT 'http://meilisearch.karakeep.svc.cluster.local:7700/indexes/bookmarks/settings/filterable-attributes' \
  -H 'Authorization: Bearer SSECRET' \
  -H 'Content-Type: application/json' \
--data-binary '["userId","tags","createdAt"]'

curl -X PUT 'http://meilisearch.karakeep.svc.cluster.local:7700/indexes/bookmarks/settings/sortable-attributes' \
  -H 'Authorization: Bearer SECRET' \
  -H 'Content-Type: application/json' \
--data-binary '["tags","createdAt"]'
```

## Meilisearch database upgrades

`stateful-set-meilisearch.yaml` keeps:

* `MEILI_DB_PATH=/meili_data/data-v1.37.0-r1.ms`
* `MEILI_UPGRADE_DB=true`

The upgrade flag remains enabled so Meilisearch automatically migrates the on-disk search index after future image upgrades. The index is disposable and can be rebuilt by Karakeep if a migration fails.

### Rollout

Sync ArgoCD and verify the StatefulSet restarts cleanly:

```bash
kubectl -n karakeep get sts meilisearch
kubectl -n karakeep rollout status statefulset/meilisearch
kubectl -n karakeep get pods -l app=meilisearch -o wide
kubectl -n karakeep logs statefulset/meilisearch --tail=200
```

### Verify the upgrade task

```bash
# terminal 1
kubectl -n karakeep port-forward svc/meilisearch 7700:7700
```

```bash
# terminal 2
set -euo pipefail
master_key=$(kubectl -n karakeep get secret karakeep-secret-env \
  -o jsonpath='{.data.MEILI_MASTER_KEY}' | base64 --decode)
meili_request() {
  printf 'Authorization: Bearer %s\n' "$master_key" |
    curl --fail --silent --show-error --max-time 30 --header @- \
      --request "$1" "http://127.0.0.1:7700/$2"
}

meili_request GET 'tasks?types=UpgradeDatabase' | jq .
unset master_key
```

Wait for the `UpgradeDatabase` task to finish with `succeeded`.

### Smoke test

```bash
# terminal 1
kubectl -n karakeep port-forward svc/meilisearch 7700:7700
```

```bash
# terminal 2
set -euo pipefail
master_key=$(kubectl -n karakeep get secret karakeep-secret-env \
  -o jsonpath='{.data.MEILI_MASTER_KEY}' | base64 --decode)
meili_request() {
  printf 'Authorization: Bearer %s\n' "$master_key" |
    curl --fail --silent --show-error --max-time 30 --header @- \
      --request "$1" "http://127.0.0.1:7700/$2"
}

meili_request GET health | jq .
meili_request GET indexes/bookmarks/stats | jq .
unset master_key
```

## Historical migration: 1.36.0 (Deployment) -> 1.37.0 (StatefulSet)

### Phase 1: Restore availability

`deployment-meilisearch.yaml` is pinned to `v1.36.0` and keeps:

* `MEILI_DB_PATH=/meili_data/data-v1.36.0-r2.ms`

Sync ArgoCD and verify:

```bash
kubectl -n karakeep get deploy meilisearch
kubectl -n karakeep get pods -l app=meilisearch
kubectl -n karakeep logs deploy/meilisearch --tail=50
```

### Phase 2: Export dump from 1.36.0

```bash
# terminal 1
kubectl -n karakeep port-forward svc/meilisearch 7700:7700
```

```bash
# terminal 2
set -euo pipefail
master_key=$(kubectl -n karakeep get secret karakeep-secret-env \
  -o jsonpath='{.data.MEILI_MASTER_KEY}' | base64 --decode)
meili_request() {
  printf 'Authorization: Bearer %s\n' "$master_key" |
    curl --fail --silent --show-error --max-time 30 --header @- \
      --request "$1" "http://127.0.0.1:7700/$2"
}

dump_task=$(meili_request POST dumps)
task_uid=$(printf '%s' "$dump_task" | jq -r '.taskUid')
while :; do
  task=$(meili_request GET "tasks/$task_uid")
  status=$(printf '%s' "$task" | jq -r '.status')
  printf '%s\n' "$status"
  case "$status" in
    enqueued|processing) sleep 2 ;;
    succeeded) break ;;
    *) printf 'Dump task failed\n' >&2; exit 1 ;;
  esac
done
dump_uid=$(printf '%s' "$task" | jq -r '.details.dumpUid')
printf 'Dump file for import: /meili_data/dumps/%s.dump\n' "$dump_uid"
unset master_key
```

### Phase 3: Cut over to StatefulSet on 1.37.0

1. Ensure `stateful-set-meilisearch.yaml` has:
   - `MEILI_DB_PATH=/meili_data/data-v1.37.0-r1.ms`
   - `MEILI_IMPORT_DUMP=/meili_data/dumps/<dumpUid>.dump`
2. Ensure no `Deployment/meilisearch` manifest exists in Argo source for this app (remove it from `karakeep/`).
3. Sync ArgoCD with prune enabled so the old Deployment is removed and StatefulSet is created.
4. Verify import and readiness:

```bash
kubectl -n karakeep get sts meilisearch
kubectl -n karakeep get pods -l app=meilisearch -o wide
kubectl -n karakeep logs statefulset/meilisearch --tail=200
```

### Phase 4: Finalize

After the first successful import:

1. Remove `MEILI_IMPORT_DUMP` from `stateful-set-meilisearch.yaml`.
2. Commit that cleanup and sync again.

## Full-page archives

`karakeep-env` enables `CRAWLER_FULL_PAGE_ARCHIVE` with a 50 MB per-page
limit. This supplements the existing PDF snapshots with a local HTML archive.
Archives larger than the limit are discarded. Video downloading remains disabled.
Existing bookmarks need a recrawl to acquire an archive; verify a newly added or
recrawled bookmark offers a working full-page archive before bulk recrawling.
Watch PVC usage as the archive collection grows. Disable the flag to stop new
archives; existing assets are retained.

# TODO

* Metrics + Dashboard
