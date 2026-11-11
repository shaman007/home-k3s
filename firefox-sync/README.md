# Firefox Sync

Self-hosted Syncstorage and Tokenserver, with Mozilla accounts for sign-in.
This syncs Firefox-supported data (bookmarks, history, passwords, tabs, add-ons,
and selected settings), rather than cloning an entire profile directory.

Status: initially deployed on 2026-11-03; migrated live to MariaDB 12.3.3 LTS on
2026-11-09. MariaDB and Sync are Ready; the active Longhorn volume is healthy
with two replicas. During the initial live migration, Firefox Sync alone was
held with `argocd.argoproj.io/skip-reconcile=true` until the final MariaDB
manifests were published. Remove that temporary guard only after publication
and verify actual Argo Synced/Healthy adoption; cached status while skipped
is not reconciliation proof. Parent Argo auto-sync uses its original policy.

OpenBao SecretStore and ExternalSecret are Ready. Both database schemas and the
public tokenserver node are initialized. Public DNS resolves, the certificate is
Ready, and public HTTPS certificate validation succeeds. Health endpoints return
200 and unauthenticated token requests return 401. An authenticated synthetic
storage write/read/cleanup passed through the public HTTPS ingress with certificate
validation enabled. The app can reach Mozilla OAuth keys over trusted HTTPS.
Initial MySQL-era Firefox verification completed: the user reported successful synchronization
between two isolated test profiles. Server-side checks confirmed one enrolled
Mozilla account, two client records, two tab records, and 45 bookmark records.
Record payloads and account identifiers were not inspected. The normal desktop
Firefox profile was not modified.

The active volume has daily filesystem trim and the Longhorn
`backup-daily-retain31-b` backup assignment (02:05 UTC daily, 31 retained copies).
Both the verification backup and the scheduled 2026-11-10 backup completed.
The retained original MySQL PVC is protected against Argo pruning.
Its pre-migration snapshot was backed up to the existing SeaweedFS target; a
physical backup restore has not been tested.

MariaDB migration procedure and [execution results](../docs/migrations/firefox-sync-mariadb/EXECUTION.md): see
[the compatibility assessment and cutover runbook](../docs/migrations/firefox-sync-mariadb/README.md).
All 10 imported tables matched by count and SHA-256 value fingerprints. Fresh
migrations and two Hawk API clients passed write/read, batch staging/commit,
timestamp and cleanup checks on isolated MariaDB and public production HTTPS.
The user will verify actual Firefox sign-in and cross-profile sync separately.

## Deployment prerequisites

- Create DNS `sync.andreybondarenko.com` pointing to the same ingress endpoint as
  `keep.andreybondarenko.com` (observed IPv4: `81.19.4.105`; verify before changing).
- After explicit approval, run `python3 tools/firefox-sync/bootstrap_secrets.py --execute`.
  It generates four independent secrets directly in OpenBao, preserves an existing
  complete secret, and grants only the dedicated namespace access. No secret files
  or values are printed. Passwords are hexadecimal, suitable for database URLs.
- Publish these manifests through the repository's authorized GitOps process.
  This includes `namespaces/namespaces.yaml`, the `applications` AppProject destination,
  `argocd/application-firefox-sync.yaml`, the `firefox-sync` directory, and
  `traefik/network-policy-traefik-allow-egress-firefox-sync.yaml`.
  Live bootstrap alone does not establish GitOps reconciliation; the Argo
  Application must not be created before its source is published. This deployment
  has now been published and adopted by Argo CD.
- For an approved live bootstrap before publication, create the namespace first,
  then create the resources in this directory using `kubectl create -f firefox-sync/`,
  plus the dedicated Traefik egress policy above (required for API and ACME traffic).
  Do not create the auto-syncing Argo Application until its source is published;
  unpublished source cannot provide GitOps reconciliation.

The dedicated MariaDB 12.3.3 instance uses a 5 GiB Longhorn `mariadb-data` PVC.
The old MySQL Deployment and `mysql-data` PVC are retired.
Never attach a MySQL datadir to MariaDB. Both database schemas
and the non-root app user are initialized automatically. Sync migrations and the
public node URL are initialized by the pinned Mozilla server. Database credentials
are initialization values: changing OpenBao passwords alone does not rotate database
users. Preserve the PVC and OpenBao secret together; restore both for recovery.
Include the active database in the existing backup process before treating this as durable storage.
The app needs outbound HTTPS for Mozilla OAuth, plus DNS and MySQL access.

## Verify

Check ExternalSecret Ready, bound PVC, both Deployments ready, successful schema
migration logs, and Certificate Ready. Verify HTTPS `/__heartbeat__` and
`/__lbheartbeat__`. An unauthenticated request to `/1.0/sync/1.5` should be rejected.
`tools/firefox-sync/verify_storage.py` performs a synthetic Hawk-authenticated
write/read/cleanup against a local-only port-forward on port 18000, or the public
endpoint with `--url https://sync.andreybondarenko.com` (trusted HTTPS required). It reads the
master secret in memory without printing it. It does not verify Mozilla OAuth.
Both verification and secret bootstrap reject redirects, including redirects
within the same service. Each request must stay on its configured origin;
bootstrap uses only the reviewed OpenBao HTTPS endpoint, and verification uses
only the reviewed public HTTPS endpoint or a loopback HTTP tunnel. HTTP failures
are closed and reported without response bodies or credential material.
Then use two Firefox clients to sync a test bookmark and verify it appears on the
second client. Health checks alone do not establish end-to-end sync.

## Client setup

In desktop Firefox `about:config`, set `identity.sync.tokenserver.uri` to:

```
https://sync.andreybondarenko.com/1.0/sync/1.5
```

Restart Firefox, sign in using a Mozilla account, and inspect `about:sync-log`.
Back up your profile before changing an existing Sync configuration.
For Android, enable the debug settings by tapping the logo six times under
Settings > About Firefox, then set the custom Sync server under Sync Debug and
stop/restart Firefox. Client configuration has not been changed by this task.

The default tokenserver permits new valid Mozilla accounts. This service is not
an account allowlist. Once intended users have signed in, the supported
`SYNC_TOKENSERVER__ALLOW_NEW_USERS=false` setting can close new enrollment (verify
availability in the pinned release before enabling). Do not add browser-based
OIDC middleware in front of the Sync API; clients use native protocol authentication.

## Fully self-hosted accounts assessment

The upstream FxA README points to a source-built development setup using Node,
Yarn, PM2, MySQL, Redis, and Memcached. The upstream self-hosting guide describes
itself as preliminary and incomplete. No accounts stack was deployed or runtime
failure established. Under the current prohibition on Docker builds/runs, this
route could not be tested; the user authorized the Mozilla-account fallback.

Sources:
- https://mozilla-services.github.io/syncstorage-rs/how-to/how-to-run-with-docker.html
- https://github.com/mozilla-services/syncstorage-rs/tree/0.24.0
- https://mozilla.github.io/ecosystem-platform/tutorials/development-setup
- https://mozilla-services.readthedocs.io/en/latest/howtos/run-fxa.html
