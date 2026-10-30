# Internal application SMTP connectivity

Mastodon (including Sidekiq), Bitwarden, Nextcloud web/background jobs, Synapse,
WordPress and Grafana
keep `andreybondarenko.com:25` as their SMTP endpoint. Their pod `hostAliases`
resolve that hostname to the existing public-ingress LAN VIP `192.168.30.210`,
reserved in `traefik/values.yaml`. This avoids the failing public-address path
while retaining the hostname expected by the mail TLS certificate. Existing passwords, authentication settings and relay restrictions are preserved.
New WordPress and Grafana SMTP transports require STARTTLS and certificate checks.

Each application has a dedicated `*-allow-egress-internal-smtp` NetworkPolicy
allowing TCP/25 only to public Traefik pods in the `traefik` namespace. Explicit
pod selectors are needed for service-translated traffic; existing IPv4 `ipBlock`
rules did not permit these connections in the observed Cilium runtime. Traefik
already accepts port 25 and forwards it with PROXY protocol to Postfix port 587.
Do not connect applications directly to that Postfix listener: it expects PROXY
protocol from Traefik.

Host aliases affect all connections to the exact hostname in these pods, including
HTTPS to the root site; subdomains are unaffected. Keep aliases aligned with the
reserved Traefik VIP if it changes. The aliases preserve existing app-managed
mail settings (Nextcloud config and Synapse's ExternalSecret included), so no
persistent application configuration or secret-store edit is needed.

## Validation and rollout

Local preparation on 2026-10-30 verified the pinned Mastodon chart (1.2.7), workload
and NetworkPolicy selectors, and SMTP routing manifests. A read-only connection
from the workstation to the LAN VIP on port 25 received SMTP/EHLO responses and
negotiated TLS 1.3 with certificate hostname verification for
`andreybondarenko.com`. No AUTH, MAIL FROM, RCPT TO or DATA commands were sent.

Alertmanager's existing internal route on port 587 also passed greeting/EHLO
checks from its running pod and needs no change.

WordPress now uses the mounted `internal-smtp.php` must-use plugin to configure
WordPress's bundled PHPMailer through `phpmailer_init`, avoiding its unavailable
sendmail binary. It uses `wordpress@andreybondarenko.com` as the sender.
Grafana SMTP is enabled with `grafana@andreybondarenko.com` as the sender and
`MandatoryStartTLS`. Existing alert rules and contact points are unchanged.

The WordPress daily report is enabled (`SEND_EMAIL=true`) with its existing
recipient `me@andreybondarenko.com`. It connects directly through the internal
Traefik DNS name, like the monitoring reports, with matching pod-based egress.
Its existing SMTP implementation does not authenticate or require STARTTLS.
The next normal scheduled run after deployment can send email; do not trigger
a manual run to test it.

New WordPress and Grafana mail transports use unauthenticated local delivery.
The existing Postfix configuration accepts recipients in `andreybondarenko.com`
and `shaman007.com`; relaying to other domains still requires SMTP credentials.
No relay access is broadened. External-recipient delivery would require a
separate authenticated SMTP configuration and is not enabled by these changes.
Other apps' existing email features remain configured; this change does not
create alert subscriptions or turn on Synapse's optional notification stream.

No live cluster changes were performed during this work. The initial four-app
repairs were included in local commit `7c5c4764` by a concurrent repository action;
the WordPress/Grafana additions remain in the worktree. At the last live check,
Argo Applications still reported revision `2ff670f9`, and the running affected
pods had no host aliases. Normal Argo reconciliation must deploy both workload
aliases and NetworkPolicies before application connectivity can be confirmed. Relevant Applications are `mastodon`,
`mastodon-custom`, `bitwarden`, `nextcloud`, `element` (Synapse), `wordpress`,
`grafana` and the existing monitoring NetworkPolicy application. Policies and
workload rollouts can reconcile independently; verify both before retesting.

After deployment, from each application container:

1. Confirm `andreybondarenko.com` resolves to `192.168.30.210`.
2. Open its configured SMTP connection with a bounded timeout; expect a 220
   greeting and a 250 EHLO response.
3. Where the app uses STARTTLS, verify the certificate against
   `andreybondarenko.com` and issue EHLO again, then QUIT.
4. Check Sidekiq logs for new SMTP connection errors. Normal queued mail may resume
   after deployment; do not enqueue test mail or rerun report Jobs for validation.

Without deployment, successful connection checks from the affected application
pods, authentication and message delivery remain unverified.

References: [WordPress SMTP hook](https://developer.wordpress.org/reference/hooks/phpmailer_init/)
and [Grafana SMTP settings](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/#smtp).
