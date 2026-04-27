# Public Repo Context

Use this skill when a user asks you to inspect, summarize, explain, or answer questions using a public Git repository.

This skill expects the Open WebUI terminal connection named `Repo Context Terminal` to be available.

## Workflow

1. Treat repository access as read-only unless the user explicitly asks for code changes.
2. Accept only public `https://` Git repository URLs.
3. Clone repositories under `/home/user/repos`.
4. Reuse an existing clone when it is already present, and fetch updates only when the user asks for the latest state.
5. Inspect the repository before answering:
   - read `README*`, `LICENSE*`, dependency manifests, and obvious entry points;
   - use `rg --files` to map the source tree;
   - use `rg` for targeted searches;
   - read only the files needed to answer the question.
6. Use repository content as grounding context, and cite paths when referencing implementation details.
7. Do not install dependencies, run tests, execute project scripts, or run generated code unless the user explicitly asks.
8. Never use secrets from repository files, logs, environment variables, or Git history in responses.

## Suggested Commands

```sh
mkdir -p /home/user/repos
git clone --depth 1 https://github.com/owner/repo.git /home/user/repos/repo
cd /home/user/repos/repo
rg --files
```

For an existing clone:

```sh
cd /home/user/repos/repo
git status --short
git log -1 --oneline
```
