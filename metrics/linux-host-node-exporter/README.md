# Linux host node exporter

This directory defines the node exporter for `backup.andreybondarenko.com`.
It publishes host CPU, memory, load, filesystem, disk, network, and OS metrics
on TCP port `9100` for the `linux-host-node-exporter` Prometheus job.

Copy `docker-compose.yaml` to the Linux host and start it there:

```bash
docker compose up -d
curl --fail http://127.0.0.1:9100/metrics
```

Restrict inbound TCP/9100 at the host or perimeter firewall to the Prometheus
source address. The exporter is read-only, uses the host network and PID
namespace, and mounts `/` read-only so its metrics describe the host rather
than the container.

The scrape target carries `alert_on_down="false"`. The shared `TargetDown`
rule excludes targets with that label, so shutting down this host or stopping
the exporter does not send an availability alert. Resource alerts naturally
have no series to evaluate while the host is absent.
