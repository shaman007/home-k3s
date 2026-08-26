# RIPE Atlas software probe

This deployment runs the official RIPE NCC Enterprise Linux package in a custom
Oracle Linux 9 image. The upstream RPM is available for x86_64 only, so both the
image builder and Deployment are intentionally limited to AMD64.

The `ripe-atlas-config` volume contains the probe's private identity. Do not
delete it when restarting or upgrading the workload.

After the first pod starts, retrieve its public key:

```bash
kubectl exec -n ripe-atlas deploy/ripe-atlas -- \
  cat /etc/ripe-atlas/probe_key.pub
```

Register that key at <https://atlas.ripe.net/apply/swprobe/>. Approval is manual;
the pod can remain running while RIPE NCC processes the application.

The probe requires its upstream setuid measurement helper and `NET_RAW` for ICMP
measurements. Host networking is also forbidden by the Baseline and Restricted
Pod Security profiles, so this dedicated namespace enforces Privileged while still
auditing and warning against Restricted violations.

The pod uses the node network so it can measure both IPv4 and IPv6 even though the
cluster pod network is IPv4-only. Kubernetes NetworkPolicy does not isolate a
host-networked pod, so the probe shares the selected node's network namespace.

The image bootstraps its RIPE Atlas control registration through the official IPv4
registration endpoints. RIPE derives a NATed probe's public IPv4 address from that
connection, while the probe continues to report its global IPv6 address and execute
measurements over both address families.
