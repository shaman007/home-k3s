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

## Meilisearch migration: 1.36.0 (Deployment) -> 1.37.0 (StatefulSet)

### Phase 1: Restore availability

`deployment-meilisearch.yaml` is pinned to `v1.36.0` and keeps:

* `MEILI_DB_PATH=/meili_data/data-v1.36.0-r2.ms`

Sync ArgoCD and verify:

```powershell
kubectl -n karakeep get deploy meilisearch
kubectl -n karakeep get pods -l app=meilisearch
kubectl -n karakeep logs deploy/meilisearch --tail=50
```

### Phase 2: Export dump from 1.36.0

```powershell
# terminal 1
kubectl -n karakeep port-forward svc/meilisearch 7700:7700
```

```powershell
# terminal 2
$masterKey = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String((kubectl -n karakeep get secret karakeep-secret-env -o jsonpath='{.data.MEILI_MASTER_KEY}')))
$headers = @{ Authorization = "Bearer $masterKey" }

$dumpTask = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:7700/dumps" -Headers $headers
$taskUid = $dumpTask.taskUid

do {
  Start-Sleep -Seconds 2
  $task = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:7700/tasks/$taskUid" -Headers $headers
  $task.status
} while ($task.status -in @("enqueued", "processing"))

if ($task.status -ne "succeeded") {
  throw "Dump task failed: $($task | ConvertTo-Json -Depth 10)"
}

$dumpUid = $task.details.dumpUid
$dumpFile = "/meili_data/dumps/$dumpUid.dump"
Write-Host "Dump file for import:" $dumpFile
```

### Phase 3: Cut over to StatefulSet on 1.37.0

1. Ensure `stateful-set-meilisearch.yaml` has:
   - `MEILI_DB_PATH=/meili_data/data-v1.37.0-r1.ms`
   - `MEILI_IMPORT_DUMP=/meili_data/dumps/<dumpUid>.dump`
2. Ensure `deployment-meilisearch.yaml` is disabled (or removed from Argo source) to avoid duplicate controllers.
3. Sync ArgoCD with prune enabled so the old Deployment is removed and StatefulSet is created.
4. Verify import and readiness:

```powershell
kubectl -n karakeep get sts meilisearch
kubectl -n karakeep get pods -l app=meilisearch -o wide
kubectl -n karakeep logs statefulset/meilisearch --tail=200
```

### Phase 4: Finalize

After the first successful import:

1. Remove `MEILI_IMPORT_DUMP` from `stateful-set-meilisearch.yaml`.
2. Commit that cleanup and sync again.

# TODO

* Metrics + Dashboard
