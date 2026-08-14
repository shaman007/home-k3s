# AGENTS.md

## Command approval policy

### Allowed without asking
- Any read-only `kubectl` command that inspects cluster state without mutating resources.
- Any read-only `helm` command that inspects releases, charts, values, rendered manifests, or history without mutating cluster state.
- Any read-only `git` command that inspects repository state without changing the worktree, index, refs, stash, remotes, or commits.
- Common approved `kubectl` examples: `get`, `describe`, `logs`, `top`, `events`, `explain`, `api-resources`, `api-versions`, `cluster-info`, `version`, `auth can-i`, `config get-contexts`, `config current-context`, `config view`.
- Common approved `helm` examples: `list`, `status`, `history`, `get`, `show`, `search`, `template`, `version`, `repo list`.
- Common approved `git` examples: `status`, `diff`, `log`, `show`, `grep`, `rev-parse`, `branch --show-current`, `branch --list`, `tag --list`, `ls-files`, `blame`, `remote -v`, `reflog`, `config --get`.
- `docker version`
- `docker info`
- `docker ps`
- `docker images`
- `docker inspect`
- `docker logs`
- `docker stats --no-stream`
- `docker exec` for diagnostic/read-only commands

### Never run
- `git commit`
- `git push`
- `kubectl apply`
- `docker push`
- `docker build`
- `docker compose up`
- `docker run`

## Working conventions
- This repository is a GitOps-based Kubernetes home-lab. Prefer inspecting the app-specific manifest in its folder and the matching Argo CD application manifest before suggesting changes.
- Keep changes minimal, reversible, and consistent with the surrounding YAML, docs, and naming conventions.
- When troubleshooting a deployment, inspect the manifest, related ConfigMaps/Secrets, persistent volumes, and pod logs/events before proposing a fix.
- Whenever work leaves uncommitted repository changes, include a suggested commit
  message in the final response by default. Base it only on the uncommitted diff,
  use a concise imperative subject, and add a short body for multiple material
  changes. Do not suggest one for a clean worktree, and never stage, commit, or push.

## MemPalace and MCP workflow
- MemPalace is the preferred durable knowledge store for repo-related context, imported notes, and project snapshots.
- Prefer reading and writing through the MemPalace pod under `/data/.mempalace`, `/data/imports`, and `/data/projects` when a task needs persistent memory.
- MemPalace exposes an MCP server; use it when a workflow benefits from structured knowledge retrieval or long-lived context.
- After completing a large or important repository change, checkpoint a concise durable summary to MemPalace by default, preferably in structured project memory or under `/data/projects`.
- Include the objective, major decisions, affected applications or manifests, validation performed, operational caveats, and remaining work. Never store credentials, secret values, tokens, raw secret manifests, transient logs, or verbose diffs.
- Treat multi-component, architectural, security, operational, data, and deployment-behavior changes as important. Skip minor or purely mechanical edits; if MemPalace is unavailable, note it briefly and continue without blocking the handoff.

## Notes
- Keep `kubectl`, `helm`, and `git` approvals scoped to verifiably read-only commands.
- Ask before any `kubectl` or `helm` command that creates, updates, patches, deletes, rolls back, installs, upgrades, uninstalls, or otherwise changes live cluster state, unless it is listed under Never run.
- Ask before any `git` command that changes the worktree, index, refs, stash, submodules, remotes, or commits.
- If it is unclear whether a `kubectl`, `helm`, or `git` action mutates state, ask first.
- Keep Docker usage scoped to diagnostics/read-only operations.

## Skills
A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills available in this workspace.

### Available skills
- grafana-operator: Operate and audit Grafana instances through the HTTP API with a practical, Kubernetes-friendly workflow. Use when users ask to check Grafana health, inventory datasources/dashboards/folders/alerts, troubleshoot dashboard issues, or apply targeted dashboard/alert changes. (file: C:/Users/me/.codex/skills/grafana-operator/SKILL.md)
- k8s-readonly-ops: Run read-only Kubernetes and Helm diagnostics without approval. Use when users ask to inspect cluster objects, logs, events, release state, rendered manifests, chart values, or Helm history with non-mutating commands, and ask before any live cluster change. (file: C:/Users/me/.codex/skills/k8s-readonly-ops/SKILL.md)
- git-readonly-ops: Run read-only Git inspection commands without approval. Use when users ask to inspect repository status, diffs, history, refs, tracked files, or authorship with non-mutating commands, and ask before any repository state change. (file: C:/Users/me/.codex/skills/git-readonly-ops/SKILL.md)
