# Postgres deployment from the Helm chart

```bash
helm install postgres oci://registry-1.docker.io/bitnamicharts/postgresql --namespace db -f ./values.yaml
```
