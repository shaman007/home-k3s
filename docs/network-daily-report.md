# Orange Pi daily network report

The Orange Pi runs `/usr/local/sbin/network-daily-report`, maintained in
`tools/network-daily-report.py`. Its systemd timer schedules 08:00 Europe/Prague
with catch-up after downtime. Input is the last 24 hours of retained Suricata
EVE JSON, including rotated gzip files. Outputs and configuration are under
`/var/lib/network-daily-report` on NVMe. The report is sent to the configured
recipient using STARTTLS on the existing mail server.

The email is an executive brief, not a client-by-client telemetry dump. It opens
with a deterministic assessment, prioritizes issues and next actions, states
confidence, and reports monitoring coverage. Code checks sensor services,
NVMe headroom, event freshness and capture loss. Informational signatures and
routine domains are suppressed. Higher-priority alerts trigger triage, never
an automatic claim of compromise. Device attribution behind NAT is explicitly
reported as an actionable monitoring gap.

Ollama `gemma3:4b` receives a small list of measured issues and writes short
plain-language impact explanations. It cannot choose the overall status,
change actions, or add issues. Requests use structured JSON, 32K context,
streaming and bounded output. Model failures fall back to deterministic
explanations. Raw IPs, signatures and counters stay in the evidence attachment.
A previous complete report is required before claiming day-over-day changes.
The HTML email uses a status heading and short action cards; plain text is
included for other mail clients. `--preview` explicitly resends a preview
without altering the daily sent marker.

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
sudo /usr/local/sbin/network-daily-report --preview  # explicit preview resend
```
