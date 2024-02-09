# Registry deployment from the Helm chart

```bash
upgrade registry twuni/docker-registry -f ./registry-values.yaml  --namespace=registry --create-namespace
```
