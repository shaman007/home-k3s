# Private console login, CrowdSec observation, and Mastodon media caching

## Scope and rollout status

This change adds Keycloak OIDC to private infrastructure consoles, introduces
CrowdSec in simulation mode, and includes the production Mastodon media-cache configuration. Sablier remains deferred.

External prerequisites were provisioned on 2026-10-29: the `traefik-admin`
Keycloak client, its realm-role ID-token mapper, and the two dedicated OpenBao KV
entries, read policies, and namespace/service-account-bound Kubernetes auth roles.
No secret values are in this repository. GitOps revision `70607afa` reached the
cluster on 2026-10-29. CrowdSec and both Traefik releases rolled out; Longhorn
redirects to Keycloak. The two missing Thanos DNS records were subsequently
added through `/home/shaman007/git/unifi-infra/internal-service-dns.tf`. Both
certificates are Ready, monitoring ingress is Synced/Healthy at `0002dca9`, and
all six console endpoints serve valid TLS and redirect to the `traefik-admin`
Keycloak client. Real Keycloak browser login remains unverified.

## OIDC

`traefik-private` loads `sevensolutions/traefik-oidc-auth` v0.21.0. Its
`admin-oidc` middleware follows the existing `internal-clients-only` middleware
on these private ingresses:

| Host under `w386.k8s.my.lan` | Backend |
| --- | --- |
| `prometheus` | Prometheus HTTP UI/API |
| `alerts` | Alertmanager HTTP UI/API |
| `longhorn` | Longhorn frontend |
| `thanos` | Thanos Query |
| `thanos-compactor` | Thanos Compactor HTTP UI |
| `thanos-store` | Thanos Store Gateway HTTP UI |

Access requires the `admin` realm role in the `realm_roles` ID-token claim.
Authentication uses authorization code flow with S256 PKCE, issuer and audience
validation, and secure, HTTP-only, host-scoped cookies. No authentication bypass
is configured. Keycloak role removal takes effect as token/session claims renew;
checking authorization on each request does not query Keycloak role membership
on each request.

Grafana retains its own existing OIDC login. Internal Prometheus scraping,
Grafana datasource queries, Alertmanager delivery, and Thanos HTTP/gRPC Services
are not wrapped in interactive login. Clients that currently use the ingress
hostnames programmatically must switch to internal Services or use an explicitly
designed machine authentication path; there is no unauthenticated ingress API
exception.

The client contract is `keycloak/config/traefik-admin.client.json`. Callbacks are
an exact allowlist of `/oidc/callback` URLs, with no wildcards. Direct password
grants, implicit flow, and service accounts are disabled. This file is a single
client definition, not a realm import.

The `traefik-oidc` ExternalSecret reads `clientSecret` and `sessionSecret` from
OpenBao `kv/traefik-oidc`. Both Traefik replicas mount the same Secret. Secret
updates trigger Reloader; a session-key rotation invalidates existing sessions.
The SecretStore's role is bound only to `traefik/oidc-vault-auth`, and its policy
reads only the dedicated KV path.

Check prerequisites without changing configuration:

```sh
python3 tools/provision-traefik-security.py
```

The explicit `--write` option provisions or repairs only the dedicated client,
KV entries, ACLs and auth roles. It preserves an existing session key and reads
operator credentials into memory without logging them. It does not deploy
Kubernetes resources. Follow the repository approval rules before using it.

DNS verified on 2026-10-29: `thanos.w386.k8s.my.lan`,
`thanos-compactor.w386.k8s.my.lan`, and `thanos-store.w386.k8s.my.lan` all resolve
to `192.168.30.211`. The latter two records were added with a targeted OpenTofu
apply: exactly two additions, no updates or removals. Their configuration and
state live in `/home/shaman007/git/unifi-infra`; this is outside this repository.
Their Certificates use the existing `vault-acme` ClusterIssuer and are Ready.

After reconciliation, verify the SecretStore and ExternalSecret are Ready and
both private Traefik replicas load the plugin without errors. An unauthenticated
browser must reach Keycloak, an administrator must reach each backend, and a
non-admin account must receive 403. Repeat using both replicas and verify
Longhorn updates/live connections. Confirm internal monitoring targets and
Grafana's datasource queries still work. Browser login against real Keycloak has
not been validated by local mock-provider tests.

## CrowdSec observation

`crowdsec-config` manages RBAC, acquisition configuration, External Secrets and
network policies. `crowdsec` installs chart 0.24.2 / engine v1.8.1 in its own
namespace, with one log processor and one LAPI instance. Namespace quotas allow
six pods and 2 GiB of requested storage; the two LAPI PVCs request 1 GiB and
100 MiB on Longhorn. LAPI uses a Recreate strategy for its RWO volumes.

