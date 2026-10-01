# Orange Pi daily network report

The Orange Pi runs `/usr/local/sbin/network-daily-report`, maintained in
`tools/network-daily-report.py`. Its systemd timer schedules 08:00 Europe/Prague
with catch-up after downtime. Input is the last 24 hours of retained Suricata
EVE JSON, including rotated gzip files. Outputs and configuration are under
`/var/lib/network-daily-report` on NVMe. The report is sent to the configured
recipient using STARTTLS on the existing mail server.

Evidence is aggregated by client IP, with top DNS/TLS/QUIC names, destination
IPs, protocols and alert signatures. Full aggregated evidence is attached to
mail and saved alongside plain-text reports. Measured totals and per-client activity are rendered directly by code. Model
interpretations use structured JSON; every cited domain or alert must occur
in that client's evidence, and unsupported findings are omitted.

Requests to local Ollama use
`gemma3:4b`, 32K context, bounded batches and streaming responses. Empty,
incomplete and token-limit responses are rejected; failures produce a warning
email with measured evidence rather than invented conclusions. A sent marker
prevents a second submission on the same local calendar date.

IPv4 WAN traffic is predominantly after NAT. Shared public-IP activity cannot
be attributed to a specific client. Absent traffic does not establish safety
or inactivity. Flow bytes are approximate cumulative observations. Capture
coverage is explicitly reported; the initial report has less than 24 hours.

Ollama is reached through Traefik using its configured host header and a pinned
TLS certificate. The PEM and SHA256 pin in the Pi configuration must be updated
if Traefik's default certificate changes. Verification failures are reported;
TLS validation is not silently bypassed. Prefer a dedicated CA-issued Ollama
certificate when the ingress's DNS/TLS configuration is repaired.

`traefik/network-policy-traefik-allow-egress-ollama.yaml` permits only Traefik
pods to reach `app=ollama` in namespace `ollama` on TCP 11434. This was necessary
because existing Traefik egress policy omitted Ollama. The policy was created
live with explicit approval and needs committing through the normal GitOps
workflow to preserve the source of truth. No commits or pushes were performed.

Useful commands on the Pi:

```sh
sudo systemctl status network-daily-report.timer
sudo journalctl -u network-daily-report.service
sudo /usr/local/sbin/network-daily-report --collect-only
sudo /usr/local/sbin/network-daily-report  # generate without sending
sudo /usr/local/sbin/network-daily-report --send
```
