# Registry deployment from the Helm chart

```bash
helm upgrade registry twuni/docker-registry -f ./registry-values.yaml  --namespace=registry --create-namespace
```

* be sure to give it enough memory and CPU to handle large layers
* don't forget ingress upload limits
* password hash file is just .htpasswd
