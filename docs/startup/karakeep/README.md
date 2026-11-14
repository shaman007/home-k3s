# Karakeep startup and separate Chrome

Deployed and verified on 2026-11-14. The whole worker pool waits for Chrome and
Meilisearch; Chrome runs in a separate Pod.

## Dependencies and readiness

```mermaid
flowchart LR
  Storage[Longhorn / PVC] --> SQLite[SQLite migration]
  SQLite --> Web[web / UI]
  SQLite --> Gate[s6 worker gate]
  Chrome[Chrome Deployment: CDP discovery] --> Gate
  Meili[Meilisearch: health available] --> Gate
  Gate --> Workers[all background workers]
```

Chrome uses the existing exact image, arguments, UID 65534, capability drop,
read-only root and temporary-volume limits. Its upstream entrypoint forwards
9222 through socat to Chrome on localhost:9223. It already supports remote
connections; Karakeep 0.34.1 resolves the browser hostname before Patchright CDP.
Local testing with two separate containers proved CDP and synthetic DOM access.
No upgrade, custom browser image or extra proxy is required.

The new ClusterIP Service is `chrome.karakeep.svc.cluster.local:9222`.
Default deny remains effective; new paired NetworkPolicies permit CDP only
from `app=karakeep` to `app=karakeep-chrome` in this namespace. Chrome inherits
existing namespace DNS and HTTP/HTTPS egress, but receives no Karakeep Secrets,
PVC, service-account token, ingress, public VIP or route. The web Service selector
cannot select the browser Pod.

The gate replaces only `/etc/s6-overlay/s6-rc.d/svc-workers/run` with an immutable
versioned ConfigMap. The upstream entrypoint, migration dependency and web runner
remain intact. It checks Chrome `/json/version` and nonempty debugger URL plus
Meilisearch `/health` JSON `status=available`, using bounded parallel HTTP requests
and a five-minute wait budget. On expiry it exits 75; s6 retries only workers.
On readiness it execves the original worker process, preserving signals.

All crawler/search/inference/other workers wait together. Ollama and Keycloak
are not unconditional startup gates: they serve AI and login respectively.
SQLite migration readiness belongs to existing s6 ordering, not a separate DB
Deployment. There is no dependency from Chrome/Meili back to workers or web.
After startup, existing application reconnection/retry handles provider loss;
this gate does not continuously stop already-running workers.

## Local validation

* Native HTTP unit cases cover wrong status/JSON, redirects and stalled replies.
* `python3 tools/security/test_karakeep_worker_startup.py` uses the production
  Karakeep image, no network uplink, empty disposable SQLite and fake providers.
  Migrations/web run with providers down; Chrome alone cannot release workers;
  both providers release the real worker executable. Graceful s6 stop passes.
* `python3 tools/security/test_karakeep_remote_chrome.py` uses both declared images
  in a private no-uplink Podman network. The actual Patchright client connects
  remotely, creates a synthetic page, reads its title and disconnects.
* Manifest tests cover canonical script projection, distinct Service selectors,
  same-namespace policy peers, port restriction and browser separation.

Requires Podman, Python/PyYAML and existing registry access to the declared
images. These opt-in integration scripts create/remove only their own local
containers, temporary files and network. They never use production Secrets/data.
Cluster DNS, policy reachability, browser temporary paths and a real synthetic
bookmark crawl were verified after deployment (see runtime acceptance below).

## Transition

1. Before publication retain the current Git revision (`c12103fd`) as rollback
   reference. No database changes or task requeue are required.
2. Publication permits ordinary Argo reconciliation. Before the authorized
   rollout, create short, narrowly scoped maintenance silences for affected
   Karakeep/Chrome Pod alerts only, recording IDs/expiry; remove after checks.
3. Argo creates the Chrome Deployment/Service/policies and replaces the Karakeep
   Pod using its existing Recreate strategy. Brief UI interruption is expected.
   Resource ordering is safe even if web starts first: only workers wait.
4. Verify Chrome startup/readiness, writable temporary paths, Service endpoints,
   namespace policy reachability and CDP from web. Check Meili readiness.
5. Confirm logs show migration completion, then worker dependency `ready`, then
   workers. Confirm UI, SSO, existing bookmark/search and a user-authorized
   synthetic bookmark crawl, screenshot/PDF/archive. Do not mutate existing
   bookmarks merely for verification.
6. Verify Argo Synced/Healthy, zero recurring gate failures, no new alerts and
   remove maintenance silences. Do not treat Pod Ready alone as functional proof.

## Rollback

Prepare a focused Git revert of only this Karakeep package and publish through
the usual user push. Restore the old sidecar, writable-path init mounts, localhost
BROWSER_WEB_URL, original s6 worker runner and volumes together. The web Deployment
uses Recreate; do not run two writers against its SQLite PVC. Keep all Secrets,
PVCs, bookmarks and Meili data. Do not roll back unrelated later changes.

First restore and verify the sidecar-based Pod. Then explicitly remove only the
now-unused separate browser Deployment/Service/policies and gate ConfigMap if
necessary: this Argo Application does not enable automatic prune. Their temporary
continued existence does not receive traffic after localhost is restored.
Never delete old projected ConfigMaps until no running Pod references them.

## Post-publication CDP discovery correction

On 2034b16d the separate Chrome and web Pods became Healthy, but workers stayed
in the gate: Chrome rejected discovery with a DNS Service name in the HTTP Host
header. The real crawler resolves the name to an IP first, so its isolated CDP
check passed; the initial fake-provider test did not reproduce this restriction.
The gate now sets `Host: localhost` only for CDP discovery using Node http.get.
Both the HTTP regression and full s6 fake provider enforce this restriction.
A read-only request using the same HTTP API confirmed valid debugger JSON over
the real Service. The fixed immutable ConfigMap and Deployment reference were published and
reconciled; live worker gate release was verified.

## Runtime recovery acceptance — 2026-11-14

* Restarted only the separate Chrome Pod. The existing application worker
  reconnected to the replacement through CDP in approximately ten seconds, after
  two transient connection errors. The Karakeep Pod and worker process did not
  restart. An application-owned established socket confirmed the new backend.
* Recreated only `meilisearch-0`, retaining `meili-data`. It became Ready on a
  different node; all 396 bookmark documents and 394 vector documents survived.
  Karakeep web/health stayed available and its worker process did not restart.
* After both recoveries, a synthetic public-page bookmark completed remote
  Chrome crawling, reader content, PDF/screenshot capture and full-page archive
  attachment, AI summary/tags, embedding and indexing. Its unique title appeared
  in the authenticated user search as well as a read-only Meilisearch query.
  Attachment links and capture logs were checked; downloaded file integrity was
  not independently tested.
* Deleted only that synthetic bookmark through the normal UI with explicit user
  confirmation. Search became empty, its index document returned 404, and index
  counts returned to 396/394. Existing bookmarks were not changed.
* Removed the narrowly scoped maintenance silences. Final Argo report passed
  95/95 applications; the Prometheus alert inventory was empty.

These checks establish recovery and processing of new work after dependency
replacement. They do not establish retry semantics for a job interrupted during
its crawl/index write, prolonged simultaneous outages, or Ollama/SSO failure.
The startup gate remains a startup check, not continuous worker suspension.
