# Orange Pi daily network report

The Orange Pi runs `/usr/local/sbin/network-daily-report`, maintained in
`tools/network-daily-report.py`. Its systemd timer schedules 08:00 Europe/Prague
with catch-up after downtime. Input is the last 24 hours of retained Suricata
EVE JSON, including rotated gzip files. Outputs and configuration are under
`/var/lib/network-daily-report` on NVMe. Mail uses STARTTLS on the existing server.

The email opens with a verdict: no concerning activity detected, an anomaly
requiring attention, potential threat, degraded monitoring, or incomplete
analysis. Actionable findings name the connection or behavior, supporting
observations, confidence and next action. An IDS alert is not proof of compromise.
The verdict applies only to observed network traffic.

Alerts are correlated with final connection records by flow ID, including
connection state, response packets, byte counts, domains and signature metadata.
Informational signatures and incoming reputation probes without an established
session are excluded from incident triage. Small reputation-only exchanges on
expected public services are treated as background unless a related substantive
alert supplies corroboration. Outbound reputation alerts remain candidates.
Sensor service health, storage headroom, event freshness and capture loss are
checked separately; monitoring failures cannot produce an all-clear.

Ollama `gpt-oss:20b` assesses remaining incidents using structured JSON and a
32K context. Every candidate must receive a classification and evidence-based
reason. Missing or incomplete model output yields incomplete analysis rather
than an all-clear. Reputation alone cannot establish a threat. Live verification
showed the RTX 4070 Ti participating in inference with CPU offload: Ollama
reported 48% CPU / 52% GPU placement with this model and context on 12 GB VRAM.
These percentages describe placement, not GPU utilization.

A comparable previous report with at least 20 hours of observations is required
before claiming day-over-day changes. Per-client uploads of at least 1 GiB and
five times the baseline are anomaly candidates when both reports have sufficient
coverage and byte counters. Shared public-IP traffic is excluded from that
client comparison. Cumulative flow counters are deduplicated by client and flow;
long-lived flows and capture boundaries still limit exact window attribution.

HTML and plain-text reports are saved alongside `evidence.json`,
`assessment.json` and `model-findings.json`. The email attaches technical evidence.
`--preview` explicitly resends without altering the daily sent marker.

IPv4 WAN traffic is predominantly after NAT, so shared public-IP activity cannot
be attributed to a specific client. Encrypted content and unobserved devices are
outside the verdict. Absent traffic does not establish safety or inactivity.
Capture duration is reported explicitly; the initial report has less than 24 hours.

Ollama is reached through Traefik using its configured host header and a pinned
TLS certificate. Update the PEM and SHA256 pin in the Pi configuration when
Traefik's default certificate changes. Verification failures are reported;
TLS validation is not silently bypassed.

`traefik/network-policy-traefik-allow-egress-ollama.yaml` permits Traefik pods
to reach `app=ollama` in namespace `ollama` on TCP 11434.

Useful commands on the Pi:

```sh
sudo systemctl status network-daily-report.timer
sudo journalctl -u network-daily-report.service
sudo /usr/local/sbin/network-daily-report --collect-only
sudo /usr/local/sbin/network-daily-report  # generate without sending
sudo /usr/local/sbin/network-daily-report --send
sudo /usr/local/sbin/network-daily-report --preview  # explicit preview resend
```

Regression checks:

```sh
python3 -m unittest discover -s tests -p 'test_network_daily_report.py'
```
