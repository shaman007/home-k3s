# MemPalace

MemPalace is deployed here as a persistent toolbox pod rather than a public web app.

The upstream project currently ships a CLI and MCP server, not an HTTP service, so this
deployment keeps a writable volume with the virtual environment and palace data under
`/data`.

Typical usage:

```sh
kubectl -n mempalace exec -it deploy/mempalace -- sh
mempalace init /data/workspace
mempalace status
```