The processor streams public Traefik pod logs through the Kubernetes datasource
using selector `app.kubernetes.io/instance=traefik-traefik` in namespace `traefik`.
It does not collect private Traefik logs, read Secrets, or mount node log paths.
Its Role grants only pod list/watch/get and pod-log get in that namespace.

The chart's acquisition schema does not yet accept the engine's Kubernetes
source. The real datasource is therefore mounted separately as
`kubernetes-acquisition.yaml`, with `crowdsec_service.acquisition_path` pointing
to it. The chart-generated `/dev/null` file acquisition is unused. This keeps
chart schema validation enabled. The source fields were checked against the
v1.8.1 engine source and acquisition schema.

Selective enforcement was activated with explicit operator approval on
2026-10-30. Both public Traefik replicas run the registered bouncer. The desired
configuration remains uncommitted and unpushed. Global simulation stays enabled,
with six explicit exclusions: `http-backdoors-attempts`, `http-cve-probing`,
`thinkphp-cve-2018-20062`, `CVE-2017-9841`, `CVE-2022-41082`, and
`jira_cve-2021-26086` (all under `crowdsecurity/`). A single LAPI profile repeats
that allowlist and issues only 15-minute IP bans, without escalation or range
bans. Generic probing, crawling, sensitive-file, WordPress and authentication
scenarios remain simulated. AppSec and LAPI online/community API use remain
disabled.

Public Traefik loads `maxlerebourg/crowdsec-bouncer-traefik-plugin` v1.8.1 in
stream mode on the HTTPS entrypoint, including HTTP/3. It polls LAPI every ten
seconds, uses direct client addresses, trusts no forwarded-header sources and
allows unbanned traffic when LAPI is unavailable. Private Traefik and TCP mail
entrypoints are unchanged. Both sides of TCP/8080 access are restricted to
public Traefik pods and the LAPI pods. A dedicated OpenBao KV entry
`kv/crowdsec-bouncer` supplies the API key through External Secrets and a
read-only policy bound to `traefik/crowdsec-bouncer-vault-auth`. The middleware
reads the mounted key file; no key is embedded in a manifest.

Investigation on 2026-10-30: the Czech IPv6 address triggered generic rules
while accessing Hister document URLs, Karakeep navigation, Immich video segments
and Harbor image layers. These appear to be legitimate client activity; no
address-wide exception was added. Spotify `/.git/config`, `/.git/HEAD` and
`/config.prod.json` returned the exact homepage body. Harbor's Jira probe also
returned its exact homepage body; tested `.env` paths now return 418 from the
existing probe-blocking route. No exposed file was found in these checks;
historical response bodies were unavailable.

The approved rollout provisioned the dedicated OpenBao credential/policy/role,
registered the bouncer, created its resources, updated the pod configurations
and network policies, and temporarily paused Argo reconciliation on `crowdsec`,
`crowdsec-config`, `traefik` and `traefik-network-policy`. These four live-only
pauses remain necessary while Git still describes observation mode. Do not
commit or push without a separate request.
After the desired revision reaches Git, remove the live-only
`argocd.argoproj.io/skip-reconcile` annotations and verify all four applications
reconcile. Before calling enforcement complete, verify a controlled temporary
ban returns 403 on both public replicas, spoofed forwarded headers cannot bypass
it, removal/expiry restores access and ordinary public traffic still works.
Do not replay historical simulated alerts into real bans.

Live verification on 2026-10-30 passed on public replicas
`traefik-6bd598f5d8-jbf8j` and `traefik-6bd598f5d8-zp2nj`: requests through
individual pod tunnels returned 200 with valid public TLS certificates, 403
under a 45-second loopback-only ban, 403 despite a spoofed `X-Forwarded-For`,
and 200 again after natural expiry. A second temporary ban verified explicit
removal restores 200 on both replicas. Pod logs independently recorded these
200/403 transitions; both replicas were Ready with no error-level log entries.
The live LAPI profile issued a non-simulated ban with 14m59s remaining for a
controlled TEST-NET backdoor alert and issued no decision for a generic-probing
input. All synthetic test decisions and alerts were removed. Ordinary public
HTTPS requests to Spotify, Harbor, SSO, WordPress and Mastodon returned 200.
The agent parsed logs from both new public replicas. These checks exercise the
live ingress middleware and LAPI but do not constitute an outside-network
IPv4/IPv6 ban test or an end-to-end exploit-detection test from a public client.
The pinned plugin also passed isolated tests for ban expiry/removal, spoof
resistance and continued unbanned access during LAPI failure. Both charts
rendered successfully and 17 repository checks passed.
 Agents still download the Traefik
