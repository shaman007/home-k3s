# OpenBao internal TLS and Harbor bootstrap routing

OpenBao internal TLS was activated on 2026-11-12. Harbor, DNS, MetalLB and the
router were not changed. See [EXECUTION.md](EXECUTION.md) for evidence, recovery
paths, current Argo pauses and the remaining publication gate.

## Trust and private keys

| Material | Location |
| --- | --- |
| Root CA private key | Kubernetes Secret `openbao/openbao-internal-root-ca`, `tls.key` |
| Root public certificate | Same Secret `tls.crt`; public copy [root-ca.pem](root-ca.pem) |
| Transition client trust | [dual-trust.pem](dual-trust.pem): ISRG Root X1/X2 plus the internal root; pinned in ESO `caBundle`, monitoring `vault-ca` ConfigMap and public-only `openbao-backend-trust` Secret |
| Active backend private key/certificate | Secret `openbao/openbao-server-letsencrypt-tls`; compatibility name retained, NOW issued by internal CA |
| Staging/canary leaf | Secret `openbao/openbao-internal-tls`, issued independently before cutover |
| Browser TLS | Existing `openbao-ingress-letsencrypt-internal-tls`, still ACME |
| Harbor TLS | Existing `harbor/harbor-tls`, unchanged |

Only public certificates are tracked in Git. Private keys are backed up as
age-encrypted files outside the cluster; plaintext keys were never written to
local files or printed. Decryption was verified in memory. Recovery of this
backup requires the independently kept age identity, not a working OpenBao.
Kubernetes Secret protection remains that of existing etcd/RBAC; this change
adds no HSM or new encryption-at-rest guarantee.

The namespaced cert-manager SelfSigned Issuer creates a dedicated ten-year root;
the CA Issuer issues ninety-day leaves with renewal thirty days before expiry.
Root key rotation is `Never`, leaf key rotation is `Always`. Expiry is covered
by the existing generic cert-manager certificate alert. Root renewal/rotation
requires planned old+new trust distribution; cert-manager does not update
pinned client trust automatically. Restore the same root after loss rather than
silently bootstrapping a new one.

## Dependency cycle removed

```text
Before: OpenBao backend ACME TLS -> GoDaddy token -> ESO -> working OpenBao
After:  Kubernetes + cert-manager -> local CA -> OpenBao backend TLS
          -> ESO -> GoDaddy token -> ACME browser certificates
```

The final operation differed from the initial proposal: retaining the existing
Secret and mount names allowed TLS hot reload on both 8200/8202 listeners, with
no OpenBao Pod restart or unseal. Its Certificate issuer is now `Issuer/
openbao-internal-ca`, so the old `letsencrypt` NAME creates no ACME dependency.
The server has no mandatory publicly issued backend certificate.

All 35 live ESO stores now use
`https://openbao-active.openbao.svc.cluster.local:8200` and explicit CA trust.
Vault roles, secret paths, audiences and credentials are unchanged. Traefik uses
explicit backend trust; browser TLS and hostname remain unchanged. Prometheus
uses the internal Service, hostname verification and the mounted public CA.
No additional DNS zone or system-wide host trust installation is needed.

The StatefulSet template and ConfigMap configure CA verification for FUTURE
starts, including Raft retry-join. It remains `OnDelete`; existing processes
were not restarted and still have their startup HCL copy. Runtime TLS reload is
verified, but cold-start/rejoin with the updated HCL is not yet exercised.
Compatibility SANs and temporary public-root trust are intentionally retained
for rollback and out-of-repository clients. Direct backend clients outside this
repository require CA configuration; use the existing public ingress for
workstation/API access unless internal DNS/trust are explicitly configured.

## Harbor: next phase only

User selected a separate minimal internal Traefik for nodes/LAN. It keeps the
hostname `harbor.andreybondarenko.com`, token realm and existing public certificate.
The public ingress stays unchanged. The additional controller has no plugins,
OIDC Secret, PVC, init download or CrowdSec; it watches only Harbor Ingresses.
Only TCP 443 is exposed and Harbor authentication remains required.

Candidate VIP `192.168.30.212` has no Kubernetes allocation, no configured
reservation found in unifi-infra, is outside DHCP `.50-.99`, and answered none
of four duplicate-address ARP probes on infrastructure VLAN 30. It is NOT
reserved/deployed. Router SSH authentication was unavailable, so live UniFi
lease/client inventory was not verified. Recheck immediately before allocation.

Important newly confirmed preparation gap: the UDM BGP configuration permits
only `.210/32`, `.211/32`, `.213/32` and maximum-prefix three. Before announcing
the new VIP, prepare the allowlist AND maximum-prefix update in unifi-infra,
then verify live router state. A Kubernetes pool/advertisement alone is
insufficient. No router configuration was changed in this phase.

Split DNS must work on Talos HOST resolvers and LAN clients, not merely CoreDNS.
Suppress the public AAAA in that split view unless an internal IPv6 VIP exists.
Public DNS/WAN forwarding and Harbor externalURL remain unchanged. Existing
Harbor HTTP-01 renewal must remain on public Traefik. The bootstrap route still
needs a valid `harbor-tls`; lost/expired certificate recovery is separate.

The offline [candidate generator](../../../tools/bootstrap/prepare_cold_start.py)
writes a new external directory only and never deploys. Supply an authentic
public CA and an independently checked VIP. Its output is a final-state
candidate, not authorization to sync Harbor. The new ingress Application has
no automated sync policy. Review Argo app/project inventory tests and UDM
routing before promotion.

## Validation tools

- [Explicit transition stages](../../../tools/bootstrap/openbao_tls_transition.py)
- [Verified TLS/health probe for all six listeners](../../../tools/bootstrap/probe_openbao_tls.py)
- [Candidate safety tests](../../../tests/test_cold_start_candidates.py)
- [Backend/consumer integration contracts](../../../tests/test_openbao_migration.py)

```sh
python3 -m unittest discover -s tests -p test_cold_start_candidates.py
python3 -m unittest discover -s tests -p test_openbao_migration.py
python3 -m unittest discover -s tests -p test_vault_acme.py
```

References: cert-manager [CA Issuer](https://cert-manager.io/docs/configuration/ca/),
[SelfSigned bootstrap](https://cert-manager.io/docs/configuration/selfsigned/),
ESO [API specification](https://external-secrets.io/main/api/spec/), Traefik
[entrypoint middleware inheritance](https://doc.traefik.io/traefik/master/reference/install-configuration/entrypoints/).
