# Open Terminal

Open Terminal provides an Open WebUI terminal backend for public Git repository context workflows.

Open WebUI is configured with `TERMINAL_SERVER_CONNECTIONS` to reach:

```text
http://open-terminal.open-terminal.svc.cluster.local:8000
```

The bearer key is read from Vault through External Secrets. Create this Vault value before syncing the app:

```text
kv/open-terminal api_key=<strong random token>
```

The SecretStore authenticates through the namespace-bound `vault-auth` ServiceAccount and the `external-secrets-open-terminal` Vault Kubernetes auth role.

The terminal pod is intended for read-oriented repository exploration. It persists working files in the `open-terminal-data` PVC and uses `/home/user/repos` for cloned public repositories.

The companion Open WebUI skill is stored at `docs/open-webui-repo-context-skill.md`.
