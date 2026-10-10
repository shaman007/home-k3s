# Retired Omni trial

Retired on 2026-10-10 after evaluating the interface and features. Do not redeploy these archived manifests automatically.

Omni was stopped and its SideroLink, EventSink, and omni-kmsg configuration documents were removed from all three Talos nodes without rebooting or changing their working Kubernetes/etcd configuration. The nodes retain the direct API endpoint https://192.168.1.100:6443. No pending Omni configs were applied.

After the retirement was published, cleanup removed the Helm release, namespace, 10 GiB Omni PVC, dedicated Keycloak client, and OpenBao Omni credentials/access rules. Cluster recovery backups in kv/omni-import-backup are retained. Do not restore the database onto a running management instance without reviewing the recovered etcd identities.

The parent Argo Application temporarily excludes application-omni.yaml while published main still contains it. Publish the retirement diff through the normal workflow; no commit or push was performed during retirement.

Original deployment material is under deployment/; associated manifests are archived under their original folder names. Existing DNS names are unchanged.
