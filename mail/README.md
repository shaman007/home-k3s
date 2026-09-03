# TODO

* Harden authentication

## Manual spam training

Forward unwanted messages to `spam@andreybondarenko.com`. The
`rspamd-spam-trainer` CronJob runs at minute 7 of every hour, teaches each
message to Rspamd as spam, and removes it from the training mailbox only after
Rspamd accepts the learning request. A failed message remains in the mailbox
for the next run.

Forwarding the unwanted message as an attachment preserves its original
headers and gives Rspamd the best training sample. An ordinary inline forward
is also accepted, but includes the forwarding wrapper in the learned content.

Postfix delivers all other addresses at `andreybondarenko.com` to the `me`
mailbox. The explicit `spam@andreybondarenko.com` mapping takes precedence over
that domain catch-all.

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
