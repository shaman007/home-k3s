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

GPU and SMART metrics use node exporter's textfile collector. Install the
matching NVIDIA utility package, link the checked-in systemd units, and start
their timers:

```bash
sudo dnf install xorg-x11-drv-nvidia-cuda smartmontools
sudo systemctl link "$PWD"/linux-host-{gpu,smart}-metrics.{service,timer}
sudo systemctl daemon-reload
sudo systemctl enable --now \
  linux-host-gpu-metrics.timer linux-host-smart-metrics.timer
```

The GPU collector runs every 15 seconds and exports utilization, VRAM,
temperature, power, fan percentage, and clocks. The SMART collector runs every
five minutes and exports overall health, disk temperatures, power-on hours,
NVMe wear/spare/error counters, and ATA reallocated/pending/uncorrectable
sectors. Output is written atomically under `/var/lib/node_exporter` and mounted
read-only into node exporter. Motherboard fan RPM is not exported because the
current ASUS hwmon driver does not expose any `fan*_input` sensors.

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
