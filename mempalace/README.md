# MemPalace

MemPalace is deployed as a persistent MCP HTTP service and toolbox pod.

The MCP server uses Streamable HTTP behind the internal Traefik ingress. Its authenticated
endpoint is `http://mempalace.w386.k8s.my.lan/mcp`; the bearer token is sourced from
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
- `/data/venv` — the pinned virtualenv for the installed MemPalace version

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
kubectl -n mempalace exec deploy/mempalace -- /data/venv/bin/python -c "import importlib.metadata as m; print(m.version('mempalace'))"

# list persisted data
kubectl -n mempalace exec deploy/mempalace -- find /data/.mempalace -maxdepth 3 -type f | head

# check the HTTP transport without authentication
curl http://mempalace.w386.k8s.my.lan/healthz
```
