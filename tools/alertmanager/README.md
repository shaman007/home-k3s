# Alertmanager Telegram delivery

Alertmanager duplicates email notifications to the Telegram destination stored
in OpenBao. Critical alerts retain
30-minute repeats; other alerts retain four-hour repeats. Resolved notifications
remain disabled for both integrations.

The ExternalSecret reads `kv/telegram`, properties `token` and `id`, through
the existing monitoring SecretStore. Store the numeric destination ID as `id`.
Both values are mounted read-only and read through Alertmanager file settings;
neither value nor the bot username is included in Git. The `bot_name` property
can be maintained in OpenBao for reference; Alertmanager does not require it.

Before deploying, merge `monitoring-telegram-policy.hcl` into the existing OpenBao
`monitoring` policy, preserving its current rules. This requires approval for the
live policy change. The current policy only permits `kv/monitoring`.

Deploy the monitoring network policy and ExternalSecret, verify the Secret is
ready, then roll out Alertmanager. Verify all three replicas are ready, config
reload succeeds, and an alert arrives in both email and Telegram. A direct bot
message alone does not validate Alertmanager delivery. No live deployment or
policy change has been performed as part of preparing these manifests.
