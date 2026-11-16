# PVC maintenance audit — 2026-11-16

Live audit following OpenBao recovery. Times below use Europe/Prague.

- All 73 Longhorn filesystem PVCs have assignments resolving to existing trim jobs. The two local-path HDD PVCs (Immich library and Plex library) have existing approved unsupported-discard exceptions.
- Daily trim CronJobs completed successfully; current hourly/15-minute jobs select zero volumes. The current volume labels mostly select daily trim. Old daily job Pods/logs are no longer available, so schedule success is not proof of bytes reclaimed on every filesystem.
- 37 volumes have an explicit recurring backup assignment: 34 have completed backups from this morning (14–16 hours old). The three new OpenBao volumes were created afterward and have not had their first Longhorn backup. Their next daily run is 2026-11-17 04:05 Prague time. A verified encrypted OpenBao Raft snapshot exists separately.
- 36 Longhorn volumes have no recurring backup assignment. This includes caches and also WordPress MariaDB, Harbor registry and Dawarich storage/public. Existing snapshots are not external backups. This audit did not add policies or establish that other application-specific/off-cluster backups cover these volumes.
- Talos etcd backup scheduler is active and recently succeeded. Backup metadata checks do not prove restoreability; no new restore drill was performed in this audit.

## Alert diagnosis

All eight active `KubePodNotReady` alerts checked at this audit referred to Succeeded pods from the maintenance/reboot (Longhorn, MetalLB, Hubble and NVIDIA validation). The rule excludes Job owners and deleting pods but does not exclude terminal Succeeded pods owned by ReplicaSets or other controllers. Their replacements are healthy. This is a rule-filtering defect; no alert rules were changed or silenced in this follow-up.

## Longhorn inventory

An empty backup timestamp means no completed backup is recorded on that volume; an old timestamp without a current backup assignment does not establish current protection.

