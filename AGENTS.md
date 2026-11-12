# AGENTS.md

## Kubernetes and Helm approval policy

- Run read-only `kubectl` and `helm` diagnostics without asking, subject to the active sandbox.
- Common approved `kubectl` examples: `get`, `describe`, `logs`, `top`, `events`, `explain`, `exec` for diagnostic/read-only commands, `api-resources`, `api-versions`, `cluster-info`, `version`, `auth can-i`, `config get-contexts`, `config current-context`, `config view`.
- Common approved `helm` examples: `list`, `status`, `history`, `get`, `show`, `search`, `template`, `version`, `repo list`.
- Keep approvals scoped to verifiably read-only commands. Ask before any `kubectl` or `helm` command that creates, updates, patches, deletes, rolls back, installs, upgrades, uninstalls or otherwise changes live cluster state, unless it is listed under Never run. If mutability is unclear, ask first.

### Never run in this repository

- `git commit`
- `git push`
- `kubectl apply`
- `docker push`
- `docker build`
- `docker compose up`
- `docker run`

Do not stage repository changes. Keep Docker usage scoped to diagnostics/read-only operations. General Git and Docker diagnostic rules are in the global `AGENTS.md`.

## GitOps working conventions

- This repository is a GitOps-based Kubernetes home-lab. Prefer inspecting the app-specific manifest in its folder and the matching Argo CD application manifest before suggesting changes.
- When troubleshooting a deployment, inspect the manifest, related ConfigMaps/Secrets, persistent volumes, and pod logs/events before proposing a fix. Do not print or persist secret values.

## Project memory fallback

- Follow the global MemPalace lookup and checkpoint policy.
- Prefer MemPalace MCP. If MCP is unavailable, the MemPalace pod paths `/data/.mempalace`, `/data/imports`, and `/data/projects` are a project-specific fallback, subject to the same permissions and secret-handling rules.
- Store repository checkpoints in the project's structured MemPalace context or under `/data/projects` when using the pod fallback.

## Project skills

- grafana-operator: Use for Grafana health, datasource/dashboard/folder/alert inventories and targeted troubleshooting or changes. (file: /home/shaman007/.codex/skills/grafana-operator/SKILL.md)
- k8s-readonly-ops: Use for read-only Kubernetes and Helm diagnostics and approval boundaries for live changes. (file: /home/shaman007/.codex/skills/k8s-readonly-ops/SKILL.md)
