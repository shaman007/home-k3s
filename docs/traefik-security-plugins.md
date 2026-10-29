# Private console login, CrowdSec observation, and Mastodon cache pilot

## Scope and rollout status

This change adds Keycloak OIDC to private infrastructure consoles, introduces
CrowdSec in simulation mode, and prepares an opt-in cache for disposable Mastodon
media fixtures. Sablier remains deferred.

External prerequisites were provisioned on 2026-10-29: the `traefik-admin`
Keycloak client, its realm-role ID-token mapper, and the two dedicated OpenBao KV
entries, read policies, and namespace/service-account-bound Kubernetes auth roles.
No secret values are in this repository. Kubernetes manifests must still be
committed/pushed by the operator and reconciled through Argo CD. Do not call the
rollout complete until the runtime checks below pass.

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

DNS checked on 2026-10-29: `thanos.w386.k8s.my.lan` resolves to `192.168.30.211`.
**Add LAN DNS records for `thanos-compactor.w386.k8s.my.lan` and
`thanos-store.w386.k8s.my.lan`, both pointing to `192.168.30.211`, before validating
those consoles.** These records are managed outside this repository. The new
Certificates use the existing `vault-acme` ClusterIssuer.

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

Global simulation is enabled with no exclusions. No Traefik bouncer or firewall
remediation is deployed, and AppSec is disabled. LAPI online/community API use
is disabled for this observation phase. Agents still download the Traefik
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

## Mastodon media-cache pilot

Souin v1.7.8 is loaded by public Traefik. The pilot route requires all of:

- Host `s3.andreybondarenko.com`.
- A LAN/WireGuard client address, or loopback for operator port-forward checks.
- Header `X-Mastodon-Cache-Pilot: 1`.
- A GET/HEAD for a disposable `/mastodon/cache-pilot/` object, or a PURGE to the
  exact `/souin-api/__mastodon_cache_pilot/flush` endpoint.
- No Authorization, Cookie, or Range header.

Query-bearing media requests bypass caching. The default for responses without
an explicit cache policy is `no-store`; stale serving is disabled. Fixtures
should be small and explicitly carry `Cache-Control: public, max-age=30`.
Do not place actual user media in the pilot prefix. Keep pilot fixtures
non-sensitive: the Souin administrative API dispatches by URI substring.

The normal S3 ingress, other buckets, writes, signed requests, and production
Mastodon media URLs retain their existing behavior. Neither `S3_ENDPOINT` nor
`S3_ALIAS_HOST` changes. This pilot does not accelerate federation yet.

Caches are local to each Traefik process. **A load-balanced PURGE is insufficient**:
the operator helper enumerates all running public Traefik pods and opens a
loopback, certificate-verified TLS port-forward to each pod:

```sh
python3 tools/check-mastodon-cache-pilot.py
python3 tools/check-mastodon-cache-pilot.py --purge
```

Provision only a disposable `mastodon/cache-pilot/fixture.txt` object using the
existing authenticated S3 workflow. The helper does not create or delete S3
objects. After warming every replica, delete that fixture at the origin, then:

```sh
python3 tools/check-mastodon-cache-pilot.py --purge --expect-missing
```

Every replica must return 403 or 404 after purge. The helper never prints body
contents or S3 credentials. It verifies identical bodies and repeat cache hits.
Use access logs and origin read counts/latency to measure value before expanding
the route. Monitor Traefik memory: the pilot has no aggregate cache-memory cap.

Before production media caching, implement and test automatic invalidation from
Mastodon deletion, suspension/ACL changes, media cleanup and direct object
changes, with purge fan-out to every replica and fail/retry behavior. Mastodon's
cache-buster hooks can help, but do not cover arbitrary direct S3 mutations.
Do not widen the fixture route merely because cache-hit tests pass.

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
ingress chains; retain LAN restrictions. Remove the pilot IngressRoute before
removing its plugin registration. CrowdSec can be stopped independently because
it has no enforcement component. Preserve its LAPI PVCs if observations are
needed; review Argo pruning before deleting the Application. Retain external
credentials until no workloads reference them, then retire only these dedicated
clients/roles/KV entries with operator authorization.
