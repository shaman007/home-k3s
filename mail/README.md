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

## Secondary MX

`backup.andreybondarenko.com` (157.180.125.24) is the secondary MX only for
`andreybondarenko.com`: primary preference 0, secondary preference 20 (TTL 600).
DNS source is `/home/shaman007/git/dns/zones/andreybondarenko.com.json`; remote
Postfix/native nginx/Certbot configuration and restore scripts are in
`/home/shaman007/git/dotfiles/hosts/backup-mx/`. These directories belong to their
own repositories and are not deployed by this mail Argo application.

The backup accepts all local parts for this domain to match the primary's
catch-all. It rejects other domains and subdomains, requires authenticated TLS
when relaying directly to `[81.19.4.105]:25`, and retains queued mail for seven
days. SMTP AUTH and unrestricted relay are disabled. This is an SMTP queue,
not a mailbox backup; keep its disk space and delivery backlog monitored.

Rspamd's `external_relay` configuration trusts only 157.180.125.24/32 and derives
the original SMTP client from the Received header inserted by that backup.
SPF/RBL and other antispam checks then use the original client; mail from this
IP is not exempted from filtering. Do not grant this backup unrestricted relay
in Postfix `mynetworks`, or whitelist all its messages in Rspamd.

On 2026-11-12, the ConfigMap/Deployment changes here were patched into the live
Rspamd after user approval. The `mail` application is paused with the live-only
annotation `argocd.argoproj.io/skip-reconcile: "true"` until these changes are
published to its tracked Git branch. Removing `spec.syncPolicy.automated` alone
was insufficient: its parent `argocd-applications` restored that spec from Git.
Only mail reconciliation is paused; its reported Argo status is stale during
this pause, so inspect workloads directly. The normal automated policy remains
`prune: true`, `selfHeal: true` in the Application manifest.

After publishing the trusted-relay changes to main, remove the pause annotation
with `kubectl annotate application mail -n argocd argocd.argoproj.io/skip-reconcile-`,
then review/verify the application Healthy/Synced and verify Rspamd's loaded
external_relay configuration. Do not remove the pause before publication:
self-healing would undo the trusted-relay configuration. This recovery command
changes live state and requires task authorization.

Validation included strict Kubernetes schemas and Rspamd configtest/configdump,
public STARTTLS and rejected foreign-domain/subdomain RCPTs, a controlled relay
pause proving durable queueing, and delivery of the same unique test Message-ID
into the primary Dovecot INBOX after resuming relay. An initial greylist response
was retried; the backup queue drained. No actual primary outage or host reboot
was performed for this test.
