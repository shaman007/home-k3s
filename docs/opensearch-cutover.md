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
7. Confirm the retired `elastic-stack-*` and `elastic-system*` Argo CD
   Applications, namespaces, ECK custom resources, and old Elasticsearch
   Longhorn volume are gone. These resources were removed after the cutover.

## Rollback

Elasticsearch is retired. To roll back, redeploy it, restore the previous
Mastodon endpoint and credentials, and rebuild its index from PostgreSQL. The
OpenSearch volume is not a compatible rollback source.

## Security boundary

The OpenSearch HTTP security plugin is disabled. The service is ClusterIP-only,
the namespace has default-deny ingress and egress policies, and ingress to port
9200 is allowed only from the Mastodon namespace. Do not expose the service or
broaden that policy without enabling authenticated TLS first.
