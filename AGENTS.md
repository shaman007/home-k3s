# AGENTS.md

## Kubernetes and Helm approval policy

- Run read-only `kubectl` and `helm` diagnostics without asking, subject to the active sandbox.
- Common approved `kubectl` examples: `get`, `describe`, `logs`, `top`, `events`, `explain`, `exec` for diagnostic/read-only commands, `api-resources`, `api-versions`, `cluster-info`, `version`, `auth can-i`, `config get-contexts`, `config current-context`, `config view`.
- Common approved `helm` examples: `list`, `status`, `history`, `get`, `show`, `search`, `template`, `version`, `repo list`.
- Keep approvals scoped to verifiably read-only commands. Ask before any `kubectl` or `helm` command that creates, updates, patches, deletes, rolls back, installs, upgrades, uninstalls or otherwise changes live cluster state, unless it is listed under Never run. If mutability is unclear, ask first.

### Never run in this repository

- `git push`
- `kubectl apply`
- `docker push`
- `docker build`
- `docker compose up`
- `docker run`

Keep Docker usage scoped to diagnostics/read-only operations. General Git and Docker diagnostic rules are in the global `AGENTS.md`.

## Autonomous documentation, tools and tests commits

- Standing authorization: stage and commit your own verified task changes without another question when the entire proposed commit consists only of documentation (including README/AGENTS Markdown files and runbooks), `tools/` and/or `tests/`.
- Inspect the worktree and index first, preserve unrelated changes and never include someone else's staged work. Run checks appropriate to the change and review the exact staged diff before committing.
- This exception does not authorize commits containing application/runtime manifests, charts, policies or other files outside those categories. Obtain explicit authorization for such Git mutations. It does not authorize pushes, pull requests or live changes; the Never run restrictions still apply.
- Outside this exception, do not stage repository changes without explicit authorization.

## GitOps working conventions

- Before authorized live maintenance, create time-limited Alertmanager silences only for the alerts and resource labels affected by that work. Record the reason, expiry and silence IDs; remove them after verification or rollback. Renew only while work continues. Do not disable alert rules, silence unrelated resources or hide unexpected failures. Local preparation/read-only diagnosis does not require a silence. Creating and removing these narrowly scoped maintenance silences is included in authorization for the live maintenance itself.

- For repeatable Argo CD, backup-freshness and maintenance-baseline checks, run `python3 tools/ops/verify.py` with one subcommand: `argocd`, `backups` or `baseline`, following `docs/operational-procedures.md`. These read-only reports do not prove application functionality, recoverability or readiness to upgrade; respect their exit codes and stated scope.
- This repository is a GitOps-based Kubernetes home-lab. Prefer inspecting the app-specific manifest in its folder and the matching Argo CD application manifest before suggesting changes.
- When troubleshooting a deployment, inspect the manifest, related ConfigMaps/Secrets, persistent volumes, and pod logs/events before proposing a fix. Do not print or persist secret values.

## Project memory fallback

- Follow the global MemPalace lookup and checkpoint policy.
- Prefer MemPalace MCP. If MCP is unavailable, the MemPalace pod paths `/data/.mempalace`, `/data/imports`, and `/data/projects` are a project-specific fallback, subject to the same permissions and secret-handling rules.
- Store repository checkpoints in the project's structured MemPalace context or under `/data/projects` when using the pod fallback.

## Project skills

- grafana-operator: Use for Grafana health, datasource/dashboard/folder/alert inventories and targeted troubleshooting or changes. (file: /home/shaman007/.codex/skills/grafana-operator/SKILL.md)
- k8s-readonly-ops: Use for read-only Kubernetes and Helm diagnostics and approval boundaries for live changes. (file: /home/shaman007/.codex/skills/k8s-readonly-ops/SKILL.md)
