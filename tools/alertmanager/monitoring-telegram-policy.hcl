# Merge these rules into the existing monitoring policy; do not replace it.
path "kv/data/telegram" {
  capabilities = ["read"]
}
