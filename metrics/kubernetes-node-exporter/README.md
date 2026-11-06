# kubernetes-node-exporter

The DaemonSet uses `hostNetwork: true` because the default netdev collector in
node-exporter 1.12.1 queries netlink in the exporter's network namespace. Mounting
host `/sys` and `/` alone does not make `node_network_*_bytes_total` describe the
node: without host networking those counters describe the pod's `eth0`.
`ClusterFirstWithHostNet` preserves cluster DNS resolution. The exporter retains
its non-root user, read-only mounts and dropped capabilities; host PID/IPC access
is not required for this fix.

Both netdev and netclass exclude pod-side `veth*` and Cilium host-side `lxc*`
interfaces. Physical interfaces and host bridges/tunnels remain available.
Select the physical device when graphing link utilization to avoid counting
traffic again on virtual interfaces.

Prometheus discovers the exporter pods and retains the `kubernetes_node` label.
After rollout their target addresses become node IPs on TCP/9100. The Cilium
policy `monitoring-allow-prometheus-cilium-host-metrics` permits that port only
from the Prometheus pod selector to the local host and remote nodes. The metrics
listener uses the host network; Kubernetes pod ingress policies do not provide
the same isolation as they do for ordinary pod-network exporters.

After deployment, verify all three nodes rather than only DaemonSet readiness:

```promql
up{job="node-exporter"}
node_scrape_collector_success{job="node-exporter",collector="netdev"}
node_network_receive_bytes_total{job="node-exporter",device="enp7s0"}
node_network_transmit_bytes_total{job="node-exporter",device="enp7s0"}
```

Each query should return one healthy series per node. Compare receive/transmit
counters with `/sys/class/net/enp7s0/statistics/{rx_bytes,tx_bytes}` on the same
node; allow for the scrape interval. Check rates after at least two scrapes.
The old pod-`eth0` series may remain visible briefly until Prometheus marks them
stale; they are not a baseline for the new physical-interface counters.

Upstream implementation:
https://github.com/prometheus/node_exporter/blob/v1.12.1/collector/netdev_linux.go
