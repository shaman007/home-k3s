# AGENTS.md

## Command approval policy

### Allowed without asking
- `kubectl get`
- `kubectl describe`
- `kubectl logs`
- `kubectl top`
- `kubectl events`
- `kubectl explain`
- `kubectl api-resources`
- `kubectl api-versions`
- `kubectl cluster-info`
- `kubectl version`
- `kubectl auth can-i`
- `kubectl config get-contexts`
- `kubectl config current-context`
- `kubectl config view`
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

## Notes
- Keep `kubectl` approvals scoped to read-only commands only.
- Do not use broad `kubectl` approvals.
- Keep Docker usage scoped to diagnostics/read-only operations.