collection and dependencies from the Hub. Network policy permits DNS, public
HTTPS for Hub downloads, scoped agent-to-LAPI traffic, Kubernetes API access,
and Prometheus metric scraping. It exposes no public ingress.

`kv/crowdsec` holds stable LAPI/bootstrap registration secrets through External
Secrets; the chart does not regenerate them on every Argo render. The dedicated
OpenBao role is bound only to `crowdsec/vault-auth`.

After reconciliation:

```sh
kubectl logs -n crowdsec deployment/crowdsec-agent --tail=100
kubectl exec -n crowdsec deployment/crowdsec-agent -- cscli simulation status
kubectl exec -n crowdsec deployment/crowdsec-agent -- cscli metrics
kubectl exec -n crowdsec deployment/crowdsec-lapi -- cscli alerts list
kubectl exec -n crowdsec deployment/crowdsec-lapi -- cscli decisions list
```

Require evidence that both public Traefik replicas are being tailed, valid access
logs are parsed, and scenario counters/alerts respond to a controlled test.
Startup/non-access log lines may remain unparsed. Review source IP attribution
for both address families and observe false positives before considering
blocking. A healthy pod or an empty alert list alone does not establish that
acquisition works. Prometheus scrapes LAPI and agent metrics on TCP/6060 under
job `crowdsec`; confirm both targets are up.

## Production Mastodon media caching

The Souin fixture pilot is replaced by a dedicated NGINX 1.30.6 proxy, pinned by
image digest. The in-process Souin integration did not expose the storage limits
needed for production. `seaweedfs/media-cache.yaml` defines a ConfigMap, two
cache replicas, a ClusterIP Service, and Traefik ingress permission on TCP/8080.
The existing SeaweedFS intra-namespace and DNS policies cover origin access.

The existing IngressRoute and Middleware identities retain their historical
`mastodon-media-cache-pilot` names to update them in place: SeaweedFS automatic
pruning is disabled. They now route all GET/HEAD requests for
`s3.andreybondarenko.com/mastodon/` to the cache proxy. No LAN restriction or
pilot header is required. The legacy Middleware becomes a 64-request concurrency
limit per public Traefik replica. The route has sync wave 1, so cache Deployment
health gates the cutover. Normal S3 writes and other buckets retain the existing
S3 ingress. The original `/robots.txt` route is unchanged. The new media route
uses only its concurrency middleware; it does not add GeoIP enrichment.

Mastodon's `S3_ENDPOINT`, `S3_ALIAS_HOST`, S3 credentials, and media URLs are
unchanged. Anonymous GETs are cache candidates. Authorization, cookies, any
query string (including presigned S3 URLs), Range, conditional requests, and
HEAD bypass storage and go directly to S3 with their original Host and headers.

### Correctness and privacy

Before every cache-eligible GET, an uncached anonymous HEAD request checks the
current S3 object. A deleted object returns 404 and an inaccessible object
returns 403 even if both replicas have warm caches. Origin failures return 503;
there is no stale fallback. This also covers direct S3 mutations and media
cleanup, without depending on Mastodon callbacks or a purge fan-out job.

Cache keys include the current ETag, Last-Modified, Content-Type,
Content-Disposition, and Cache-Control. Thus replacements and metadata-only
changes select a different representation. Missing validators/length, private or
no-store/no-cache policies, Set-Cookie responses, and oversized objects bypass
storage. GET response metadata must match the HEAD result before storage, which
prevents caching a concurrent replacement under an obsolete validator. Native
NGINX handling of Cache-Control, Vary and Set-Cookie remains enabled.

Downstream responses use `Cache-Control: private, no-cache` (or `private,
no-store` when the origin says no-store), so an external shared cache cannot
skip the per-read permission check. Browsers can retain a body but must
revalidate it. Origin checks add a metadata round trip per eligible request;
this design saves repeated payload reads and transfer from SeaweedFS, rather
than removing all origin requests. Cached files may remain on local disk until
eviction, but revocation immediately prevents serving them.

### Bounds and availability

Each pod has a 512 MiB disk cache and 16 MiB shared key zone, inside a 768 MiB
ephemeral volume. Cached bodies must have known lengths strictly below
10,000,000 bytes. Larger/unknown-length media and ranges stream from the origin.
Non-cacheable buffering cannot spill to unbounded temporary files. Memory is
limited to 128 MiB and ephemeral storage to 1 GiB per pod. Cache contents are
rebuildable and are lost on restart. Idle entries expire after one hour;
Cache-Control controls freshness, with a ten-minute default for HTTP 200 when
no explicit origin freshness exists.

