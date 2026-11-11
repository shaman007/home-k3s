# UniFi console trusted-TLS migration

Status: certificate issued after owner publication of 193b51f2. Argo reconciled
that revision and Certificate unifi-console-tls is Ready. The issued certificate
has SAN unifi.int.andreybondarenko.com, issuer Let's Encrypt YR2 and expiry
2027-02-09 18:44:42 UTC. Its public chain/hostname passes workstation system-trust
verification. No private-key field was extracted. Router activation and client
cutover are pending; both TLS alerts remain open until actual verified collection
and genuine rescanning.

## Identity and certificate

Use `unifi.int.andreybondarenko.com` for the console at `192.168.1.1:443`.
This name points directly to the router, **not** the private ingress VIP. No public
A record, Ingress, Service or new router port is needed. DNS-01 uses the existing
production `letsencrypt-internal-prod` issuer. On 2026-11-11 its Ready condition
was true, its ACME directory was production Let's Encrypt and its selector covered
`int.andreybondarenko.com`. The active Certificate manifest requests a separate
RSA-2048 key, a 90-day certificate and renewal 30 days before expiry. Owner publication and normal Argo reconciliation issued it; the public certificate
was inspected after issuance. No private key was retrieved.

The current console's public self-signed certificate has CN `unifi.local` and does
not cover `192.168.1.1`. Do not trust that observed leaf as a bootstrap authority.

## Prepared changes

- `unifi/poller/certificate-unifi-console-tls.yaml`: issuance only; no client rollout.
- `unifi-infra-dns.patch`: add the authoritative private A record in the separate
  `/home/shaman007/git/unifi-infra` checkout; leave its current provider working
  during certificate preparation. That checkout has not been modified.
- `verified-clients.patch`: remove the BGP exporter's unverified-context branch,
  synchronize its generated ConfigMap, update both container URLs, explicitly
  enable UnPoller verification and add a pod-local hostname mapping to the router.
  It includes regression coverage preventing the old override from disabling
  verification. This patch is inactive until deliberately applied to repository source.
- `unifi-infra-provider.patch`: change the OpenTofu provider URL and set
  `allow_insecure=false`, **after** the router presents the trusted certificate.

All three patches have passed dry-run applicability checks against the inspected
source. Recheck after any intervening source changes. The pod alias preserves direct
routing even while cluster DNS caches expire; authoritative DNS is still needed by
workstations and OpenTofu. Existing port-443 egress remains scoped to the router IP.

## Activation gates, in order

1. Review/publish the issuance manifest through normal GitOps. Require Certificate
   `unifi-console-tls` in namespace `unifi` to be Ready and its secret to contain a
   complete certificate chain and matching key for the exact hostname. No secret
   contents should enter terminals, logs, chat, Git or persistent review artifacts.
2. Review/apply the DNS-only change in `unifi-infra` through its normal OpenTofu
   workflow. Check the hostname resolves to `192.168.1.1` from the workstation and
   cluster. Do not substitute an ingress address or an external proxy endpoint.
3. Inspect the installed UniFi OS console's certificate-management UI and confirm
   its supported upload/activation and rollback mechanism. Ubiquiti documents
   certificate upload under Control Plane → Console → Certificates for UniFi OS
   Server; verify the actual gateway supports the corresponding operation before
   relying on that menu. Do not guess firmware paths or modify unifi-core files.
   Record the previous active certificate selection and preserve independent
   authenticated recovery access. Router activation is a separate approved step.
4. Use the approved secret-handling path to supply the newly issued chain/key to
   the supported console UI. Activate it, then require a new connection to validate
   system trust and the hostname. No fallback to the old observed leaf is allowed.
   Example read-only check, independent of DNS cache:

   ```sh
   curl --noproxy '*' --resolve unifi.int.andreybondarenko.com:443:192.168.1.1 \
     --connect-timeout 5 --max-time 15 --silent --show-error --output /dev/null \
     https://unifi.int.andreybondarenko.com/
   ```

   There is no `-k`. Verify the chain/name from the actual BGP and UnPoller container
   trust stores as well; workstation trust alone is insufficient. Check the
   served certificate expiry and public-key match through the approved procedure.
5. Apply/review the verified-client patch in this repository, regenerate/check the
   exporter ConfigMap, run the included exporter regressions and repository gates,
   then publish through normal GitOps. This removes the insecure implementation,
   rather than leaving it available behind a configuration switch.
6. Verify both containers are ready and actually collect authenticated controller
   data: BGP scrape success is 1, last success advances after activation, expected
   peers/routes remain present and UnPoller data is fresh. Do not dump credentials,
   request headers, cookies or full controller responses. Check console access
   and other existing integrations before declaring the router migration complete.
7. Apply the OpenTofu-provider patch only after workstation DNS/trust checks pass;
   run the normal read-only plan and confirm no unexpected infrastructure changes.
   Keep independent recovery access during this transition.
8. Require successful CI plus genuine modern scanner publication before confirming
   alerts 7615 and 7524 fixed. Neither has been dismissed as an exception.

## Renewal and rollback

cert-manager renewal updates the Kubernetes Secret; it **does not** update the
router's uploaded certificate. Before activation, assign/test a supported renewal
handoff: repeat secure upload/activation after each renewal, compare the live
router certificate/expiry, and validate both consumers again. An unattended uploader
is not included or claimed operational. Secret readiness alone must not be used as
proof of router renewal. Retain the 30-day renewal window as the operational margin.

Before client cutover, a failed certificate activation can be reverted using the
console's previously verified certificate selection/recovery path. After verified
clients are published, prefer restoring a known-good trusted certificate; a broken
TLS path must remain a visible scrape failure. Do not silently reintroduce
verification bypass to make metrics green. Do not delete the prior console recovery
material until trusted clients and renewal handling have been verified.

## Sources and limits

- [Ubiquiti certificate UI guidance](https://help.ui.com/hc/en-us/articles/34210126298775-Self-Hosting-UniFi)
- [UnPoller controller verification configuration](https://unpoller.com/docs/install/configuration/)

The public-certificate handshake and issuer readiness were checked read-only.
Initial preparation performed no issuance or live changes. After owner publication,
normal Argo/cert-manager reconciliation issued the certificate and its public chain
was validated read-only. No router authentication, private-key extraction, DNS
change, console activation, OpenTofu apply, client cutover or agent push occurred.
The prepared verified-only exporter passes 20 offline tests. Its actual router TLS
and authenticated collection remain deployment gates, not established by mocks.
