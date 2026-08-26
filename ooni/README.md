# OONI Probe

This directory contains a daily Kubernetes CronJob for the OONI Probe CLI. The
probe runs the upstream `unattended` test suite at 03:17 in the `Europe/Prague`
time zone and publishes measurements to OONI.

The image is defined in the sibling `Dockerfiles/ooniprobe` repository folder.
It contains the official, statically linked OONI Probe CLI v3.30.0 binary and CA
certificates only. The upstream binary download is protected by the SHA-256
digest published with the GitHub release. The resulting container runs as
UID/GID 65532 with no Linux capabilities and a read-only root filesystem.

Build and publish the image from the `Dockerfiles` repository before enabling
the Argo CD application:

```sh
PLATFORMS=linux/amd64 TAG=3.30.0 ./build.sh ooniprobe
```

The probe database and local measurement artifacts persist in the
`ooniprobe-data` PVC. Informed consent and result publication are deliberately
enabled in `config-map-ooniprobe.yaml`.

The job uses the node network so it can measure both IPv4 and IPv6 even though
the cluster pod network is IPv4-only. Kubernetes NetworkPolicy does not isolate
a host-networked job, so it shares the selected node's network namespace while
active.

The CronJob pins the reviewed Harbor image by its immutable timestamp tag. After
rebuilding the image, update `cron-job-ooniprobe.yaml` to the new timestamp tag
explicitly.
