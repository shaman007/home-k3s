# UniFi console trusted-TLS migration

## Operational status

On 2026-11-11, after owner approval and interactive authentication, the console
certificate was uploaded inactive, checked, and activated through the installed
UniFi OS 6.0.130 certificate-management API. No firmware files were edited.
The previous active selection was the built-in certificate; no previous
certificate was deleted. Independent authenticated SSH recovery was retained.

The console at `192.168.1.1:443` now serves `unifi.int.andreybondarenko.com`,
issued by Let's Encrypt YR2, expiring **2027-02-09 18:44:42 UTC**.
Active certificate ID: `b1009401-144d-47e1-96df-d642fd001a35`.
Leaf SHA256: `32a1ea0f317bcae49440adf5fd9ab0c281f5e750034d3978197a31839b49e318`.
Fresh system-trust hostname verification passed from the workstation and the
running BGP container trust store. Chain and key were matched before activation;
private material traveled only in process memory over authenticated encrypted
transport to the supported API. No private key or credential entered Git or logs.

The private DNS A record now maps this name directly to `192.168.1.1`, not the
private ingress VIP. Workstation resolution and the router DNS answer agree.
Other DNS records were compared before/after and remained unchanged. No public
A record, ingress, service, or additional router port was created.

## Source and deployment

The Certificate manifest `unifi/poller/certificate-unifi-console-tls.yaml` was
published by the owner in `193b51f2`, reconciled by Argo, and is Ready.
It uses production `letsencrypt-internal-prod`, RSA-2048 with key rotation,
a 90-day lifetime and renewal 30 days before expiry.

The reviewed client changes are now applied to repository source: both containers
use the trusted hostname, UnPoller explicitly enables verification, and the BGP
exporter has no unverified-context implementation or insecure override. A pod-local
hostname mapping preserves direct routing to the router. Existing egress remains
scoped to the router IP. The original staged patches are retired after application;
they remain available in Git history.

The owner published `08aa3472`. Both `unifi-exporter` and
`kubernetes-prometheus` reconciled that revision and are Healthy. The deployed
BGP client authenticates with system trust; background scrape success is 1,
last-success advances, all three reviewed peers/routes are present, and policy
violations are zero. The served-certificate expiry metric is scraped by
Prometheus. UnPoller explicitly enables SSL verification and returns fresh
controller-derived client metrics. Prometheus loaded
`UDMConsoleCertificateExpiring` with health `ok` and state `inactive`.

Successful CI and genuine scanner closure of alerts **7615** and **7524** are
still pending: the workflows were queued at the post-rollout verification.
Neither alert is dismissed as an exception.

In `/home/shaman007/git/unifi-infra`, the provider now uses the trusted hostname
with `allow_insecure=false`. The new `unifi_dns_record.console_tls` resource has
been imported by its actual ID, `865884b9-e0d2-45e8-8c2c-94fcfc6bc38b`, using
`default:<id>`. Formatting and validation pass; a targeted read-only plan reports
zero changes. A full read-only plan exited 1, reporting 17 additions and eight
updates outside this resource; full-plan verification remains incomplete.
No broad apply was run. This directory currently has no Git metadata;
its file changes are separate from this repository's commit. Preserve unrelated
infrastructure and review any full-plan drift before applying it.

## Renewal and rollback

cert-manager renewal updates the Kubernetes Secret; it **does not** replace the
router's uploaded certificate. Renewal is an operator handoff, not an unattended
uploader. After each renewal, use the supported console certificate API/UI to
upload the complete matching chain/key as inactive, validate identity and metadata,
activate it, and verify fresh system-trust connections and both consumers.
Never print private material, save it to review artifacts, or alter firmware paths.

The collector exports `unifi_bgp_tls_certificate_expiry_timestamp_seconds` from a
fresh verified handshake to the actual router. `UDMConsoleCertificateExpiring`
warns when that live certificate has under 21 days left for 30 minutes, gated on
successful collection. A renewed Secret alone cannot clear this warning.
Failed collection is covered separately by `UDMBGPCollectionUnavailable`.
Both rules are loaded by the reconciled Prometheus deployment.

Before client rollout, the supported certificate selection can restore the prior
built-in identity through independent recovery access. After verified clients
are deployed, restore a valid trusted certificate instead: certificate failure
must remain visible, and verification bypass must not be reintroduced. Keep
recovery access until deployment and renewal checks are complete.

## Read-only verification

```sh
curl --noproxy '*' --resolve unifi.int.andreybondarenko.com:443:192.168.1.1 \
  --connect-timeout 5 --max-time 15 --silent --show-error --output /dev/null \
  https://unifi.int.andreybondarenko.com/
```

This verifies trust and hostname independently of DNS caches. Also check the
actual container trust stores and authenticated data; a successful TLS handshake
alone does not prove collection works.

## Sources

- [Ubiquiti certificate UI guidance](https://help.ui.com/hc/en-us/articles/34210126298775-Self-Hosting-UniFi)
- [UnPoller verification configuration](https://unpoller.com/docs/install/configuration/)

The installed console API was inspected before use. The private-key upload and
activation were explicitly authorized by the owner. No agent push occurred.