| PVC | Trim assignment | Backup assignment | Last backup (Prague) |
| --- | --- | --- | --- |
| aiy-voice/aiy-voice-usage | trim-daily-a | **none** | — |
| backup-rsync/backup-rsync-host-keys | trim-daily-a | **none** | — |
| bastioncam/bastioncam-data | trim-daily-a | backup-daily-retain31-c | 2026-11-16 04:05 |
| bitwarden/data-bitwarden-postgres-lh | trim-daily-a | backup-daily-retain31-a | 2026-11-16 02:05 |
| bitwarden/data-lh | trim-daily-a | backup-daily-retain31-b | 2026-11-16 03:05 |
| bitwarden/keys-lh | trim-daily-a | backup-daily-retain31-c | 2026-11-16 04:06 |
| clamav/avdata | trim-daily-a | **none** | — |
| comfyui/comfyui-data-v2 | trim-daily-a | **none** | — |
| convertx/convertx-data | trim-daily-a | **none** | — |
| crowdsec/crowdsec-config-pvc | trim-daily-a | **none** | — |
| crowdsec/crowdsec-db-pvc | trim-daily-a | **none** | — |
| dawarich/data-dawarich-postgres-lh | trim-daily-a | backup-daily-retain31-a | 2026-11-16 02:05 |
| dawarich/data-valkey-dawarich-0 | trim-daily-a | **none** | — |
| dawarich/photon-data | trim-daily-a | **none** | — |
| dawarich/public | trim-daily-a | **none** | 2026-05-13 14:25 |
| dawarich/storage | trim-daily-a | **none** | 2026-05-13 14:24 |
| dawarich/watched | trim-daily-a | backup-daily-retain30 | 2026-11-16 03:35 |
| firefox-sync/mariadb-data | trim-daily-a | backup-daily-retain31-b | 2026-11-16 03:05 |
| harbor/data-harbor-redis-0 | trim-daily-a | **none** | 2026-05-13 14:24 |
| harbor/data-harbor-trivy-0 | trim-daily-a | **none** | — |
| harbor/database-data-harbor-database-0 | trim-daily-b | backup-daily-retain31-b | 2026-11-16 03:06 |
| harbor/harbor-jobservice | trim-daily-a | **none** | 2026-05-13 14:25 |
| harbor/harbor-registry | trim-daily-a | **none** | — |
| hister/hister-data | trim-daily-a | backup-daily-retain31-c, backup-monthly-retain60-hister | 2026-11-16 04:06 |
| i2pd/i2pd-data | trim-daily-a | **none** | — |
| immich/data-immich-postgres16-lh | trim-daily-c | backup-daily-retain31-a | 2026-11-16 02:05 |
| immich/immich-ml-cache-lh | trim-daily-a | backup-daily-retain31-c | 2026-11-16 04:05 |
| immich/immich-valkey-lh | trim-daily-a | backup-daily-retain11 | 2026-11-16 02:20 |
| karakeep/karakeep-data | trim-daily-a | backup-daily-retain30 | 2026-11-16 03:35 |
| karakeep/meili-data | trim-daily-a | **none** | 2026-10-27 15:57 |
| keycloak/data-keycloak-postgres-lh | trim-daily-a | backup-daily-retain31-a | 2026-11-16 02:05 |
| lenka/mysql-pv-claim | trim-daily-a | backup-daily-retain30 | 2026-11-16 03:35 |
| loki/storage-loki-0 | trim-daily-a | **none** | — |
| mail/mail-lh | trim-daily-a | backup-daily-retain31-b | 2026-11-16 03:05 |
| mail/queue-lh | trim-daily-a | **none** | — |
| mail/rspamd-local | trim-daily-a | backup-daily-retain31-a | 2026-11-16 02:05 |
| mail/valkey-mail-lh | trim-daily-c | backup-daily-retain31-c | 2026-11-16 04:05 |
| mastodon/data-mastodon-postgres-v2 | trim-daily-b | backup-daily-retain1 | 2026-11-16 02:35 |
| mastodon/data-valkey-0 | trim-daily-a | **none** | — |
| matrix/matrix-lh-v2 | trim-daily-a | backup-daily-retain31-b | 2026-11-16 03:05 |
| mempalace/mempalace-data | trim-daily-a | backup-daily-retain31-b, backup-monthly-retain60-mempalace | 2026-11-16 03:05 |
| minecraft/minecraft1-lh | trim-daily-a | backup-daily-retain31-c | 2026-11-16 04:06 |
| monitoring/compactor-lh | trim-daily-a | **none** | 2026-05-13 14:25 |
| monitoring/data-thanos-receive-0 | trim-daily-a | **none** | — |
| monitoring/grafana-pvc | trim-daily-a | backup-daily-retain31-a | 2026-11-16 02:05 |
| monitoring/prometheus-lh | trim-daily-a | **none** | — |
| monitoring/storagegw-lh | trim-daily-a | **none** | 2026-05-13 14:24 |
| nextcloud/data-valkey-0 | trim-daily-a | **none** | — |
| nextcloud/mariadb-nextcloud-lh | trim-daily-a | backup-daily-retain31-b | 2026-11-16 03:05 |
| nextcloud/nextcloud-lh-120gi | trim-daily-a | backup-daily-retain31-c | 2026-11-16 04:05 |
| nllb/nllb-model-cache | trim-daily-a | **none** | — |
| ollama/ollama-data-lh | trim-daily-a | **none** | — |
| ollama/ollama-small-data | trim-daily-a | **none** | — |
| ooni/ooniprobe-data | trim-daily-a | backup-daily-retain31-c | 2026-11-16 04:05 |
| open-terminal/open-terminal-data | trim-daily-a | backup-daily-retain31-c | 2026-11-16 04:05 |
| open-webui/open-webui-data | trim-daily-a | backup-daily-retain11 | 2026-11-16 02:20 |
| openbao/data-openbao-0 | trim-daily-c | backup-daily-retain31-c | 2026-11-16 04:05 |
| openbao/data-openbao-1 | trim-daily-c | backup-daily-retain31-c | 2026-11-16 04:05 |
| openbao/data-openbao-2 | trim-daily-c | backup-daily-retain31-c | 2026-11-16 04:06 |
| openbao/data-openbao-20261116-0 | trim-daily-c | backup-daily-retain31-c | — |
| openbao/data-openbao-20261116-1 | trim-daily-c | backup-daily-retain31-c | — |
| openbao/data-openbao-20261116-2 | trim-daily-c | backup-daily-retain31-c | — |
| opensearch/opensearch-data-opensearch-0 | trim-daily-a | **none** | — |
| plex/plex-conf-lh3 | trim-daily-a | backup-daily-retain31-b | 2026-11-16 03:05 |
| ripe-atlas/ripe-atlas-config | trim-daily-a | **none** | — |
| ripe-atlas/ripe-atlas-spool | trim-daily-a | **none** | — |
| spotify/ferretdb-postgres-lh | trim-daily-a | backup-daily-retain31-c | 2026-11-16 04:06 |
| stirling-pdf/stirling-pdf-configs | trim-daily-a | **none** | 2026-05-13 14:25 |
| stirling-pdf/stirling-pdf-storage | trim-daily-a | **none** | — |
| traefik/traefik-geoip-rwx | trim-daily-a | **none** | 2026-11-13 21:29 |
| wordpress/data-valkey-0 | trim-daily-a | **none** | — |
| wordpress/mariadb-wordpress-lh | trim-daily-a | **none** | — |
| wordpress/wordpress-lh | trim-daily-a | backup-daily-retain31-a | 2026-11-16 02:05 |

## User-approved follow-up

The user requested review before changing the general backup policy, then
explicitly approved these four additions only. The other previously unassigned
PVCs were judged unimportant by the user; no policy was added to them.

| PVC | Daily job | Schedule (Europe/Prague, winter) | Immediate backup |
| --- | --- | --- | --- |
| wordpress/mariadb-wordpress-lh | backup-daily-retain31-a | 02:05 | Completed 2026-11-16 18:52; backup-1655f50019354ae7 |
| dawarich/storage | backup-daily-retain31-b | 03:05 | Not requested |
| convertx/convertx-data | backup-daily-retain31-a | 02:05 | Not requested |
| comfyui/comfyui-data-v2 | backup-daily-retain31-c | 04:05 | Not requested |

All four retain 31 scheduled copies. Existing trim and snapshot assignments
were preserved. PVC source labels and the corresponding Longhorn volume
assignments were verified. The WordPress first backup used a temporary,
single-volume RecurringJob; its definition, temporary selectors and execution
Jobs were removed after completion. The completed backup remains in the
backup target. That manual recovery point is separate from the scheduled
job's retention set. This is a live database volume snapshot, not a tested
application-consistent SQL restore. No database outage or restore drill was
performed. Policies were also added to the owning manifests; source publication
is a separate user action. The originally requested OpenBao immediate backups
and alert-rule changes were cancelled before execution and remain unchanged.
