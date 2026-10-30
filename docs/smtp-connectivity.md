# Internal application SMTP connectivity

Mastodon (including Sidekiq), Bitwarden, Nextcloud web/background jobs and Synapse
keep `andreybondarenko.com:25` as their SMTP endpoint. Their pod `hostAliases`
resolve that hostname to the existing public-ingress LAN VIP `192.168.30.210`,
reserved in `traefik/values.yaml`. This avoids the failing public-address path
while retaining the hostname expected by the mail TLS certificate. No passwords,
authentication settings, certificate checks or relay restrictions are changed.

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
checks from its running pod and needs no change. Grafana SMTP is disabled.
WordPress has no installed SMTP plugin or sendmail binary, and its daily report
has `SEND_EMAIL=false`; it is deliberately not enabled by this change.

These repository changes have not been committed, pushed, or applied. Normal
Argo reconciliation must deploy the workload aliases and NetworkPolicies before
application connectivity can be confirmed. Relevant Applications are `mastodon`,
`mastodon-custom`, `bitwarden`, `nextcloud` and `element` (Synapse). Policies and
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
