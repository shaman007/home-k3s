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

## Personal email layout

Email uses `homelab.email.subject/text/html` from `alertmanager-templates`.
All authored email copy is English. Priority is first, followed by a readable event title and affected application,
namespace or node. Each grouped alert has its own outcome, local Prague timestamp
and ordered target fields. Routing metadata and links are omitted. HTML uses the
same content as text with automatic escaping; Telegram and routing are unchanged.
Audit notifications contain node/outcome aggregates, not event actors or Secret
names. The email states this limit explicitly rather than inventing attribution.
Other alerts retain their description and rule name; URLs are removed.

Validate locally with Alertmanager v0.35.1 `amtool`:

```sh
python3 -m unittest tests.test_alertmanager_email
```

Set `AMTOOL_BINARY` if the binary is outside PATH. Without it rendering tests skip;
that is not proof that templates parse. No mail is sent by these tests. After
publication, verify all three Alertmanager replicas reload and inspect the next
real email in text and HTML. A test notification requires separate authorization.

The `email-format-test` receiver matches only `NotificationEmailTest` with
`notification_test="true"`, groups by a unique `test_id`, and sends email only.
Use a short-lived synthetic alert after deployment only when the user authorizes
a test email. This prevents a mail layout check from also notifying Telegram.
