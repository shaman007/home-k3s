# TODO

* Harden authentication

## Rspamd Valkey

Rspamd stores learned and operational Redis-protocol data in the
`valkey.mail.svc.cluster.local:6379` service. The Valkey StatefulSet and its
dedicated `valkey-mail-lh` PVC are defined in:

* `mail/stateful-set-valkey.yaml`
* `mail/persistent-volume-claim-valkey-mail-lh.yaml`

Unlike the cache and queue cutovers, the Rspamd dataset was preserved when the
old Redis instance was replaced. Valkey runs with AOF enabled and an RDB save
policy of one change per 60 seconds. The PVC uses Longhorn's
`backup-daily-retain31-c` and `trim-daily-c` recurring jobs.

Do not remove a retained Redis volume until Valkey reports healthy AOF/RDB
persistence, Rspamd is reading the migrated keys, and the replacement volume
has completed at least one Longhorn backup. See
`docs/valkey-cutover.md` for the verification and cleanup procedure.
