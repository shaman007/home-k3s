# Linux host node exporter

This directory defines the node exporter for the Fedora workstation at
`192.168.1.112`. It publishes host CPU, memory, load, filesystem, disk,
network, and OS metrics on TCP port `9100` for the
`linux-host-node-exporter` Prometheus job.

Fedora uses the checked-in Podman Quadlet. Install it as a system service so
node exporter can inspect desktop-managed filesystems under `/run/media`:

```bash
sudo podman quadlet install --replace node-exporter.container
sudo systemctl daemon-reload
sudo systemctl restart node-exporter.service
curl --fail http://127.0.0.1:9100/metrics
```

Enable the `node-exporter` firewalld service for the trusted LAN source or
otherwise allow the Kubernetes nodes to reach TCP/9100. The exporter is
read-only, uses the host network and PID namespace, and mounts `/` read-only.
It runs as container UID 0 only so it can traverse root-owned mount parents;
`no-new-privileges` remains enabled. The existing `docker-compose.yaml` is
retained as a portable alternative for Docker hosts.

The scrape target carries `alert_on_down="false"`. The shared `TargetDown`
rule excludes targets with that label, so shutting down this host or stopping
the exporter does not send an availability alert. Resource alerts naturally
have no series to evaluate while the host is absent.
