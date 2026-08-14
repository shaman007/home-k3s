#!/usr/bin/env sh
set -eu

: "${VAULT_ADDR:?Set VAULT_ADDR to the Vault API URL}"
: "${VAULT_TOKEN:?Set VAULT_TOKEN to a Vault administrator token}"

role_name="w386-k8s-my-lan-acme"
issuer_name="w386-lab-intermediate"
issuer_id="$(vault read -format=json "pki-int/issuer/${issuer_name}" | jq -er '.data.issuer_id')"

vault write pki-int/config/issuers \
  default="${issuer_id}" \
  default_follows_latest_issuer=false

vault write "pki-int/roles/${role_name}" \
  issuer_ref="${issuer_id}" \
  allowed_domains=w386.k8s.my.lan \
  allow_subdomains=true \
  allow_bare_domains=false \
  allow_wildcard_certificates=false \
  allow_ip_sans=false \
  allow_localhost=false \
  enforce_hostnames=true \
  require_cn=false \
  server_flag=true \
  client_flag=false \
  code_signing_flag=false \
  email_protection_flag=false \
  key_type=rsa \
  key_bits=2048 \
  max_ttl=720h \
  no_store=false

vault write pki-root/roles/openbao-server \
  allowed_domains="openbao,openbao.openbao,openbao.openbao.svc,openbao.openbao.svc.cluster.local,openbao-active,openbao-active.openbao,openbao-active.openbao.svc,openbao-active.openbao.svc.cluster.local,*.openbao-internal,*.openbao-internal.openbao,*.openbao-internal.openbao.svc,*.openbao-internal.openbao.svc.cluster.local" \
  allow_bare_domains=true \
  allow_glob_domains=true \
  allow_subdomains=false \
  allow_localhost=false \
  allow_ip_sans=false \
  enforce_hostnames=true \
  server_flag=true \
  client_flag=false \
  key_type=rsa \
  key_bits=2048 \
  max_ttl=720h

vault secrets tune \
  -allowed-response-headers=Link \
  -allowed-response-headers=Location \
  -allowed-response-headers=Replay-Nonce \
  pki-int/

vault write pki-int/config/cluster \
  path=https://openbao.w386.k8s.my.lan/v1/pki-int

vault write pki-int/config/acme \
  enabled=true \
  default_directory_policy=forbid \
  allowed_roles="${role_name}" \
  allowed_issuers="${issuer_id}" \
  eab_policy=not-required \
  max_ttl=720h

vault write pki-int/config/auto-tidy \
  enabled=true \
  interval_duration=24h \
  tidy_acme=true \
  tidy_cert_store=true \
  tidy_revoked_certs=true \
  safety_buffer=72h \
  acme_account_safety_buffer=720h
