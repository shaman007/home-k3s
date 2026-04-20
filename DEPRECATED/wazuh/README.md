# Wazuh

Deprecated: this stack is no longer part of the active cluster and is kept here only for reference.

This directory deploys a small-footprint Wazuh stack for this cluster:

- `wazuh-manager`: single manager for API, authd, and Dream Machine syslog
- `wazuh-indexer`: single-node indexer for a homelab/small-office footprint
- `wazuh-dashboard`: UI exposed through Traefik
- `loki-forwarder`: polls Loki for security-relevant cluster log lines and forwards them into Wazuh over syslog
- `harbor-webhook-bridge`: receives Harbor webhooks and forwards image/security events into Wazuh over syslog
- `traefik-access-indexer`: mirrors raw Traefik access logs from Loki into OpenSearch indices named `traefik-access-*`
- `traefik-detector-bootstrap`: creates per-host OpenSearch anomaly detectors for exposed ingresses

Design notes:

- Images are pulled through Harbor cache paths such as `harbor.andreybondarenko.com/dockerhub/wazuh/...`.
- Pod logs automatically land in Loki through the existing cluster Alloy setup.
- Dream Machine log ingestion is direct syslog into Wazuh, not via Loki. Wazuh does not naturally use Loki as its SIEM event store.
- The same external Wazuh IP can also accept agent enrollment and secure agent traffic on `1515/tcp` and `1514/tcp`.
- Loki integration in this repo is additive: Wazuh keeps Loki as the source of truth for cluster logs and only mirrors selected high-signal events into the SIEM.
- WordPress web detections are mirrored from Traefik access logs for suspicious paths such as `wp-login.php`, `xmlrpc.php`, `wp-admin`, `wp-content`, `wp-includes`, `wlwmanifest.xml`, and `wp-json`.
- Raw Traefik access logs are also normalized into OpenSearch so anomaly detection can run against real ingress traffic instead of only post-processed Wazuh alerts.
- Harbor integration uses an internal webhook receiver at `http://harbor-webhook-bridge.wazuh.svc.cluster.local/`.
- Credentials and certificates are expected in Vault and synced with External Secrets.

Required Vault data under `kv/wazuh`:

- `indexer_username`
- `indexer_password`
- `dashboard_username`
- `dashboard_password`
- `wazuh_api_username`
- `wazuh_api_password`
- `authd_pass`
- `root_ca_pem`
- `node_pem`
- `node_key_pem`
- `admin_pem`
- `admin_key_pem`
- `filebeat_pem`
- `filebeat_key_pem`
- `dashboard_pem`
- `dashboard_key_pem`

Dream Machine setup:

- Send remote syslog to the `wazuh-syslog` `LoadBalancer` IP.
- Use port `514`.
- UDP is enabled, and TCP is also exposed if the device supports it.

Agent setup:

- Point Wazuh agents at the same external `LoadBalancer` IP.
- Use `1515/tcp` for registration and `1514/tcp` for ongoing secure agent traffic.
- The sample one-liner is:
  `WAZUH_MANAGER='192.168.1.211' WAZUH_REGISTRATION_PASSWORD='wazuh-authd-pass-2026' WAZUH_AGENT_NAME='your-hostname' dpkg -i ./wazuh-agent_4.14.4-1_amd64.deb`

Alert visibility:

- Wazuh keeps all mirrored events in archives, but this repo also raises Loki, Harbor, and UDM-originated events into normal alerts so they appear in the dashboard.
- WordPress alerts are raised as dedicated Wazuh rules for login endpoint access, suspicious probing, anomalous HTTP statuses, and burst-style scanning patterns.
- Ingress anomaly detectors are created per exposed host and include a dedicated WordPress auth detector for `andreybondarenko.com`.

Harbor setup:

- Create a Harbor webhook that points to `http://harbor-webhook-bridge.wazuh.svc.cluster.local/`.
- Start with artifact push, delete, scan completed, and vulnerability-related events.

Current assumptions:

- LAN devices live on `192.168.1.0/24`.
- The dashboard is served at `wazuh.w386.k8s.my.lan`.

Bootstrap note:

- `secret-vault-token.yaml` seeds a placeholder `vault-token` secret so the
  existing Vault token rotator can mint and rotate a namespace-scoped token.