Rolling updates retain both available replicas until a replacement is ready.
There is no purge/admin endpoint. Availability depends on S3 metadata checks;
serving potentially revoked content during an origin outage is deliberately
excluded.

### Rollout and verification

Commit/push the production manifests and let Argo reconcile `seaweedfs` and the
public `traefik` plugin removal. The public Traefik release may restart to unload
Souin; its existing HA settings remain unchanged. The cache route switches only
after the proxy Deployment is healthy. This configuration is prepared in Git;
production activation and real-origin verification still require reconciliation.

`X-Media-Cache` reports HIT, MISS or BYPASS. Cache logs contain cache result,
status, origin-check status, bytes and duration; they omit request paths,
queries, cookies and credentials.

Use uniquely named synthetic objects under `/mastodon/cache-pilot/` for live
verification; that prefix now follows the ordinary production route. The
operator helper reads each cache pod directly through a loopback port-forward,
using a canonical Host header and never exposing object bodies or credentials:

```sh
python3 tools/check-mastodon-media-cache.py --path /mastodon/cache-pilot/fixture.txt
```

After warming both replicas, overwrite the same fixture with different bytes
and verify the new SHA256 without purging:

```sh
python3 tools/check-mastodon-media-cache.py --path /mastodon/cache-pilot/fixture.txt \
  --expect-body-sha256 <current-body-sha256>
```

Also warm and then revoke anonymous read permission at S3; require 403 from
both replicas using `--expect-private`. Warm and delete the fixture; require 404
from both using `--expect-missing`. No PURGE is needed or supported. Confirm
normal signed S3 reads/writes and existing Mastodon media delivery still work,
and remove only the synthetic fixtures afterward.

Behavior tests run the production configuration in two real NGINX processes
against an isolated mock S3 origin:

```sh
NGINX_BINARY=/path/to/nginx python3 -m unittest tests.test_media_cache_runtime
```

The binary needs the auth-request and rewrite modules. Eight tests cover warm
hits, deletion, ACL revocation, replacement, metadata-only changes, cache-policy
revocation, origin failure, all bypass classes, oversized/unknown responses,
Set-Cookie, concurrent changes and denial of admin/other-bucket paths. These
passed locally against NGINX 1.30.6; they are not a substitute for the real S3
rollout checks above.

## Validation and rollback

On 2026-10-29, isolated Traefik v3.7.16 processes loaded the pinned plugins.
A mock OIDC provider completed code flow and verified PKCE: the admin role
received 200 and a non-admin role received 403. Two independent cache instances
passed repeat-hit, Authorization/Cookie/Range bypass, signed-query bypass, and
origin deletion followed by per-instance purge tests. These are local behavior
tests, not a live rollout or a real Keycloak browser test.

Render the pinned charts, validate Kubernetes and installed CRD schemas, and run:

```sh
python3 -m unittest tests.test_traefik_security_plugins tests.test_argocd_projects \
  tests.test_traefik_ha tests.test_pod_security_namespace_labels \
  tests.test_cert_manager_migration tests.test_dual_stack_ingress \
  tests.test_monitoring_container_security tests.test_container_resource_policy
```

Rollback OIDC by removing only `traefik-admin-oidc@kubernetescrd` from the affected
ingress chains; retain LAN restrictions. To roll back media caching, point the existing media IngressRoute service back
to `s3:8333` before removing the proxy resources. Keep the media URL and origin
permissions unchanged. Do not reinstate the old Souin cache for production. To roll back CrowdSec enforcement, remove the public HTTPS entrypoint bouncer
middleware before stopping LAPI or retiring its credential. Keep the observer
and its simulation configuration if detection history is still wanted. Preserve its LAPI PVCs if observations are
needed; review Argo pruning before deleting the Application. Retain external
credentials until no workloads reference them, then retire only these dedicated
clients/roles/KV entries with operator authorization.

### Live pilot verification, 2026-10-29

Both CrowdSec sources parsed real public Traefik requests, global simulation was
enabled, and Prometheus reported both CrowdSec scrape targets up. A uniquely
named synthetic S3 fixture produced repeat hits with identical bodies on both
public Traefik replicas. After origin deletion, both replicas still served cached
copies; after per-replica purge, both returned 404. The fixture was removed.
The verification helper now sends the canonical Host header so ephemeral local
port-forward ports cannot create different cache keys between test runs. This verification applied to the original fixture pilot; production media
caching is defined separately above and needs a new post-reconciliation check.
