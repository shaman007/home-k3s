# Traefik ACME to cert-manager migration

This migration deliberately keeps Traefik's existing `acme.json` certificates
available until every public router uses a ready Kubernetes TLS Secret. Do not
combine all phases into one deployment.

## Phase 1: release HTTP-01 and install cert-manager

The first change:

- installs cert-manager and staging and production ClusterIssuers;
- changes Traefik's temporary native ACME solver from HTTP-01 to TLS-ALPN-01;
- retains the `letsencrypt` resolver, `acme.json`, the Traefik PVC, and the mail
  certificate exporter.

This releases port 80 for cert-manager HTTP-01 challenges without withdrawing
certificates already served from `acme.json`. Verify the cert-manager
Application, all three deployments, the webhook, the ClusterIssuer, Traefik,
and the current external certificates before continuing.

Rollback: revert the ClusterIssuer/application changes and change Traefik's
resolver back to `httpChallenge.entryPoint: web`.

## Phase 2: canary

Create an explicit staging Certificate for `year.andreybondarenko.com` in the
`year` namespace, but leave the Ingress on Traefik's native resolver. After the
staging Certificate is Ready, replace it with a production Certificate and wait
for that to become Ready too. Then update the Ingress in a separate change:

- remove `traefik.ingress.kubernetes.io/router.tls.certresolver`;
- add `spec.tls` with the host and the cert-manager Secret.

Confirm the externally served serial number matches the Secret before bulk
migration. The `year` default-deny policy selects only the application Pod, so
it does not isolate cert-manager's solver Pod.

## Phase 3: issue namespaced certificates

Create one Certificate per namespace, combining hosts only where shown:

| Namespace | DNS names |
| --- | --- |
| bitwarden | `bitwarden.andreybondarenko.com` |
| convertx | `convert.andreybondarenko.com` |
| dawarich | `dawarich.andreybondarenko.com` |
| harbor | `harbor.andreybondarenko.com` |
| hister | `hister.andreybondarenko.com` |
| homeassistant | `ha.andreybondarenko.com` |
| immich | `immich.andreybondarenko.com` |
| karakeep | `keep.andreybondarenko.com` |
| keycloak | `sso.andreybondarenko.com` |
| mastodon | `mastodon.andreybondarenko.com` |
| matrix | `shaman007.com` |
| nextcloud | `cloud.andreybondarenko.com`, `office.andreybondarenko.com` |
| open-webui | `chat.andreybondarenko.com` |
| plex | `plex.andreybondarenko.com` |
| seaweedfs | `s3.andreybondarenko.com` |
| spotify | `spt.andreybondarenko.com`, `spt-server.andreybondarenko.com` |
| stirling-pdf | `pdf.andreybondarenko.com` |
| wordpress | `andreybondarenko.com` |

Namespaces whose default-deny policy selects every Pod need an additional
solver ingress policy allowing Traefik Pods to TCP port 8089 on Pods labelled
`acme.cert-manager.io/http01-solver: "true"`: `harbor`, `hister`, `immich`,
`karakeep`, `keycloak`, `mastodon`, `nextcloud`, `plex`, `seaweedfs`, `spotify`,
`stirling-pdf`, and `wordpress`.

Issue and verify the Certificates before changing any routers. Use Argo sync
waves if a Certificate and its router must be in the same Application sync.

## Phase 4: switch routers

For Kubernetes Ingress resources, remove the Traefik cert-resolver annotation
and add `spec.tls[].secretName`. For sensitive-path IngressRoutes, replace
`tls.certResolver` with `tls.secretName`, referencing the same namespace-local
Secret as the corresponding Ingress.

The `.my.lan` names used by `comfyui`, `ollama`, and one `open-webui` rule cannot
be issued by public ACME. Remove their ineffective public cert-resolver use and
leave them on Traefik's default certificate until an internal CA migration is
handled separately.

Perform the cutover in small batches and compare the externally served
certificate serials with their Secrets after each batch.

## Phase 5: mail

Issue `andreybondarenko.com` into a new Secret in the `mail` namespace. Once it
is Ready, update Postfix and Dovecot to use it, verify SMTP submission and IMAPS,
and update the platform-health certificate check. Do not let cert-manager and
the exporter write the same Secret during the transition.

After mail verification, remove the exporter Application and manifests, its
ServiceAccount/RBAC/Cilium policy, the placeholder `letsencrypt-prod` Secret,
and the Argo ignore-difference rule for that Secret.

## Phase 6: remove native ACME

Only after every public router and mail consumer is verified:

- remove all remaining `certResolver: letsencrypt` references;
- remove `certificatesResolvers.letsencrypt` from both Traefik values sources;
- retain the Traefik PVC because it also stores the GeoIP database;
- leave `acme.json` untouched initially for rollback, then clean it up during a
  later maintenance window.

Final checks: no Traefik ACME resolver arguments, no exporter RBAC, every
Certificate Ready, no failed Orders or Challenges, all Argo Applications
Synced/Healthy, and external HTTPS/SMTP/IMAPS certificate checks passing.
