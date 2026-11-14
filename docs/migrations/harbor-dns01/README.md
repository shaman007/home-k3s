# Harbor DNS-01 and bootstrap image recovery

Prepared and tested in stages on 2026-11-14. Existing public/private Harbor
routes keep the same hostname and `harbor/harbor-tls` Secret. No A/AAAA/MX change
is required. Global HTTP-01 issuance and other certificates are unchanged.

## Why delegation, not broader solver permissions

The deployed GoDaddy webhook deliberately accepts only `_acme-challenge.*.int`
inside `andreybondarenko.com`. Its existing binary/image/permissions stay intact.
The exact production issuer `letsencrypt-harbor-dns01` selects only
`harbor.andreybondarenko.com` and follows this CNAME:

```
_acme-challenge.harbor.andreybondarenko.com.
  CNAME _acme-challenge.harbor.int.andreybondarenko.com.
```

The permanent CNAME is described in [dns-record.json](dns-record.json).
`tools/bootstrap/harbor_dns01_record.py` checks it using the existing solver PAT
only in memory; explicit `--create` creates only this missing record. Existing
conflicting records cause refusal, never replacement. No zone-wide PUT, token
export or change to routing records is used. Public TXT challenge data is created
and removed by the unchanged webhook. This is supported cert-manager
[CNAME Follow behavior](https://cert-manager.io/docs/configuration/acme/dns01/).

GoDaddy API access, public authoritative DNS, Internet/ACME, running cert-manager
and the webhook remain issuance dependencies. The webhook image is Harbor-backed:
include its exact digest in the independent image bundle and node preloads.
Missing solver credentials still need independent secret recovery; DNS-01 does
not solve that separate recovery problem.

## Transition and acceptance

1. Verify/create only the challenge CNAME. Confirm it through public DNS.
2. Use [staging-canary.yaml](staging-canary.yaml) as a separately authorized
   temporary test. It is outside active Argo source directories and writes only
   `harbor-dns01-staging-canary`, never the real `harbor-tls` Secret. Silence only
   its `CertificateNotReady` temporarily; remove the silence after verification.
3. Require actual staging Certificate Ready, valid Order and DNS-01 solver with
   CNAME Follow. An issuer Ready or visible TXT alone is not sufficient. Verify
   challenge cleanup and preserve unrelated TXT values.
4. Publish the exact production issuer and Harbor issuerRef together. Directory
   sources already include both new and changed manifests. If applying the
   authorized transition ahead of publication, pause only the affected Argo
   apps to prevent old Git reversing the change; restore after publication.
   Repository prohibition on `kubectl apply` remains in force.
5. Keep the existing production TLS Secret throughout issuance. Require a new
   production CertificateRequest/Order issued by DNS-01, Certificate Ready,
   valid chain/SAN/expiry and TLS verification on `.212` and the old public route.
   Do not stop Traefik, remove the old certificate or delete Harbor data to test.
6. Remove only temporary canary resources after their DNS cleanup completes;
   retain production issuer/account/certificate and the permanent CNAME.
7. Check Argo health/sync and alerts, expire maintenance silences. Commit/push
   follow the normal user approval/publication workflow.

## Rollback

Before transition record issuerRef, Certificate UID/revision and public leaf
fingerprint/expiry, without exporting private keys. Restore only issuerRef to
`letsencrypt-prod` (HTTP-01) through Git or the authorized guarded patch. Preserve
`harbor-tls`; a new valid DNS-01 leaf is also valid after rollback. Existing
public HTTP-01 solver and routes remain available. Do not delete the active
Secret, ACME account or certificate to force reissuance.

The challenge CNAME can remain without affecting A/AAAA traffic. If explicitly
retiring it, remove only created GoDaddy record ID
`bf48b556-1daa-404e-8539-f07305aa7bad` after checking its current name/type/data
against dns-record.json and checking there is no pending DNS-01 challenge.
Never restore an entire zone snapshot or delete all TXT records.

## Execution status

* Permanent challenge CNAME created and confirmed through GoDaddy API and public
  recursive resolvers; existing routing records untouched.
* Exact bootstrap references/digests preloaded and checked on all three nodes;
  no image removal, node restart or Pod restart requested.
* Staging test explicitly authorized after automatic review required a specific
  approval. Initial self-check saw internal DNS NXDOMAIN while public TXT was
  already visible; issuance success is recorded only after Certificate Ready.
* Runtime issuance/cutover and final checks are recorded below as completed,
  rather than inferred from the prepared files.

### Verified production outcome — 2026-11-14

Staging Certificate Ready/revision1 and valid Order passed via CNAME Follow;
GoDaddy removed its temporary TXT. Production `harbor-tls` is now Ready,
revision3, issued by `letsencrypt-harbor-dns01`, valid until
2027-02-11T23:44:20Z. Production Order valid and CertificateRequest reason Issued.
Both `.212` and unchanged public Traefik `.210` present the new certificate,
verified against system trust/SNI, returning the expected `/v2/` Bearer401.
New leaf SHA256:
`667ea07069cf7106dd5a2fa2ac21a3901b217b8b6ec509d643a5b0f6b975abab`.

All three nodes performed a successful native registry pull of the pinned
GoDaddy webhook image after renewal. Harbor containers retained zero restarts.
The production TLS Secret was never removed/exported. No A/AAAA/route changed.
Only `harbor-custom` is temporarily skip-reconcile until matching sources are
published; cert-manager and Harbor core reconciliation remain enabled.
Remove this single pause only after Git desired state contains the new issuerRef.

Authorized canary cleanup removed only staging Certificate/Issuer and their
separate leaf/account Secrets; no canary CertificateRequest/Order/Challenge
remains. Permanent CNAME and production issuer/account remain. Maintenance
silences `41c60f8f-9f1e-427b-a49c-88bc04e6ee6e` and
`6ab3707e-ef98-4417-acc7-a053f60531a8` were explicitly expired. Original expiries
were 2026-11-14T01:07:08.942118Z and 2026-11-14T01:11:12.801008Z respectively.
Old HTTP-01 provider remains unchanged for other certificates and rollback.

The global HTTP-01 self-check nameserver flag is retained: other public services
still use HTTP-01; the Harbor transition is not authorization to change them.
