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

# TODO

* Metrics + Dashboard
