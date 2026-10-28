## kubernetes prometheus Setup

### Hubble metrics

`talos/cilium-values.yaml` enables drop, TCP, flow, and ICMP metrics on port
9965. The Cilium chart creates an annotated `hubble-metrics` service, discovered
by the existing `kubernetes-service-endpoints` job. Monitoring egress policies
allow this port to Cilium node endpoints. No ServiceMonitor is needed.
HTTP and DNS metrics are intentionally omitted because they require L7 visibility.
After syncing Cilium and monitoring policies, check every discovered Hubble target
is up and `hubble_flows_processed_total` returns samples.

### Native histogram pilot

Only the `prometheus` self-scrape job enables native histogram scraping and classic
histogram conversion to native custom-bucket histograms (NHCB). Classic histogram
series remain enabled to preserve existing dashboards and alerts. Conversion
preserves existing bucket precision; this pilot validates the data path rather
than adding higher-resolution instrumentation. Keeping both formats increases
storage during the pilot.

After syncing, verify the loaded configuration and a successful self scrape.
Query `prometheus_http_request_duration_seconds` directly and confirm the API
returns histogram samples; also verify its `_bucket` series still exist. Repeat
through Thanos with `max_source_resolution=0s` so the pilot uses raw data. Check
historical queries after sidecar upload before expanding the pilot; downsampled
histogram behavior is not covered by this configuration change.

Rollback by removing the three histogram settings from the self-scrape job.
