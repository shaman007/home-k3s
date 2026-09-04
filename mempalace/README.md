# MemPalace

MemPalace is deployed as a persistent MCP HTTP service and toolbox pod.
The application runs from the official, version-pinned MemPalace container image;
Renovate discovers updates through the image tag in the Deployment.

The MCP server uses Streamable HTTP behind the internal Traefik ingress. Its authenticated
endpoint is `https://mempalace.w386.k8s.my.lan/mcp`; the bearer token is sourced from
`kv/mempalace` in Vault through External Secrets.

Codex is configured to read the bearer token from `MEMPALACE_MCP_HTTP_TOKEN`. Export it
before starting Codex:

```sh
export MEMPALACE_MCP_HTTP_TOKEN="$(vault kv get -field=mcp_http_token kv/mempalace)"
```

Persistent paths:

- `/data/.mempalace` — MemPalace databases and palace data
- `/data/imports` — import sources such as markdown or YAML files
- `/data/projects` — a workspace mirror for repositories and project content

The legacy `/data/venv` directory from the former bootstrap installation is no longer
used and can be removed manually after a successful rollout and data check.

Recommended usage:

```sh
kubectl -n mempalace exec -it deploy/mempalace -- sh
mkdir -p /data/workspace /data/imports /data/projects
mempalace init /data/workspace
mempalace status
```

Useful commands:

```sh
# inspect the current store
kubectl -n mempalace exec deploy/mempalace -- mempalace --version

# list persisted data
kubectl -n mempalace exec deploy/mempalace -- find /data/.mempalace -maxdepth 3 -type f | head

# check the HTTP transport without authentication
curl https://mempalace.w386.k8s.my.lan/healthz
```
