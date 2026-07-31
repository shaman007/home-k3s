<!--
Sync Impact Report
- Version change: template (unratified) -> 1.0.0
- Modified principles:
  - Template placeholders -> I. GitOps Is the Source of Truth
  - Template placeholders -> II. Read-Only Inspection Comes First
  - Template placeholders -> III. Mutation Requires Explicit Authority
  - Template placeholders -> IV. Secrets Must Remain Secret
  - Template placeholders -> V. Changes Stay Minimal and Evidence-Based
- Added sections:
  - Operational Tools and Durable Knowledge
  - Investigation and Change Workflow
- Removed sections: none (template placeholders were resolved)
- Follow-up TODOs: none
-->
# home-k3s Constitution

## Core Principles

### I. GitOps Is the Source of Truth
Repository manifests and their matching Argo CD `Application` manifests MUST be treated as the
primary description of desired cluster state. Work on an application MUST begin by inspecting both
the application-specific directory and its Argo CD entry point. Live-cluster observations MAY
explain drift or runtime failure, but MUST NOT silently replace the declared GitOps configuration.

Rationale: keeping desired state in Git makes cluster behavior reviewable, reproducible, and
recoverable.

### II. Read-Only Inspection Comes First
Diagnosis MUST begin with non-mutating inspection. Read-only `kubectl`, `helm`, and `git` commands
MAY run without prior approval when their arguments are verifiably non-mutating. Approved examples
include:

- `kubectl get`, `describe`, `logs`, `top`, `events`, `explain`, `api-resources`, `api-versions`,
  `cluster-info`, `version`, `auth can-i`, and read-only `config` queries;
- `helm list`, `status`, `history`, `get`, `show`, `search`, `template`, `version`, and `repo list`;
- `git status`, `diff`, `log`, `show`, `grep`, `rev-parse`, `branch --show-current`,
  `branch --list`, `tag --list`, `ls-files`, `blame`, `remote -v`, `reflog`, and read-only
  `config --get` queries; and
- `docker version`, `info`, `ps`, `images`, `inspect`, `logs`, `stats --no-stream`, plus
  `docker exec` only for diagnostic, read-only commands.

If a command's mutability is uncertain, execution MUST pause for explicit approval.

### III. Mutation Requires Explicit Authority
Any `kubectl` or `helm` action that creates, updates, patches, deletes, scales, rolls back,
installs, upgrades, uninstalls, or otherwise changes live cluster state MUST receive explicit
approval first.
Any Git action that changes the worktree, index, refs, stash, submodules, remotes, or commits MUST
also receive explicit approval first.

The following commands are prohibited for repository work and MUST NOT be run: `git commit`,
`git push`, `kubectl apply`, `docker push`, `docker build`, `docker compose up`, and `docker run`.
Docker use MUST remain limited to diagnostics and read-only inspection.

Rationale: the repository controls production-like infrastructure, so operational side effects
must be deliberate and attributable.

### IV. Secrets Must Remain Secret
Vault MUST be treated as a sensitive secret-management system. Secret values MUST NOT be exposed in
logs, command output, specifications, plans, tasks, diffs, or responses. Vault investigation MUST
prefer read-only operations, including `vault kv get`, `vault auth list`, `vault secrets list`, and
`vault status`, with output constrained to the minimum needed. Any Vault state change MUST be
explicitly confirmed, narrowly scoped, and auditable.

Vault-related diagnosis MUST inspect the relevant secret paths, policies, access entries, and
application configuration before a fix is proposed.

### V. Changes Stay Minimal and Evidence-Based
Changes MUST be minimal, reversible, and consistent with the repository's surrounding YAML,
documentation, layout, and naming conventions. Deployment diagnosis MUST inspect the declared
manifest, related ConfigMaps and Secrets, persistent volume claims, pod logs, and events before a
fix is proposed. Conclusions and proposed changes MUST be supported by observed repository or
runtime evidence.

Rationale: small, convention-aligned changes reduce blast radius and make review and rollback
practical.

## Operational Tools and Durable Knowledge

The applicable repository skill MUST be used when its domain matches the task:

- `k8s-readonly-ops` for Kubernetes and Helm inspection;
- `git-readonly-ops` for non-mutating Git inspection;
- `grafana-operator` for Grafana health, inventory, troubleshooting, dashboards, and alerts; and
- `vault-operator` for Vault health, access, policy, and secret-path troubleshooting.

These skills do not relax the approval and prohibition rules in this constitution.

MemPalace is the preferred durable store for repository context, imported notes, and project
snapshots. When persistent memory is needed, work MUST prefer the MemPalace pod paths
`/data/.mempalace`, `/data/imports`, and `/data/projects`. Its MCP server SHOULD be used when
structured retrieval or long-lived context materially benefits the workflow.

## Investigation and Change Workflow

1. Identify the application directory and matching Argo CD `Application` manifest.
2. Inspect the repository-declared configuration and all directly related resources.
3. Use read-only Git, Kubernetes, Helm, Docker, Grafana, or Vault inspection as applicable.
4. Record evidence without disclosing secret values.
5. Propose the smallest reversible change consistent with nearby repository conventions.
6. Obtain explicit approval before any allowed mutation; never execute a prohibited command.
7. Validate repository changes through non-mutating rendering, linting, or diff inspection when
   those checks are available.

Specifications, plans, task lists, reviews, and implementation work MUST demonstrate compliance
with this workflow. Any necessary exception MUST be documented with its rationale and approved by
the repository owner before work proceeds; an exception cannot authorize a prohibited command.

## Governance

This constitution is the canonical governance document for Spec Kit work in this repository.
`AGENTS.md` and `SKILLS.md` remain operational references; where their guidance conflicts with this
constitution, the stricter safety constraint governs until the documents are reconciled.

Amendments MUST be documented in this file, include an updated Sync Impact Report, and receive
repository-owner approval. Constitution versions follow semantic versioning: MAJOR for incompatible
governance changes or removed principles, MINOR for new principles or materially expanded
requirements, and PATCH for clarifications that do not change obligations.

Every specification, plan, task set, and review MUST include a constitution-compliance check.
Reviewers MUST reject unexplained violations. Runtime guidance may elaborate on these requirements
but MUST NOT weaken them.

**Version**: 1.0.0 | **Ratified**: 2026-07-31 | **Last Amended**: 2026-07-31
