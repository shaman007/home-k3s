# Vault ACME migration for internal ingress certificates

Vault PKI exposes a role-specific ACME directory for cert-manager at:

`https://vault.w386.k8s.my.lan/v1/pki-int/roles/w386-k8s-my-lan-acme/acme/directory`

The `pki-int` mount contains the `w386-lab-intermediate` CA, signed by the
existing `w386 Lab Root CA`. The ACME configuration deliberately forbids the
top-level directory and permits only the `w386-k8s-my-lan-acme` role and the
key-backed intermediate issuer. The role accepts concrete subdomains of
`w386.k8s.my.lan` for server authentication, but rejects wildcard requests,
bare domains, localhost and IP SANs.

[`configure-pki-acme.sh`](../vault/configure-pki-acme.sh) reapplies the
non-secret Vault configuration. The intermediate private key remains inside
Vault and is protected by the Raft backup process.

## Staged cutover

1. Reconcile the `vault-acme` ClusterIssuer and the non-consumed
   `vault-acme-canary-tls` Secret. Require the canary Certificate, request,
   order and challenge to become Ready/valid.
2. Add one namespaced Certificate per existing internal ingress Secret. Use
   concrete DNS names rather than copying one wildcard certificate between
   namespaces.
3. After every ingress serves its cert-manager Secret, remove those targets
   and their cross-namespace RBAC from `vault-pki-renewer`.
4. Retain the renewer only for `vault-server-tls`, whose Vault API and Raft DNS
   names are not HTTP-01 ingress endpoints. Rename and simplify it separately
   after the ingress migration is complete.

Vault advertises the stable internal ingress URL so in-cluster and operator
clients receive the same ACME endpoint links. The Vault servers need egress
only to Traefik's HTTP entrypoint for ACME validation; existing policies
already permit Traefik to reach the Vault API on TCP port 8200.
