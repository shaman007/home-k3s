# OONI Probe

This directory contains a self-built OONI Probe CLI image and a daily Kubernetes
CronJob. The probe runs the upstream `unattended` test suite at 03:17 in the
`Europe/Prague` time zone and publishes measurements to OONI.

The image contains the official, statically linked OONI Probe CLI v3.30.0 binary
and CA certificates only. The upstream binary download is protected by the
SHA-256 digest published with the GitHub release. The resulting container runs
as UID/GID 65532 with no Linux capabilities and a read-only root filesystem.

Build and publish the image before enabling the Argo CD application:

```sh
podman build --platform linux/amd64 \
  --tag harbor.andreybondarenko.com/library/ooniprobe:3.30.0 \
  --file ooni/Containerfile ooni
podman push harbor.andreybondarenko.com/library/ooniprobe:3.30.0
```

The probe database and local measurement artifacts persist in the
`ooniprobe-data` PVC. Informed consent and result publication are deliberately
enabled in `config-map-ooniprobe.yaml`. NetworkPolicy permits DNS through
CoreDNS and unrestricted protocols to public IPv4/IPv6 destinations, while
excluding private, loopback, link-local, and multicast address ranges.
