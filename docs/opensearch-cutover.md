# Mastodon OpenSearch cutover

Mastodon search is a derived index. PostgreSQL remains the source of truth, so
the Elasticsearch data directory must not be copied or attached to OpenSearch.

## Deployment order

1. Sync the `namespaces` Application, then sync `opensearch`.
2. Wait for `statefulset/opensearch` in namespace `opensearch` to become ready.
3. From inside the Mastodon namespace, verify that
   `http://opensearch.opensearch.svc.cluster.local:9200` returns an OpenSearch
   version response.
4. Sync `mastodon-custom` and the Mastodon chart Application so the web and
   Sidekiq workloads use the new endpoint.
5. Rebuild the derived search index:

   ```bash
   kubectl exec -n mastodon deploy/mastodon-web -c mastodon-web -- \
     bin/tootctl search deploy
   ```

6. Confirm search works from Mastodon and check the web and Sidekiq logs for
   OpenSearch client errors.
7. In a follow-up revision, remove the retired `elastic-stack-*` and
   `elastic-system*` Argo CD Applications and their repository manifests. Let
   the parent Application prune them, then confirm their managed resources are
   gone before deleting the old Elasticsearch Longhorn volume.

## Rollback

Before the old Elasticsearch resources are removed, rollback consists of
restoring the previous Mastodon endpoint and credentials and resyncing its
Applications. After Elasticsearch is retired, redeploy it and rebuild its
index from PostgreSQL; the OpenSearch volume is not a compatible rollback
source.

## Security boundary

The OpenSearch HTTP security plugin is disabled. The service is ClusterIP-only,
the namespace has default-deny ingress and egress policies, and ingress to port
9200 is allowed only from the Mastodon namespace. Do not expose the service or
broaden that policy without enabling authenticated TLS first.
