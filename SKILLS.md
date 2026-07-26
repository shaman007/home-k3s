# SKILLS.md

## Kubernetes operations
- Prefer read-only `kubectl` inspection commands for cluster diagnostics.
- When investigating a deployment, inspect the manifest, relevant ConfigMap/Secret resources, PVCs, pod logs, and events before proposing changes.
- Use the repository’s GitOps structure and Argo CD application manifests as the primary source of truth.
- Keep changes minimal, reversible, and consistent with the surrounding YAML and naming conventions.

## Vault operations
- Treat Vault as a sensitive secret-management system; do not expose secrets in logs or output.
- Prefer read-only inspection commands such as `vault kv get`, `vault auth list`, `vault secrets list`, and `vault status` when gathering context.
- If a change to Vault state is necessary, confirm the intent explicitly and keep the change scoped and auditable.
- When troubleshooting Vault-related issues, inspect the relevant secret paths, policies, access entries, and application configuration before proposing a fix.

## MemPalace workflow
- Use MemPalace as the durable knowledge store for repo context, imported notes, and project snapshots.
- Prefer reading and writing through the MemPalace pod under `/data/.mempalace`, `/data/imports`, and `/data/projects` when persistent memory is needed.
- MemPalace exposes an MCP server; use it for structured retrieval or long-lived context when appropriate.
