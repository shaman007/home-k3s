# Collabora deployment from the Helm chart:

```bash
helm repo add collabora https://collaboraonline.github.io/online/
helm install --create-namespace --namespace collabora collabora-online collabora/collabora-online -f ./values.yaml
```
