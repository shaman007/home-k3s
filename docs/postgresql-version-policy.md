# PostgreSQL compatibility policy

Database image updates must preserve the on-disk major version until a separate
migration has been rehearsed and approved. A successful image pull or Kubernetes
schema check does not establish data-directory or extension compatibility.

The November 2026 migration targets are:

| Application | PostgreSQL ceiling | Required compatibility |
| --- | --- | --- |
| Keycloak | 18 | The official supported database matrix currently ends at 18. |
| Bitwarden Lite | 19 after verified cutover | Rehearse the current Lite application against its restored database. |
| Mastodon | 19 after verified cutover | Rehearse Rails and preserve pg_stat_statements. |
| Dawarich | 18 | Stable PostGIS image and successful spatial-data restore. |
| Immich | 18 | Published stable Immich image with compatible VectorChord and pgvector. |
| FerretDB | 17 | Published DocumentDB image paired with the FerretDB release. |

These are compatibility ceilings, not claims that every running database has
already reached them. The scoped rules in `renovate.json` are authoritative for
the currently approved data-directory major. Each cap advances in the same
change as its rehearsed migration and new data volume; supported but not yet
migrated majors remain blocked. Patch updates
within an approved major remain eligible; prereleases are excluded. FerretDB and
DocumentDB updates are grouped for review instead of automatically merged.

For a major migration, use a new PVC, restore a complete logical backup, verify
indexes and application behavior, quiesce every writer, take the final dump, and
only then switch the workload. Retain the previous PVC for rollback; a rollback
after new writes requires reconciling those writes, not blindly selecting the
old volume. Restore ordinary Argo reconciliation and backup coverage afterward.
Never initialize a newer server on the old data directory or reset WAL to make
an incompatible directory start.

A Codex reminder checks support on the 20th of each month at 10:00 Europe/Prague.
It is read-only: new upstream support is a proposal, not deployment approval.
Changing a ceiling requires reviewing application support, stable image tags,
extension availability, migration instructions and a tested restore.

Primary references:

- [PostgreSQL major upgrades](https://www.postgresql.org/docs/current/upgrading.html)
- [Keycloak supported configurations](https://www.keycloak.org/server/supported-configurations)
- [Bitwarden Lite deployment](https://bitwarden.com/help/install-and-deploy-lite/)
- [Immich PostgreSQL requirements](https://docs.immich.app/administration/postgres-standalone/)
- [PostGIS image releases](https://github.com/postgis/docker-postgis)
- [FerretDB DocumentDB images](https://docs.ferretdb.io/installation/documentdb/docker/)
