# MemPalace

MemPalace is deployed here as a persistent toolbox pod rather than a public web app.

The upstream project currently ships a CLI and MCP server, not an HTTP service, so this
deployment keeps a writable volume with the virtual environment, MemPalace state, imports,
and a mirrored project workspace under `/data`.

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
```
