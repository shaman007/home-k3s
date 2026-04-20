# Wazuh

This directory deploys a small-footprint Wazuh stack for this cluster:

- `wazuh-manager`: single manager for API, authd, and Dream Machine syslog
- `wazuh-indexer`: single-node indexer for a homelab/small-office footprint
- `wazuh-dashboard`: UI exposed through Traefik

Design notes:

- Images are pulled through Harbor cache paths such as `harbor.andreybondarenko.com/dockerhub/wazuh/...`.
- Pod logs automatically land in Loki through the existing cluster Alloy setup.
- Dream Machine log ingestion is direct syslog into Wazuh, not via Loki. Wazuh does not naturally use Loki as its SIEM event store.
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

Current assumptions:

- LAN devices live on `192.168.1.0/24`.
- The dashboard is served at `wazuh.w386.k8s.my.lan`.
