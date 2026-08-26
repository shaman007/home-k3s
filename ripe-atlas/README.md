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
measurements. For that reason, its namespace enforces the Kubernetes Pod Security
Baseline profile and audits/warns against Restricted rather than enforcing it.
