#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: $0 <vault-token>"
  exit 1
fi

VAULT_TOKEN="$1"
# Get all namespaces in the cluster
namespaces=$(kubectl get ns -o jsonpath='{.items[*].metadata.name}')

for ns in $namespaces; do
  echo "Processing namespace: $ns"

  #  vault-token-registry exists?
  if ! kubectl get secret vault-token-registry -n "$ns" &> /dev/null; then
    echo "  Creating secret 'vault-token-registry' in $ns"
    kubectl create secret generic vault-token-registry \
      --from-literal=token="$VAULT_TOKEN" \
      -n "$ns"
  else
    echo "  Secret 'vault-token-registry' already exists in $ns"
  fi

  # ExternalSecret exists?
  if ! kubectl get externalsecret my-private-registry -n "$ns" &> /dev/null; then
    echo "  Creating ExternalSecret in $ns"
    cat <<EOF | kubectl apply -n "$ns" -f -
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: my-private-registry
  namespace: $ns
spec:
  refreshInterval: "1m"
  secretStoreRef:
    name: vault-secret-store-registry
    kind: SecretStore
  target:
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: "{{ .mysecret | toString }}"
    name: my-private-registry
    creationPolicy: Owner
  data:
    - secretKey: mysecret
      remoteRef:
        key: registry-access
        property: my-private-registry
EOF
  else
    echo "  ExternalSecret already exists in $ns"
  fi

  # SecretStore exists?
  if ! kubectl get secretstore vault-secret-store-registry -n "$ns" &> /dev/null; then
    echo "  Creating SecretStore in $ns"
    cat <<EOF | kubectl apply -n "$ns" -f -
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-secret-store-registry
  namespace: $ns
spec:
  provider:
    vault:
      server: "http://192.168.1.111:8200"
      path: "kv"
      version: "v2"
      auth:
        tokenSecretRef:
          name: vault-token-registry
          key: token
EOF
  else
    echo "  SecretStore already exists in $ns"
  fi

done
