# Changelog

## 2023-11-10 – `ffe61c7` by Andrey Bondarenko
- **License Addition**
  - Added MIT License to the project (LICENSE file created).
  - Copyright attributed to Andrey Bondarenko (2023).

## 2023-11-10 – `58ec08f` by Andrey Bondarenko
- **New Files Added**
  - `.gitignore`: Added to ignore `secret.yaml`.
  - `.pre-commit-config.yaml`: Configured pre-commit hooks for code quality checks.
  - `CHANGELOG.md`: Created for tracking changes.
  - `README.md`: Added installation and configuration instructions for k3s and various services.
  - `cert-manager/cert-manager.yaml`: Introduced cert-manager configuration.

- **Documentation Updates**
  - Expanded `README.md` with detailed setup instructions for k3s, NFS, Let's Encrypt, NGINX ingress, and other services.

- **Configuration Changes**
  - Updated `cert-manager` configuration with new CRDs and namespaces.
  - Added cron jobs and backup scripts in `cron/`.

- **Breaking Changes**
  - None noted in the diff; however, ensure compatibility with new cert-manager configurations.

## 2023-11-10 – `349f36a` by Andrey Bondarenko
- **Documentation Update**
  - Expanded project description in `README.md` to clarify purpose and capabilities of the k3s-local cluster.
  - Added detailed list of services and applications supported, including Dovecot, Postfix, Nextcloud, and Matrix.
  - Introduced a "ToDo" section for future enhancements, listing planned services like Mozilla sync and Bitwarden.

- **Formatting Improvements**
  - Improved structure and readability of the `README.md` with new sections for "Works" and "ToDo".

## 2023-11-10 – `5810228` by Andrey Bondarenko
- **Removed**: Deleted `mail/rsyslog_configmap.yaml` file.
- **Impact**: Configuration for rsyslog logging has been removed; ensure alternative logging configurations are in place.

## 2023-11-10 – `3f2e534` by Andrey Bondarenko
- **Configuration Update**:
  - Removed hardcoded password entry from `mail/dovecot_configMap.yaml`.

- **File Affected**:
  - `mail/dovecot_configMap.yaml` - Ensure to update any dependent configurations or secrets management practices.

## 2023-11-11 – `52b2740` by Andrey Bondarenko
- **Container Updates:**
  - Changed container name from `previews` to `previewsa` in `cron/cronjob-nextcloud.yaml`.
  - Updated image from `php-fpm:latest` to `php:latest` in:
    - `nextcloud/php_deployment.yaml`
    - `wordpress/php_deployment.yaml`

- **File Modifications:**
  - Modified deployment configurations for Nextcloud and WordPress to use a new PHP image.

## 2023-11-13 – `2ffc0e6` by Andrey Bondarenko
### CHANGELOG for Commit 2ffc0e6

#### Cron Jobs
- **Added** new Kubernetes CronJobs for backup operations across multiple namespaces:
  - **Matrix**: `cronjob-conduil.yaml` - Backs up `/matrix` to NFS.
  - **Mail**: `cronjob-mail.yaml` - Backs up `/mail` to NFS.
  - **MySQL**: `cronjob-mysql.yaml` - Backs up MySQL databases using a custom image.
  - **Postgres**: `cronjob-postgres.yaml` - Backs up PostgreSQL databases using a custom image.
  - **Redis**: `cronjob-redis.yaml` - Backs up Redis data using a custom image.

#### Persistent Volume Claims
- **Added** PersistentVolumeClaims for backup storage in respective namespaces (matrix, mail, db, redis) with `1Gi` storage requests.

#### File Removal
- **Removed** `cron/backup.sh` script, consolidating backup logic into Kubernetes CronJobs.

#### Important Notes
- Ensure that the new CronJobs are properly scheduled and that the necessary images are available in the specified private registry.
- Review the removal of `backup.sh` for any dependencies in existing workflows.

## 2023-11-13 – `4ed80e1` by Andrey Bondarenko
- **Removed CronJob Configuration**
  - Deleted `cron/cronjob.yaml`, removing the backup CronJob definition for the `db` namespace.
  - This includes the job schedule, container configuration, and volume mounts.

## 2023-11-13 – `e9e3c6e` by Andrey Bondarenko
- **Documentation Updates**
  - Added backup details for mail, databases, and Redis to `README.md`.
  - Updated ToDo list with new items: "Minecraft backup" and removed "Proper backup of the mail and databases".

## 2023-11-14 – `df5bec3` by Andrey Bondarenko
- **File Removal**: Deleted `nextcloud/apppass` file containing sensitive application password.
- **Security Improvement**: Enhances security by removing hardcoded credentials from the repository.

## 2023-11-14 – `de86156` by Andrey Bondarenko
- **Bitwarden Deployment**:
  - Added `bitwarden-deployment.yaml` for Bitwarden deployment configuration.
  - Configured environment variables for database and SMTP settings.

- **Ingress Configuration**:
  - Introduced `bitwarden-ingress.yaml` for managing external access via NGINX ingress.
  - Set up TLS with Let's Encrypt for secure connections.

- **Persistent Storage**:
  - Created `bitwarden-persistentvolumeclaim.yaml`, `data-persistentvolumeclaim.yaml`, and `logs-persistentvolumeclaim.yaml` for persistent storage needs.
  - Each PVC configured with `ReadWriteOnce` access mode and 100Mi storage request.

- **Service Definition**:
  - Added `bitwarden-service.yaml` to expose Bitwarden service on port 80.

- **Documentation Update**:
  - Updated `README.md` to include Bitwarden self-hosted note and memory usage warning.

## 2023-11-15 – `9a84083` by Andrey Bondarenko
- **New Features:**
  - Added a **CronJob** for Minecraft backups in `cron/cronjob-minecraft.yaml`, scheduled to run daily at 08:05 UTC.
  - Introduced a **PersistentVolumeClaim** for backup storage in `cron/cronjob-minecraft.yaml`.

- **Environment Variables:**
  - Added `ENABLE_RCON` and `RCON_PASSWORD` environment variables in `minecraft/minecraft_deployment.yaml` for RCON access.

- **Networking:**
  - Exposed new **RCON service** on port 25575 in `minecraft/minecraft_deployment.yaml`.

- **File Additions:**
  - Created `cron/cronjob-minecraft.yaml` for backup management.

- **Breaking Changes:**
  - Updated deployment to include RCON support; ensure secrets are configured for `RCON_PASSWORD`.

## 2023-11-15 – `e59fd6a` by Andrey Bondarenko
- **Documentation Updates:**
  - Updated README.md to include Minecraft in backup list.
  - Added Spotify stats application and Languagetool local instance to ToDo list.

## 2023-11-15 – `e2a81d8` by Andrey Bondarenko
- **Documentation Updates (README.md)**
  - Added section on **Cluster Installation** with sysctl changes for K8S compatibility.
  - Specified configuration output for K3s installation, including `cluster-cidr`, `service-cidr`, and disabling Traefik.
  - Updated deployment instructions for **NGINX ingress** replacing Traefik.
  - Included optional **Dashboard** deployment instructions and Helm commands for **Postgres**, **TT-RSS**, **Collabora**, and **Registry**.
  - Added **Mail** service exposure and TLS certificate copying instructions.
  - Clarified cleanup commands for **Docker** and **Rancher**.

- **Breaking Changes**
  - Traefik is no longer used; NGINX ingress is now the default ingress controller.

## 2023-11-15 – `ea878ee` by Andrey Bondarenko
- **Documentation Update**
  - Added "Ubiquity controller instance" to the project list in `README.md`.

## 2023-11-15 – `44c8af1` by Andrey Bondarenko
- **Documentation Update**
  - Added image of ARM-based K3S cluster to `README.md` for visual reference.

## 2023-11-16 – `c59266f` by Andrey Bondarenko
- **Removed**: `bitwarden/bitwarden-persistentvolumeclaim.yaml` file deleted.
- **Impact**: PersistentVolumeClaim for Bitwarden service is no longer available; ensure storage requirements are addressed in deployment.

## 2023-11-17 – `991fea6` by Andrey Bondarenko
- **MongoDB Setup**:
  - Added `mongo/configmap.yaml`: ConfigMap for MongoDB configuration.
  - Introduced `mongo/deployment.yaml`: StatefulSet for MongoDB deployment.
  - Created `mongo/mongo-persistentvolumeclaim.yaml`: PVC for MongoDB data storage.
  - Added `mongo/service.yaml`: Service definition for MongoDB access.

- **Documentation Update**:
  - Updated `README.md`: Mentioned MongoDB without authentication for Spotify stats application.

## 2023-11-18 – `aa06b4c` by Andrey Bondarenko
- **New Features**
  - Added **Ingress** resources for `server` and `web` services in `your-spotify/ingress.yaml` for SSL termination and routing.
  - Introduced **Deployment** configurations for `server` and `web` in `your-spotify/server-deployment.yaml` and `your-spotify/web-deployment.yaml`, respectively.
  - Created **Service** definitions for `server` and `web` in `your-spotify/server-service.yaml` and `your-spotify/web-service.yaml`.

- **Documentation**
  - Updated `README.md` to include the Spotify stats application in the project overview.

- **Environment Variables**
  - Configured environment variables for API endpoints and MongoDB connection in the new deployment files.

- **Namespace**
  - All new resources are deployed under the `spotify` namespace.

- **Breaking Changes**
  - Ensure existing configurations are compatible with the new Ingress and Service definitions.

## 2023-11-18 – `c5d7085` by Andrey Bondarenko
- **Documentation**:
  - Added `README.md` for the `your-spotify` project.
  - Included source link and ingress configuration note.

## 2023-11-18 – `6d4dae1` by Andrey Bondarenko
- **Documentation Update**
  - Added link to Mongo deployment YAMLs in `your-spotify/README.md`.

## 2023-11-21 – `16715a6` by Andrey Bondarenko
- **Removed**: `registry/htpasswd` file deleted.

## 2023-11-21 – `879081d` by Andrey Bondarenko
- **Documentation Updates**
  - Removed redundant line in the introduction of `README.md`.
  - Added "Mastodon" to the ToDo list in `README.md`.

- **Cleanup Instructions**
  - Added Docker cleanup command: `docker system prune -a`.
  - Removed Rancher cleanup section (incomplete).

## 2023-11-21 – `33455a8` by Andrey Bondarenko
- **Documentation Updates**
  - Enhanced `README.md` with installation instructions and configuration details.
  - Added code block formatting for clarity in command examples.

- **Changelog Improvements**
  - Created initial `CHANGELOG.md` with a summary of updates and changes.

- **General Cleanup**
  - Removed redundant entries and improved overall structure in both `README.md` and `CHANGELOG.md`.

## 2023-11-22 – `7e1bf9f` by Andrey Bondarenko
- **Version Update**
  - Updated `app.kubernetes.io/version` from `v1.12.4` to `v1.13.2` in `cert-manager/cert-manager.yaml`.

- **File Affected**
  - `cert-manager/cert-manager.yaml`: All instances of the version label were updated to reflect the new version.

- **Impact**
  - Ensure compatibility with features and fixes introduced in cert-manager v1.13.2.

## 2023-11-22 – `e80a1f3` by Andrey Bondarenko
### CHANGELOG for Commit e80a1f3

#### Resource Adjustments
- **Bitwarden**: Added CPU and memory requests/limits to deployment.
- **Grafana**: Reduced CPU and memory requests/limits.
- **Kubernetes Node Exporter**: Adjusted CPU and memory requests/limits.
- **Prometheus**: Updated resource requests/limits for both main and alertmanager containers.
- **Nextcloud**: Modified CPU and memory requests/limits.
- **Your Spotify**: Added resource requests/limits for both server and web deployments.

#### Configuration Updates
- **Your Spotify**: Updated CORS environment variable to include an additional domain.
- **Web Deployment**: Added labels for better categorization.

#### File Changes
- Affected files include:
  - `bitwarden/bitwarden-deployment.yaml`
  - `metrix/graphana/graphana.yaml`
  - `metrix/kubernetes-node-exporter/daemonset.yaml`
  - `metrix/kubernetes-prometheus/prometheus-deployment.yaml`
  - `nextcloud/php_deployment.yaml`
  - `your-spotify/server-deployment.yaml`
  - `your-spotify/web-deployment.yaml`

## 2023-11-22 – `e81b1d9` by Andrey Bondarenko
- **CronJob Update:**
  - Renamed `previews` to `nextcloud` in `cron/cronjob-nextcloud.yaml`.
  - Updated command to run Nextcloud's cron script using `php /nextcloud/cron.php`.

- **Dovecot Deployment:**
  - Removed commented-out `configMap` reference in `mail/dovecot_deployment.yaml`.

- **MongoDB Configuration:**
  - Added `serviceName: mongodb` in `mongo/deployment.yaml`.

- **Ingress Configuration:**
  - Added `nginx.ingress.kubernetes.io/more_set_headers` for `X-Forwarded-For` in `nextcloud/ingress.yaml`.

- **Service Annotations:**
  - Removed annotations from `your-spotify/server-service.yaml` and `your-spotify/web-service.yaml`.
  - Added labels `app: server` and `app: frontend` respectively.

## 2023-11-23 – `0d7c328` by Andrey Bondarenko
- **New Configurations**:
  - Added `clamav/configmap.yaml` for ClamAV configuration settings.

- **Deployment Setup**:
  - Introduced `clamav/deployment.yaml` defining a deployment with two containers: `clamd` and `fresclam`.
  - Configured persistent volume claim `avdata` for data storage.

- **Service Exposure**:
  - Created `clamav/service.yaml` to expose ClamAV on TCP port 3200.

- **Image and Resources**:
  - Utilizes `registry.andreybondarenko.com/clamav:latest` for container images.
  - Resource requests and limits set for CPU and memory for both containers.

- **Namespace**:
  - All resources are deployed under the `clamav` namespace.

## 2023-11-23 – `fe51146` by Andrey Bondarenko
- **Documentation Update**
  - Added note about ClamAV service: `clamav.clamav.csv.cluster.local:3200/TCP` to README.md.

- **To-Do List Adjustments**
  - Removed Languagetool local instance from To-Do list in README.md.

## 2023-11-23 – `441a4fc` by Andrey Bondarenko
- **Documentation Update**
  - Corrected spelling of "Clamav" in README.md.

## 2023-11-23 – `b2ffb1d` by Andrey Bondarenko
- **Documentation Update**
  - Corrected ClamAV service URL in `README.md` from `clamav.clamav.csv.cluseter.local` to `clamav.clamav.svc.cluster.local`.

## 2023-11-23 – `0a33b76` by Andrey Bondarenko
- **Documentation Update**
  - Added section on Dockerfiles in `README.md` for cluster setup.
  - Included link to external Dockerfiles repository for user reference.
  - Corrected typos in installation notes.

## 2023-11-23 – `bbf5214` by Andrey Bondarenko
- **Documentation Update**
  - Revised `README.md` for clarity and accuracy.

## 2023-11-23 – `e46947e` by Andrey Bondarenko
- **ClamAV**
  - Moved `PersistentVolumeClaim` for `avdata` to `clamav/pvc.yaml`.
  - Removed inline PVC definition from `clamav/deployment.yaml`.

- **Conduit**
  - Added `Ingress` and `Service` definitions for `matrix` in `conduit/matrix_ingress.yaml` and `conduit/matrix_service.yaml`.
  - Moved `PersistentVolumeClaim` for `matrix` to `conduit/pvc.yaml`.
  - Removed previous PVC, Service, and Ingress definitions from `conduit/conduit_deploy.yaml`.

- **Mail Services**
  - Added separate Service definitions for `dovecot-tls`, `dovecot-lmtp`, and `dovecot-sasl` in their respective YAML files.
  - Removed inline Service definitions from `mail/dovecot_deployment.yaml`.

- **General**
  - Multiple YAML files updated across various services, ensuring better modularity and organization of Kubernetes resources.

## 2023-11-23 – `5db3c3f` by Andrey Bondarenko
- **New Features**
  - Added `dovecot-lmtp` Service in `mail/docecot_lmtp_service.yaml` for handling LMTP traffic.

- **Changes**
  - Removed `PersistentVolumeClaim` configuration from `minecraft/minecraft_deployment.yaml`.
  - Updated `minecraft/pvc.yaml` to define a new `PersistentVolumeClaim` named `minecraft-nfs` with `ReadWriteMany` access mode and `nfs-client` storage class.

- **File Modifications**
  - `mail/docecot_lmtp_service.yaml`: New service file created.
  - `minecraft/minecraft_deployment.yaml`: Significant removal of PVC configuration.
  - `minecraft/pvc.yaml`: Updated to reflect new PVC specifications.

## 2023-11-25 – `4f83368` by Andrey Bondarenko
- **Deployment**: Added `minio` deployment configuration in `minio-single/deployment.yaml`.
  - Configures a single replica with resource limits and environment variables for MinIO.
  - Uses a private image from `registry.andreybondarenko.com`.

- **Persistent Storage**: Introduced PersistentVolumeClaim in `minio-single/pvc.yaml`.
  - Requests 100Gi of storage with `ReadWriteOnce` access mode.

- **Service**: Created service definition in `minio-single/service.yaml`.
  - Exposes MinIO on TCP port 9000.

- **Breaking Change**: New configuration files added; ensure existing setups are compatible with the new deployment structure.

## 2023-11-25 – `b174661` by Andrey Bondarenko
### CHANGELOG for Commit b174661

#### Resource Limits and Requests
- **Increased CPU limits** for several deployments:
  - `bitwarden`: from 0 to 1000m
  - `clamav`: from 0 to 2000m
  - `collabora`: from 0 to 1000m
  - `conduit`: from 0 to 1000m
  - `dovecot`: from 0 to 300m
  - `grafana`: from 0 to 1000m
  - `minecraft`: from 0 to 4000m
  - `mysql`: from 0 to 2000m
  - `nextcloud`: from 0 to 350m (nginx) and 0 to 6000m (php)
  - `postgres`: from 0 to 300m
  - `redis`: from 0 to 300m
  - `rsyslog`: from 0 to 100m

#### Configuration Changes
- **Updated image tags** in `collabora` and `postgres` to `latest` and `15`, respectively.
- **Removed unnecessary labels** from `mongo-persistentvolumeclaim.yaml`.

#### Deployment Adjustments
- **Added volume mounts** for `clamav` to include `clamd.conf`.
- **Adjusted memory requests** for `clamav` and `kube-state-metrics-configs` to optimize resource usage.

#### File Modifications
- Key files modified include:
  - `bitwarden/bitwarden-deployment.yaml`
  - `clamav/deployment.yaml`
  - `collabora/values.yaml`
  - `

## 2023-11-25 – `c672eeb` by Andrey Bondarenko
- **Postfix Deployment Updates:**
  - Added `antivirus-cf` configMap for antivirus configuration in `mail/postfix_deployment.yaml`.
  - Mounted `antivirus.conf` at `/etc/rspamd/modules.d/antivirus.conf`.

- **RSPAMD Configuration Changes:**
  - Introduced antivirus configuration in `mail/rspamd_configmap.yaml`.
  - Removed greylist and neural configuration includes to streamline settings.

- **Resource Limits Adjustments:**
  - Increased CPU limits for postfix and rspamd containers in `mail/postfix_deployment.yaml`.

- **Breaking Changes:**
  - Removal of greylist configuration may affect existing setups relying on greylisting.

## 2023-11-25 – `1360374` by Andrey Bondarenko
- **MongoDB Image Update**
  - Upgraded MongoDB image from `mongo:4.0.8` to `mongo:4.4.0` in `mongo/deployment.yaml`.

- **Resource Limits Adjustment**
  - Added CPU limit of `1000m` to MongoDB container in `mongo/deployment.yaml`.

- **Node Affinity Configuration**
  - Specified `nodeName: worker-04.k8s.my.lan` for MongoDB deployment in `mongo/deployment.yaml`.

- **File Affected**
  - `mongo/deployment.yaml`

## 2023-11-25 – `f84b9d9` by Andrey Bondarenko
- **New Feature**: Added `postgres-cli` Deployment configuration.
  - File: `postgres/cli-deployment.yaml`
  - Namespace: `db`
  - Image: `registry.andreybondarenko.com/postgres-cli:latest`

- **Container Configuration**:
  - Memory limit set to `128Mi`, CPU limit set to `500m`.
  - Environment variables configured for PostgreSQL connection (e.g., `PGPASSWORD`, `PGHOST`, `PGUSER`, `PGPORT`, `PGDATABASE`, `OUTPUT_DIR`).

- **Volume Management**:
  - Configured volume mount for backup data using a Persistent Volume Claim named `backup`.

- **Image Pull Secrets**: Specified `my-private-registry` for pulling the container image.

## 2023-11-25 – `b82c72d` by Andrey Bondarenko
- **Alertmanager Configuration**:
  - Added `alertmanager-configmap.yaml` for Alertmanager configuration.
  - Introduced `alertmanager-deployment.yaml` for deploying Alertmanager with specified resources and volume mounts.

- **Prometheus Deployment**:
  - Updated `prometheus-deployment.yaml` to include a new resource limit for CPU.
  - Removed existing PersistentVolumeClaim configuration from `prometheus-deployment.yaml`.

- **Persistent Volume Claim**:
  - Added `prometheus-pvc.yaml` for PersistentVolumeClaim with `ReadWriteMany` access mode and 500Gi storage request.

- **File Structure**:
  - New files created: `alertmanager-configmap.yaml`, `alertmanager-deployment.yaml`, `prometheus-pvc.yaml`.
  - Removed configuration sections from `prometheus-deployment.yaml` related to PersistentVolumeClaim and Alertmanager configuration.

**Note**: Ensure to review the removal of Alertmanager configuration from the Prometheus deployment file as it may affect existing setups.

## 2023-11-26 – `a586300` by Andrey Bondarenko
- **Deployment Configuration**
  - Added `unifi/deployment.yaml` for Unifi application deployment.
  - Configured container with environment variables for MongoDB connection.

- **Persistent Storage**
  - Introduced `unifi/pvc.yaml` for PersistentVolumeClaim named `unifi-nfs` with 5Gi storage.

- **Service Exposure**
  - Created `unifi/service.yaml` to expose Unifi application on multiple ports (TCP/UDP).
  - Set external IP to `192.168.1.102` for service accessibility.

- **Breaking Changes**
  - New deployment and service configurations may require adjustments in existing infrastructure.

## 2023-11-26 – `be463d8` by Andrey Bondarenko
- **Documentation Updates**
  - Removed "ToDo" section from `README.md`, including items for Mastodon and Ubiquity controller instance.

## 2023-11-28 – `8f22519` by Andrey Bondarenko
- **Documentation Updates:**
  - Removed mail-related port forwarding instructions from `README.md`.

- **Mail Services Configuration:**
  - Added `externalIPs` (192.168.1.101) to `dovecot_tls_service.yaml` and `postfix_tls_service.yaml`.

- **MinIO Service Enhancements:**
  - Added new ports (9090 for web) and names (s3) in `minio-single/service.yaml`.

## 2023-11-28 – `323481e` by Andrey Bondarenko
- **Resource Configuration**
  - Increased memory limit for MinIO deployment from 1000Mi to 2000Mi in `minio-single/deployment.yaml`.

## 2023-11-28 – `cb191b1` by Andrey Bondarenko
- **Deployment Configuration (unifi/deployment.yaml)**:
  - Added resource requests for CPU (`100m`) and memory (`500Mi`).
  - Set resource limits for memory (`2048Mi`) and CPU (`2500m`).
  - Specified `nodeName` as `worker-01.k8s.my.lan`.

- **Service Configuration (unifi/service.yaml)**:
  - Removed commented-out LoadBalancer type configuration.

## 2023-11-29 – `e5d8ff2` by Andrey Bondarenko
- **Kubernetes Resources Updates**
  - Added `apiVersion` and `---` separator to multiple YAML files across `bitwarden`, `cert-manager`, `clamav`, `collabora`, and `conduit` directories.
  - Updated `Ingress`, `Service`, `Deployment`, `PersistentVolumeClaim`, and `ConfigMap` definitions to include proper API versions.

- **Cron Jobs Enhancements**
  - Introduced `PersistentVolumeClaim` definitions in cron job YAML files for `conduil`, `mail`, `minecraft`, `mysql`, and `nextcloud`.
  - Updated backup commands in cron jobs to improve readability with line breaks.

- **Configuration Changes**
  - Added `write-kubeconfig-mode` and `tls-san` entries in `config.yaml`.

**Important Files:**
- `bitwarden/bitwarden-deployment.yaml`
- `cert-manager/cert-manager.yaml`
- `conduit/nginx_deployment.yaml`
- `cron/cronjob-mail.yaml`

**Breaking Changes:**
- Ensure compatibility with updated API versions for Kubernetes resources.

## 2023-11-29 – `e33a729` by Andrey Bondarenko
- **Documentation Updates**
  - Added new components to the project overview in `README.md`: UniFi console, Minio (single drive), and Elasticsearch.
  - Updated ToDo section in `README.md` to include Mastodon.

## 2023-11-29 – `9af7037` by Andrey Bondarenko
- **Bitwarden**
  - Added `bitwarden` namespace configuration (`bitwarden/bitwarden-namespace.yaml`).
  - Introduced PersistentVolumeClaims for `data` and `logs` services (`bitwarden/bitwarden-data-pvc.yaml`, `bitwarden/bitwarden-logs-pvc.yaml`).
  - Removed legacy PersistentVolumeClaims (`bitwarden/data-persistentvolumeclaim.yaml`, `bitwarden/logs-persistentvolumeclaim.yaml`).

- **Cert-Manager**
  - Added `cert-manager` namespace configuration (`cert-manager/cert-manager-namespace.yaml`).
  - Introduced deployments for `cert-manager`, `cainjector`, and `webhook` components (`cert-manager/cert-manager-deployment.yaml`, `cert-manager/cert-manager-cainjector-deployment.yaml`, `cert-manager/cert-manager-webhook-deployment.yaml`).
  - Updated deployment configurations with resource requests and security contexts.

**Breaking Changes**:
- Removal of old PersistentVolumeClaims for Bitwarden may affect existing deployments.

## 2023-11-29 – `2d6f6fd` by Andrey Bondarenko
- **Deployment Updates:**
  - Renamed PVC from `code-nfs` to `wordpress-lh` in `nginx-deployment.yaml` and `php-deployment.yaml`.
  - Updated volume mounts in both deployment files to use `wordpress-lh`.

- **Persistent Volume Claim Changes:**
  - Changed PVC name from `code-nfs` to `wordpress-lh` in `php-pvc.yaml`.
  - Updated storage class from `nfs-client` to `longhorn` in `php-pvc.yaml`.

- **Breaking Change:**
  - Existing configurations using `code-nfs` must be updated to `wordpress-lh` to ensure proper functionality.

## 2023-11-29 – `53ba699` by Andrey Bondarenko
### CHANGELOG for Commit 53ba699

#### Bitwarden
- Updated PersistentVolumeClaims (PVCs) to use Longhorn storage:
  - `bitwarden-data-pvc.yaml`: Changed name to `data-lh`, increased storage from 100Mi to 300Mi, access mode changed to `ReadWriteMany`.
  - `bitwarden-logs-pvc.yaml`: Changed name to `logs-lh`, increased storage from 100Mi to 300Mi, access mode changed to `ReadWriteMany`.
- Modified deployment to reflect PVC name changes and updated volume mounts in `bitwarden-deployment.yaml`.

#### Conduit
- Updated PVC for matrix storage in `conduit/matrix-pvc.yaml`: Changed name to `matrix-lh`, increased storage from 20Gi to 500Mi, access mode changed to `ReadWriteMany`.
- Adjusted deployment and cron jobs to use updated PVC names (`matrix-lh`).

#### Mail
- Transitioned mail-related PVCs to Longhorn:
  - `dovecot-pvc.yaml`: Changed name to `mail-lh`, reduced storage from 500Gi to 10Gi.
  - Updated volume mounts in `dovecot-deployment.yaml`, `postfix-deployment.yaml`, and cron jobs to use `mail-lh`.
- Introduced `migrate.yaml` for volume migration from `mail-nfs` to `mail-lh`.

#### Nextcloud
- Updated PVC reference in cron job to use Longhorn (`nextcloud-lh`).

#### Breaking Changes
- PVC names and storage classes have changed across multiple deployments, requiring updates to existing configurations and potential migration of data.

## 2023-11-29 – `8a40aec` by Andrey Bondarenko
- **Removed**: Deleted `mail/migrate.yaml` file, which defined a Pod for volume migration using Nginx.
- **Impact**: This change may affect any existing workflows or deployments relying on the `migrate1` Pod configuration.

## 2023-11-29 – `a571d75` by Andrey Bondarenko
- **Documentation Update**
  - Updated storage description in `README.md`: changed from NFS to Longhorn with NFS as backup.

## 2023-11-30 – `a15ef84` by Andrey Bondarenko
- **Configuration Update:**
  - Renamed volume from `minecraft-nfs` to `minecraft-lh` in `cron/cronjob-minecraft.yaml`.
  - Updated corresponding `persistentVolumeClaim` to `minecraft-lh`.

- **File Affected:**
  - `cron/cronjob-minecraft.yaml`

## 2023-11-30 – `c479cbe` by Andrey Bondarenko
- **Cron Jobs:**
  - Updated Nextcloud cron job schedule from `*/5` to `*/15` minutes in `cron/cronjob-nextcloud.yaml`.
  - Changed Redis backup PVC claim name from `backup` to `backup-lh` in `cron/cronjob-redis.yaml`.

- **Persistent Volume Claims (PVCs):**
  - Added `postgres-pvc.yaml` for PostgreSQL backup with `nfs` storage class.
  - Updated Redis PVC to use `longhorn` storage class and renamed to `backup-lh` in `cron/redis-pvc.yaml`.
  - Added new PVC for MongoDB named `mongo-lh` using `longhorn` storage class in `mongo/mongo-pvc.yaml`.
  - Added new PVC for MySQL named `mysql-lh` using `longhorn` storage class in `myqsl/mysql-pvc.yaml`.

- **Deployments:**
  - Updated MongoDB deployment to use `mongo-lh` PVC in `mongo/mongo-deployment.yaml`.
  - Updated MySQL deployment to use `mysql-lh` PVC in `myqsl/mysql-deployment.yaml`.
  - Introduced Redis CLI deployment in `redis/cli-deployment.yaml`.

- **Nextcloud Configuration:**
  - Removed `output_buffering` setting from `nextcloud/php-configmap.yaml` and set it to `Off` in the deployment.
  - Configured PHP deployment to mount custom `php.ini` from config map in `nextcloud/php-deployment.yaml`.

- **Unifi Configuration:**
  - Updated Unifi deployment to use `unifi-lh` PVC instead of `unifi-nfs` in `unifi/un

## 2023-11-30 – `f1fe885` by Andrey Bondarenko
- **Removed Persistent Volume Claims:**
  - Deleted `cron/postgres-pvc-yaml`.
  - Removed `mongo-nfs` PVC from `mongo/mongo-pvc.yaml`.
  - Removed `mysql-pv-claim` from `myqsl/mysql-pvc.yaml`.

- **Updated Persistent Volume Claims:**
  - Renamed `mongo-nfs` to `mongo-lh` in `mongo/mongo-pvc.yaml`.
  - Renamed `mysql-pv-claim` to `mysql-lh` in `myqsl/mysql-pvc.yaml`.

- **Namespace Consistency:**
  - All PVCs now consistently use the `db` namespace.

- **Storage Class:**
  - All PVCs retain `nfs-client` as the storage class.

**Note:** Ensure applications referencing the old PVC names are updated accordingly to prevent disruptions.

## 2023-12-03 – `96b08aa` by Andrey Bondarenko
- **Resource Configuration**
  - Updated memory limit for the deployment in `clamav/clamav-deployment.yaml` from `2048Mi` to `4800Mi`.

## 2023-12-05 – `7a1e62d` by Andrey Bondarenko
- **Deployment Configuration**
  - Added `nodeName: worker-04.k8s.my.lan` to `nextcloud/php-deployment.yaml` for specifying the node for deployment.

## 2023-12-06 – `22cc819` by Andrey Bondarenko
- **Postfix Configuration Updates**
  - Updated `postfix-configMap.yaml` to use `rspamd.mail.svc.cluster.local` for milter settings.

- **Removed Rspamd Configuration**
  - Removed multiple volume mounts and configurations related to Rspamd from `postfix-deployment.yaml`.

- **New Rspamd Deployment**
  - Added `rspamd-deployment.yaml` to define a new Rspamd deployment with a single replica and necessary configurations.

- **Rspamd ConfigMap Enhancements**
  - Enhanced `rspamd-configmap.yaml` with new logging and worker configurations for Rspamd.

**Important Files:**
- `mail/postfix-configMap.yaml`
- `mail/postfix-deployment.yaml`
- `mail/rspamd-deployment.yaml`
- `mail/rspamd-configmap.yaml`

**Breaking Changes:**
- Removal of Rspamd-related configurations from Postfix may affect existing setups relying on those configurations.

## 2023-12-06 – `5c4b847` by Andrey Bondarenko
- **New Feature**: Added MySQL CLI deployment configuration.
  - **File**: `myqsl/cli-deployment.yaml`
  - **Deployment**: Configured with resource limits, environment variables, and volume mounts.
  - **Secrets**: Utilizes Kubernetes secrets for MySQL root password.
  - **Volumes**: References persistent volume claims for backup and MySQL storage.
  - **Image**: Pulls from private registry `registry.andreybondarenko.com/mysql-cli:latest`.

## 2023-12-06 – `cd90915` by Andrey Bondarenko
- **Resource Configuration**
  - Increased memory limit from `128Mi` to `1024Mi` in `registry/registry-values.yaml`.

- **Persistence Settings**
  - Changed persistence `accessMode` from `ReadWriteOnce` to `ReadWriteMany` in `registry/registry-values.yaml`.

**Note:** Ensure compatibility with existing deployments due to changes in memory limits and access modes.

## 2023-12-10 – `155d480` by Andrey Bondarenko
- **Alertmanager Configuration**
  - Added `--web.external-url` to `alertmanager-depliyment.yaml` for external access.
  - Added `externalIPs` to `alertmanagetr-service.yaml` for service exposure.

- **Prometheus Configuration**
  - Added `--web.external-url` to `prometheus-deployment.yaml` for external access.
  - Added `externalIPs` to `prometheus-service.yaml` for service exposure.

- **Alert Rules Update**
  - Updated alert rules in `config-map.yaml`:
    - Renamed alert group to "alerts".
    - Added alerts for High Node Memory, High Swap Usage, High Load Average, and High Filesystem Usage with severity set to "mail".

## 2023-12-10 – `c420447` by Andrey Bondarenko
- **Minecraft PVC Update**
  - Increased storage request from 300Mi to 500Mi in `minecraft/minecraft-pvc.yaml`.

- **Unifi Deployment Configuration**
  - Added `replicas: 1` to `unifi/unifi-deployment.yaml`.

## 2023-12-13 – `b5fd109` by Andrey Bondarenko
- **New Feature**: Added new JSON configuration file for Grafana dashboard.
  - **File**: `metrix/graphana/Cluster load-1702377122035.json`
  - Contains panels for monitoring cluster load, memory usage, and annotations.

- **Dashboard Panels**:
  - **Load Average**: Displays 1-minute load average using Prometheus data source.
  - **Memory Usage**: Shows memory usage percentage calculated from total, free, and cached memory.

- **Configuration Details**:
  - Each panel includes customizable options for legends, tooltips, and thresholds.
  - Utilizes Prometheus as the data source with specific queries for metrics.

- **Breaking Change**: New dashboard structure may require updates to existing Grafana configurations to integrate with the new JSON file.

## 2023-12-13 – `a357eda` by Andrey Bondarenko
- **Alert Threshold Updates**:
  - Increased memory usage alert threshold from 75% to 85% for `High Node Memory` and `High Swap Usage`.
  - Raised load average alert threshold from 5 to 6 for `High Load Average`.
  - Updated filesystem usage alert threshold from 75% to 85% for `High Filesystem Usage`.

- **File Modified**:
  - `metrix/kubernetes-prometheus/config-map.yaml`

## 2023-12-13 – `82b4552` by Andrey Bondarenko
- **Configuration Update**
  - Added `externalIPs` field with value `192.168.1.101` to `metrix/graphana/service.yaml`.

- **Service Type**
  - Maintained `LoadBalancer` type for Grafana service.

## 2023-12-19 – `629869f` by Andrey Bondarenko
- **Grafana Configuration:**
  - Removed `metrix/graphana/Cluster load-1702377122035.json` file.

- **Kube-State Metrics:**
  - Updated configurations in `metrix/kube-state-metrics-configs/`:
    - Modified `cluster-role-binding.yaml`, `cluster-role.yaml`, `deployment.yaml`, `service-account.yaml`, and `service.yaml`.

- **Kubernetes Node Exporter:**
  - Updated `metrix/kubernetes-node-exporter/`:
    - Adjusted `daemonset.yaml` and `service.yaml`.

- **Kubernetes Prometheus:**
  - Enhanced configurations in `metrix/kubernetes-prometheus/`:
    - Updated `alert.yaml`, `alertmanager-configmap.yaml`, `alertmanager-deployment.yaml`, `alertmanager-service.yaml`, `clusterRole.yaml`, `config-map.yaml`, `ingress.yaml`, `prometheus-deployment.yaml`, `prometheus-pvc.yaml`, and `prometheus-service.yaml`.

- **Documentation:**
  - Updated README files in `metrix/kube-state-metrics-configs/` and `metrix/kubernetes-node-exporter/`.

## 2023-12-19 – `3d91101` by Andrey Bondarenko
- **Removal of MySQL Resources:**
  - Deleted `cli-deployment.yaml`, `migrate.yaml`, `mysql-deployment.yaml`, `mysql-pvc.yaml`, and `mysql-service.yaml` from `myqsl/`.
  - All MySQL-related deployments, services, and persistent volume claims have been removed, indicating a significant change in the database management approach.

- **Impact:**
  - This commit introduces breaking changes by removing essential Kubernetes resources for MySQL, which may affect existing deployments relying on these configurations.

## 2023-12-19 – `865e335` by Andrey Bondarenko
- **Configuration Update**
  - Added `secure_ip = "0.0.0.0/0";` to `worker "controller"` in `mail/rspamd-configmap.yaml`.

**Note:** This change may expose the controller to all IPs; review security implications.

## 2023-12-19 – `6f74309` by Andrey Bondarenko
- **Deployment Configuration**:
  - Added `unifi-poller-deployment.yaml` for deploying the Unifi Poller application.
  - Configured container with environment variables for Unifi credentials and resource limits.

- **Service Configuration**:
  - Added `unifi-poller-service.yaml` to expose the Unifi Poller on port 9130.

- **Namespace**:
  - Both resources are deployed in the `unifi` namespace.

## 2023-12-19 – `b974461` by Andrey Bondarenko
- **Metrics Configuration**:
  - Enabled metrics collection in `registry/registry-values.yaml`.
  - Set metrics path to `/metrics`.
  - Enabled `serviceMonitor` for Prometheus integration.

- **Debug Configuration**:
  - Enabled Prometheus metrics for debug configuration.

## 2023-12-19 – `12565b1` by Andrey Bondarenko
- **File Changes:**
  - Deleted `redis/redis-.yaml`.
  - Added `redis/redis-values.yaml` with resource configurations for master and replica.

- **Resource Configuration:**
  - Master and replica resource requests and limits defined in `redis-values.yaml`:
    - Master: CPU requests 61m, limits 300m; Memory requests and limits 100Mi.
    - Replica: CPU requests 81m, limits 300m; Memory requests and limits 100Mi.

- **Breaking Change:**
  - Removal of `redis-.yaml` may affect existing configurations relying on this file.

## 2023-12-19 – `9909bf0` by Andrey Bondarenko
- **New Features:**
  - Added `redis-exporter` Deployment in `redis/redis-exporter-deployment.yaml`.
  - Added `redis-exporter` Service in `redis/redis-exporter-service.yaml`.

- **Configuration:**
  - Deployment configured with Redis connection details and resource limits.
  - Service exposes port 9121 for the `redis-exporter`.

- **Namespace:**
  - Both resources are deployed in the `redis` namespace.

## 2023-12-19 – `65f649e` by Andrey Bondarenko
- **Configuration Updates**:
  - Removed `images.tag` configuration from `postgres/values.yaml`.
  - Added `auth` section with `username` and `database` fields.
  - Introduced `persistence` settings with `storageClass` and `size`.
  - Enabled `metrics` collection.

- **File Affected**:
  - `postgres/values.yaml` updated with significant configuration changes.

## 2023-12-19 – `9732c8a` by Andrey Bondarenko
- **New Features**
  - Added `mongo-exporter` Deployment in `mongo/mongo-exporter-deployment.yaml`.
  - Introduced `mongo-exporter` Service in `mongo/mongo-exporter-service.yaml`.

- **Configuration**
  - Deployment configured with Percona MongoDB Exporter image (`percona/mongodb_exporter:0.40`).
  - Service exposes port `9216` for the exporter.

- **Namespace**
  - Both resources are deployed in the `db` namespace.

## 2023-12-19 – `c6f5d7c` by Andrey Bondarenko
- **New Feature**: Added `cert-manager-exporter-service.yaml` to define a new Kubernetes Service for the cert-manager.
- **Service Configuration**:
  - Service named `cert-manager-exporter` created in the `cert-manager` namespace.
  - Exposes port `9402` for the exporter.
- **Labels**: Added label `app: cert-manager` for service identification.

## 2023-12-19 – `d3030ab` by Andrey Bondarenko
- **New Features:**
  - Added new Grafana dashboard configuration in `metrics/graphana/Cluster load-1702377122035.json` for monitoring cluster load and memory usage.

- **Updates:**
  - Enhanced `metrics/graphana/graphana.yaml` and `metrics/kubernetes-prometheus/alertmanager-depliyment.yaml` for improved alerting and monitoring capabilities.
  - Updated service configurations in `metrics/kubernetes-prometheus/prometheus-service.yaml` and `metrics/kubernetes-node-exporter/service.yaml`.

- **Documentation:**
  - Revised README files in `metrics/kube-state-metrics-configs/README.md` and `metrics/kubernetes-node-exporter/README.md` to reflect new features and usage instructions.

- **Breaking Changes:**
  - Ensure compatibility with updated Prometheus configurations in `metrics/kubernetes-prometheus/` as new metrics and alerting rules have been introduced.

## 2023-12-19 – `f76ec0f` by Andrey Bondarenko
- **New ConfigMap Creation**
  - Added `metrics/kubernetes-prometheus/config-map.yaml` for Prometheus configuration.

- **Alert Rules Defined**
  - Configured alert rules for high memory, swap, load average, and filesystem usage.

- **Scrape Configurations**
  - Defined multiple scrape jobs for MySQL, PostgreSQL, Redis, MongoDB, and others with specific intervals and targets.

- **Kubernetes Integration**
  - Included Kubernetes service discovery for nodes and pods, with relabeling configurations for metrics collection.

- **Global Settings**
  - Set global scrape and evaluation intervals to 5 seconds.

## 2023-12-19 – `1a4d228` by Andrey Bondarenko
- **New Resources**:
  - Added `ConfigMap` for MySQL exporter configuration (`mysql/mysqld-exporter-configmap.yaml`).
  - Introduced `Deployment` for MySQL exporter with environment variables and resource limits (`mysql/mysqld-exporter-deployment.yaml`).
  - Created `Service` to expose MySQL exporter on port 9104 (`mysql/mysqld-exporter-service.yaml`).

- **Configuration Details**:
  - ConfigMap includes `.my.cnf` with database connection details.
  - Deployment references a secret for MySQL root password and sets up volume mounts for configuration.

- **Namespace**: All resources are deployed in the `db` namespace.

## 2023-12-19 – `d30a874` by Andrey Bondarenko
- **New Deployments:**
  - Added `mysql-cli` Deployment in `mysql/cli-deployment.yaml` for CLI access with persistent storage.
  - Introduced `mysql` StatefulSet in `mysql/mysql-deployment.yaml` for MySQL database management.

- **Persistent Storage:**
  - Created PersistentVolumeClaim in `mysql/mysql-pvc.yaml` for MySQL storage with `longhorn` storage class.

- **Service Configuration:**
  - Added `mysql` Service in `mysql/mysql-service.yaml` for internal access to the MySQL database.

- **Environment Variables:**
  - Configured environment variables for MySQL root password and host in both deployments.

- **Resource Management:**
  - Defined resource limits and requests for MySQL and CLI containers to optimize performance.

## 2023-12-19 – `b66ae95` by Andrey Bondarenko
- **Removal**: Deleted `nextcloud/migrate.yaml` file, which defined a migration Pod for Nextcloud.
- **Impact**: This change removes the configuration for volume migration, potentially affecting deployment or migration processes.

## 2023-12-27 – `9ac7fcf` by Andrey Bondarenko
- **Storage Class Updates**
  - Changed `storageClassName` from `nfs-client` to `longhorn` in multiple PVC files:
    - `clamav/clamav-pvc.yaml`
    - `cron/conduit-pvc.yaml`
    - `cron/mail-pvc.yaml`
    - `cron/minecraft-pvc.yaml`
    - `cron/mysql-pvc.yaml`
    - `cron/postgres-pvc.yaml`
    - `mail/rspamd-pvc.yaml`
    - `metrics/graphana/pvc.yaml`
    - `minio-single/minio-single-pvc.yaml`

- **MinIO PVC Name Change**
  - Updated PVC name from `minio-nfs` to `minio-lh` in `minio-single/minio-single-pvc.yaml`.

- **Storage Size Adjustment**
  - Reduced storage request from `100Gi` to `30Gi` in `minio-single/minio-single-pvc.yaml`.

## 2023-12-27 – `bdce675` by Andrey Bondarenko
- **Service IP Changes:**
  - Updated `externalIPs` for multiple services to `192.168.1.111` in:
    - `mail/dovecot-tls-service.yaml`
    - `mail/rspamd-service.yaml`
    - `metrics/graphana/service.yaml`
    - `minecraft/minecraft-service.yaml`
    - `unifi/unifi-service.yaml`
  - Added `externalIPs` for `minio-single/minio-single-service.yaml` set to `192.168.1.112`.

- **Node Name Updates:**
  - Changed `nodeName` in `mongo/mongo-deployment.yaml` from `worker-04.k8s.my.lan` to remove it.
  - Updated `nodeName` in `unifi/unifi-deployment.yaml` from `worker-01.k8s.my.lan` to `m.k8s.my.lan`.

- **File Modifications:**
  - Modified 8 YAML configuration files across mail, metrics, Minecraft, MinIO, MongoDB, and Unifi services.

## 2023-12-27 – `ead604d` by Andrey Bondarenko
- **New Resources**:
  - Added `postgres-exporter` Deployment in `postgres/postgres-exporter.yaml`.
  - Added `postgres-exporter` Service in `postgres/postgres-exporter-service.yaml`.

- **Configuration**:
  - Deployment configured with environment variables for PostgreSQL connection.
  - Resource limits set for memory (128Mi) and CPU (500m).

- **Namespace**:
  - Both resources are deployed in the `db` namespace.

## 2023-12-27 – `e1ce3cf` by Andrey Bondarenko
- **Kubernetes Node Exporter**:
  - Increased CPU limit from 200m to 1000m and memory limit from 100Mi to 120Mi in `metrics/kubernetes-node-exporter/daemonset.yaml`.

- **Prometheus Service**:
  - Updated external IP from `192.168.1.101` to `192.168.111` in `metrics/kubernetes-prometheus/prometheus-service.yaml`.

- **MinIO Deployment**:
  - Changed image tag to `latest` removal in `minio-single/minio-single-deployment.yaml`.
  - Increased CPU limit from 1000m to 3000m and updated PVC claim name from `minio-nfs` to `minio-lh`.

- **Redis Exporter**:
  - Increased CPU limit from 500m to 1200m in `redis/redis-exporter-deployment.yaml`.

- **TinyRSS Configuration**:
  - Increased CPU limit from 200m to 800m and memory limit from 100Mi to 200Mi in `ttrss/ttrss-values.yaml`.

**Breaking Changes**:
- MinIO PVC claim name change may affect existing deployments.

## 2023-12-27 – `d9ed6b9` by Andrey Bondarenko
- **Prometheus Configuration Updates**
  - Added new scrape jobs for `postgres-local` and `rapi-local` in `metrics/kubernetes-prometheus/config-map.yaml`.
  - Set `scrape_interval` and `scrape_timeout` to 45s and 30s respectively for both jobs.
  - Configured targets for `postgres-local` and `rapi-local` metrics scraping.

## 2023-12-27 – `7c82a9e` by Andrey Bondarenko
- **New Configuration File**
  - Added `mastodon/mastodon-values.yaml` for Helm chart configuration.

- **Image Configuration**
  - Set up image repository and tag options for Mastodon deployment.

- **Admin User Creation**
  - Enabled automatic creation of an initial admin user with specified credentials.

- **Cron Jobs**
  - Configured cron job for weekly media cleanup.

- **Persistence Settings**
  - Defined storage requirements for assets (10Gi) and system (100Gi) with ReadWriteMany access mode.

- **SMTP Configuration**
  - Added SMTP settings for email notifications, including server details and authentication method.

## 2023-12-27 – `cb6035c` by Andrey Bondarenko
- **Nextcloud Configuration Updates:**
  - Updated `www.conf` in `nextcloud/php-configmap.yaml`:
    - Changed user/group to `www-data`.
    - Set `pm` to `dynamic` with increased limits (max_children: 240, start_servers: 24).
    - Enabled `opcache` with new settings.
    - Set `memory_limit` to `-1` for unlimited memory.
  - Added `www.conf` mount in `nextcloud/php-deployment.yaml`.

- **Resource Adjustments:**
  - Increased memory limit for Nextcloud deployment from `2145Mi` to `6145Mi`.
  - Updated WordPress deployment resource limits:
    - CPU limit increased from `300m` to `1300m`.
    - Memory limit increased from `126Mi` to `1024Mi`.

- **Breaking Changes:**
  - Nextcloud now requires `www-data` user permissions.
  - Increased resource requirements for both Nextcloud and WordPress deployments.

## 2023-12-27 – `7e78880` by Andrey Bondarenko
- **Added ServiceMonitor**: Introduced `longhorn-prometheus-servicemonitor` in `longhorn/longhorn-service-monitor.yaml`.
- **Monitoring Integration**: Configured to monitor `longhorn-manager` app in the `longhorn-system` namespace.
- **Endpoints Defined**: Specified endpoint for the `manager` port.

## 2023-12-27 – `5d7c0e0` by Andrey Bondarenko
- **Kubernetes Configuration**
  - Added `mysql/migrate.yaml` for database migration pod configuration.
  - Defined pod with `nginx:stable-alpine` image, volume mounts for source and destination.
  - Configured persistent volume claims: `mysql-pv-claim` and `mysql-lh`.

- **Container Setup**
  - Set `imagePullPolicy` to `IfNotPresent` for efficient image management.
  - Exposed container port 80 for potential service access.

**Note:** This commit introduces a new configuration file; ensure compatibility with existing Kubernetes resources.

## 2023-12-27 – `06c2917` by Andrey Bondarenko
- **Documentation Updates**
  - Added Mastodon and Prometheus operator to project overview in `README.md`.
  - Updated ToDo to reflect moving secrets to K8S secrets.

- **Configuration Changes**
  - Updated `postgres-exporter.yaml` to use K8S secret for PostgreSQL password (`pg-pass`).
  - Refactored `DATA_SOURCE_NAME` to utilize environment variables for improved security.

**Breaking Change**: PostgreSQL password handling now requires K8S secret management.

## 2023-12-29 – `37638e2` by Andrey Bondarenko
- **Prometheus Configuration Updates**
  - Renamed `prometheus.yml` to `prometheus.yaml.tmpl` in `config-map.yaml`.
  - Updated Prometheus deployment to use new config path: `--config.file=/etc/prometheus-shared/prometheus.yaml`.
  - Added lifecycle and storage retention options in `prometheus-deployment.yaml`.

- **Thanos Integration**
  - Introduced Thanos components: `thanos-compactor.yaml`, `thanos-queuer.yaml`, and respective PVCs.
  - Configured Thanos sidecar in Prometheus deployment with objstore configuration.
  - Added resource limits and requests for Thanos components.

- **Persistent Volume Claims (PVC) Changes**
  - Updated PVC names from `prometheus-nfs` to `prometheus-lh` and adjusted storage class to `longhorn`.
  - Created new PVC for Thanos compactor with `longhorn` storage class.

- **File Changes**
  - Added `objstore.yml` to `.gitignore`.
  - New files created for Thanos components and PVCs in the `thanos` directory.

- **Breaking Changes**
  - Prometheus configuration file path change may require updates to existing deployments.
  - PVC name and storage class changes may affect existing storage configurations.

## 2023-12-29 – `b032190` by Andrey Bondarenko
- **Documentation Updates**
  - Removed references to future experiments for Minio and Elasticsearch in `README.md`.
  - Added Prometheus Thanos to the list of applications.

- **ToDo Section**
  - Removed the task to move secrets to K8S secrets from `README.md`.

## 2023-12-29 – `50ca19a` by Andrey Bondarenko
- **Configuration Update:**
  - Changed `DATA_SOURCE_NAME` in `mysql/mysqld-exporter-deployment.yaml` to use environment variable `$MYSQL_ROOT_PASSWORD` instead of hardcoded password.

- **File Affected:**
  - `mysql/mysqld-exporter-deployment.yaml`

## 2023-12-29 – `b7aca63` by Andrey Bondarenko
- **New Feature**
  - Added `secret.yaml.asc` containing PGP encrypted secrets.

- **File Changes**
  - `secret.yaml.asc`: New file created with 103 lines of encrypted content.

- **Security**
  - Introduced PGP encryption for sensitive data, enhancing security posture.

## 2023-12-29 – `20809fe` by Andrey Bondarenko
- **Resource Configuration**:
  - Updated CPU limit from `500m` to `1000m` in `unifi/unifi-poller-deployment.yaml`.

## 2023-12-30 – `91cb21e` by Andrey Bondarenko
- **Service Updates:**
  - Updated external IP for `alertmanagetr-service.yaml` from `192.168.1.101` to `192.168.1.111`.
  - Added new `thanos-querier` service in `thanos/thanos-queuer-service.yaml` with external IP `192.168.1.113`.
  - Refactored `thanos-storage-gateway-service.yaml`:
    - Renamed service from `thanos-sidecar` to `thanos-store-gateway`.
    - Added HTTP port `10902` alongside existing gRPC port `10901`.

- **File Changes:**
  - `metrics/kubernetes-prometheus/alertmanagetr-service.yaml`
  - `thanos/thanos-queuer-service.yaml` (new)
  - `thanos/thanos-storage-gateway-service.yaml` (refactored)

- **Breaking Changes:**
  - Service name change from `thanos-sidecar` to `thanos-store-gateway` may affect existing configurations.

## 2023-12-30 – `db85a13` by Andrey Bondarenko
- **Resource Configuration**
  - Updated MySQL deployment memory limit from 800Mi to 1200Mi in `mysql/mysql-deployment.yaml`.

## 2023-12-30 – `80a38d1` by Andrey Bondarenko
- **Alert Configuration Updates**:
  - Modified thresholds and durations for existing alerts:
    - High Node Memory: threshold changed from 85% to 80%, duration from 10m to 3m.
    - High Swap Usage: threshold changed from 85% to 5%, duration from 10m to 3m.
    - High Load Average: duration changed from 10m to 3m.
    - High Filesystem Usage: threshold changed from 85% to 75%, duration from 10m to 3m.

- **New Alerts Added**:
  - Introduced alerts for database availability:
    - MongoDB: `mongodb_up < 1` for 1m.
    - MySQL: `mysql_up < 1` for 1m.
    - PostgreSQL (k8s): `pg_up{instance="postgres-exporter.db.svc.cluster.local:9187", job="postgres-local"} < 1` for 1m.
    - PostgreSQL (apps): `pg_up{instance="postgres-postgresql-metrics.db.svc.cluster.local:9187", job="postgres"} < 1` for 1m.

- **File Affected**:
  - `metrics/kubernetes-prometheus/config-map.yaml`

## 2023-12-30 – `b131228` by Andrey Bondarenko
- **Alerts Added**:
  - Introduced multiple new alerts in `metrics/kubernetes-prometheus/config-map.yaml`:
    - `KubeJobFailed`: Monitors job completion failures.
    - `CPUThrottlingHigh`: Detects elevated CPU throttling.
    - `KubePersistentVolumeFillingUp`: Alerts for persistent volumes nearing capacity (two variations for different thresholds).
    - `KubePodCrashLooping`: Identifies pods in a crash loop state.
    - `KubePodNotReady`: Flags pods not ready for over 15 minutes.

- **File Modified**:
  - `metrics/kubernetes-prometheus/config-map.yaml` updated with new alert configurations.

## 2023-12-30 – `6c6e2ba` by Andrey Bondarenko
- **Mongo Deployment Updates:**
  - Increased memory limit from 300Mi to 600Mi in `mongo/mongo-deployment.yaml`.

- **Mongo Exporter Enhancements:**
  - Updated memory limit from 128Mi to 256Mi in `mongo/mongo-exporter-deployment.yaml`.

No breaking changes identified.

## 2023-12-30 – `77230ae` by Andrey Bondarenko
- **Added Alerts in Prometheus Config:**
  - Introduced `KubeNodeNotReady` alert for non-ready nodes.
  - Added `KubeNodeUnreachable` alert for unreachable nodes.
  - Implemented `TargetDown` alert for unreachable targets.

- **File Modified:**
  - Updated `metrics/kubernetes-prometheus/config-map.yaml` with new alert configurations.

## 2024-01-01 – `48cbeb8` by Andrey Bondarenko
- **Configuration Update:**
  - Updated `UP_UNIFI_DEFAULT_URL` in `unifi/unifi-poller-deployment.yaml` from `https://192.168.1.102:8443` to `https://192.168.1.111:8443`.

## 2024-01-02 – `4052dbe` by Andrey Bondarenko
- **Documentation Updates**
  - Updated `README.md` to include Prometheus Loki and Promtail for log aggregation and delivery.

- **New Configuration Files**
  - Added `loki/promtail.yaml` for Promtail DaemonSet configuration.
  - Introduced `loki/values.yaml` for Loki configuration settings.

- **Kubernetes Resources**
  - Created Kubernetes resources for Promtail:
    - DaemonSet, ConfigMap, ClusterRole, ServiceAccount, and ClusterRoleBinding defined in `promtail.yaml`.

- **Breaking Changes**
  - New dependencies on Prometheus Loki and Promtail; ensure compatibility with existing setups.

## 2024-01-03 – `ecfd0c4` by Andrey Bondarenko
- **Alert Configuration Updates**:
  - Increased threshold for **High Swap Usage** alert from **5%** to **25%** in `metrics/kubernetes-prometheus/config-map.yaml`.
  - Raised threshold for **High Load Average** alert from **10** to **12** in the same file.

## 2024-01-03 – `a730ab1` by Andrey Bondarenko
- **Thanos Configuration Updates:**
  - Removed `Service` definition for `thanos-querier` in `thanos/thanos-queuer.yaml`.

- **Promtail Configuration:**
  - No changes reported in `loki/promtail.yaml`.

- **General:**
  - Ensure service dependencies are updated due to the removal of `thanos-querier` service.

## 2024-01-03 – `ff546a4` by Andrey Bondarenko
- **Deployment Configuration**:
  - Added `lighttpd-deployment.yaml` for camera application deployment with resource limits and environment variables.

- **Ingress Setup**:
  - Introduced `lighttpd-ingress.yaml` to manage ingress for `cctv.andreybondarenko.com`, including SSL configuration and path rewriting.

- **Service Definition**:
  - Created `lighttpd-service.yaml` to expose the camera application on port 80.

- **Namespace**: All resources are defined under the `camera` namespace.

- **Important Note**: Ensure the secret `camera` for the password and the TLS secret `letsencrypt-prod` are created prior to deployment.

## 2024-01-03 – `4e3b0d4` by Andrey Bondarenko
- **Resource Configuration Updates**:
  - Increased CPU limit from `100m` to `1000m` in `registry/registry-values.yaml`.
  - Increased persistent storage size from `4Gi` to `10Gi`.

- **File Affected**:
  - `registry/registry-values.yaml`

## 2024-01-07 – `911c7a7` by Andrey Bondarenko
- **Persistent Volume Claims:**
  - Changed `clamav` PVC access mode from `ReadWriteOnce` to `ReadWriteMany`.
  - Updated `conduit` PVC name from `matrix-lh` to `matrix1-lh` and increased storage request from `500Mi` to `2Gi`.
  - Renamed `minecraft` PVC from `minecraft-lh` to `minecraft1-lh` and increased storage request from `500Mi` to `1000Mi`.

- **Deployment Changes:**
  - Updated `conduit` deployment to use new PVC name `matrix1-lh`.
  - Modified `minecraft` deployment to use image `itzg/minecraft-server:latest` and added environment variables for custom server configuration.
  - Adjusted resource requests for `mysqld-exporter` and `postgres` deployments.

- **Configuration Updates:**
  - Set `mastodon` admin creation to `false`.
  - Reduced `loki` retention period from `744h` to `372h`.
  - Updated `postgres` resource limits and persistence size from `1Gi` to `8Gi`.

- **Ingress Fix:**
  - Corrected service name in `ttrss` ingress from `my-tt-rss` to `may-tt-rss`.

- **Breaking Changes:**
  - PVC name changes may require updates in dependent resources.

## 2024-01-07 – `10ee2db` by Andrey Bondarenko
- **Secret Management**
  - Updated PGP message in `secret.yaml.asc` with new encrypted content.
  - Removed old PGP message data, ensuring sensitive information is replaced.

- **File Changes**
  - `secret.yaml.asc` modified to enhance security with updated encryption.

## 2024-01-07 – `5a49e6f` by Andrey Bondarenko
- **Resource Limits Update**
  - Increased memory limit for `redis/cli-deployment.yaml` from 128Mi to 228Mi.
  - Increased CPU limit for `redis/cli-deployment.yaml` from 500m to 1000m.
  - Increased memory limit for `redis/redis-exporter-deployment.yaml` from 128Mi to 228Mi.

- **File Changes**
  - Modified `redis/cli-deployment.yaml` and `redis/redis-exporter-deployment.yaml`.

- **Breaking Change**
  - Resource limits have been adjusted; ensure compatibility with existing resource allocation.

## 2024-01-09 – `1673db4` by Andrey Bondarenko
- **New Feature: FTP Service Deployment**
  - Added `vsftpd` deployment in `camera` namespace with a PersistentVolumeClaim for FTP storage.
  - Configured environment variables for passive FTP settings and user credentials.
  - Specified resource limits for the `vsftpd` container.

- **Service Configuration**
  - Created a `Service` for `vsftpd` exposing ports 20, 21, 21110, and 21111 with external IP `192.168.1.111`.

- **File Added**
  - New file: `camera/vsftpd.yaml` containing the complete configuration for the FTP service.

## 2024-01-11 – `31b1087` by Andrey Bondarenko
- **Documentation Updates**
  - Added an image of the ARM-based K3S cluster to `README.md`.
  - Expanded "Works" section to include:
    - Live RTSP viewer for Foscam CCTV camera.
    - FTP server for Foscam CCTV camera.
  - Updated "TODO" section with plans for Vault and Plex.

## 2024-01-11 – `0314993` by Andrey Bondarenko
- **Documentation Updates**
  - Added new image of ARM-based K3s cluster with 4 OrangePI 5 nodes in `README.md`.
  - Updated existing image caption for ARM-based K3s cluster with 4 OrangePI 4LTS nodes in `README.md`.

## 2024-01-17 – `7c5c773` by Andrey Bondarenko
- **Prometheus & Alertmanager Updates:**
  - Updated external URLs in `alertmanager-depliyment.yaml` and `prometheus-deployment.yaml` from `http://master.k8s.my.lan` to `http://m.k8s.my.lan`.
  - Simplified alert expressions in `config-map.yaml` for memory and filesystem usage alerts.

- **Nextcloud Resource Adjustments:**
  - Increased CPU limits in `nginx-deployment.yaml` from `350m` to `3000m` and memory from `100Mi` to `512Mi`.
  - Updated PHP deployment memory limits in `php-deployment.yaml` from `6145Mi` to `8145Mi`.
  - Added `opcache.jit_buffer_size` to `php-configmap.yaml`.

- **File Changes:**
  - Modified files: `alertmanager-depliyment.yaml`, `config-map.yaml`, `prometheus-deployment.yaml`, `nginx-deployment.yaml`, `php-configmap.yaml`, `php-deployment.yaml`.

## 2024-01-18 – `4e4a6c6` by Andrey Bondarenko
- **Deployment Configuration**
  - Added `plex-deployment.yaml` for Plex deployment with resource requests/limits and environment variables.
  - Configured container ports for Plex service.

- **Persistent Volume Claims**
  - Introduced `plex-pvc.yaml` with three PVCs: `plex-conf-lh`, `plex-conf-old`, and `plex-lib-lh`, each with 100Gi storage requests.

- **Service Definition**
  - Created `plex-service.yaml` to expose Plex service on multiple ports, including UDP protocols and external IP configuration.

- **Namespace**
  - All resources are defined under the `plex` namespace.

## 2024-01-19 – `4902b8f` by Andrey Bondarenko
- **Documentation Update**
  - Added new image to `README.md` showcasing the project in a rack.

## 2024-01-19 – `4ea68e4` by Andrey Bondarenko
- **Database Configuration Changes:**
  - Switched database from MySQL to PostgreSQL in `bitwarden/bitwarden-deployment.yaml`.
  - Updated database connection details (server, username, password secret) accordingly.

- **Persistent Volume Claims (PVC) Adjustments:**
  - Changed access mode from `ReadWriteMany` to `ReadWriteOnce` in `bitwarden/bitwarden-data-pvc.yaml` and `bitwarden/bitwarden-logs-pvc.yaml`.

- **Important Files Modified:**
  - `bitwarden/bitwarden-data-pvc.yaml`
  - `bitwarden/bitwarden-deployment.yaml`
  - `bitwarden/bitwarden-logs-pvc.yaml`

- **Breaking Change:**
  - Database migration required due to change from MySQL to PostgreSQL.

## 2024-01-19 – `afdb57a` by Andrey Bondarenko
- **Alert Configuration Updates**
  - Modified `High Load Average` alert threshold: changed expression from `node_load5 > 12` to `node_load5 > 20`.
  - Increased alert duration from `3m` to `5m`.

- **Job Configuration Changes**
  - Removed `rapi-local` job configuration from `metrics/kubernetes-prometheus/config-map.yaml`.

- **File Affected**
  - `metrics/kubernetes-prometheus/config-map.yaml`

## 2024-01-20 – `b0b9458` by Andrey Bondarenko
- **Deployment Configuration Updates**:
  - Updated `plex/plex-deployment.yaml` to include comments clarifying the usage of the `image` and `env` variables.
  - Added note that `PLEX_CLAIM` is valid for 4 minutes.
  - Clarified that `ADVERTISE_IP` does not function as intended.

## 2024-02-09 – `7539eb1` by Andrey Bondarenko
- **Storage Configuration**
  - Increased PVC storage request from **8Gi** to **200Gi** in `thanos/thanos-compactor-pvc.yaml`.

- **Retention Policy Update**
  - Adjusted retention settings in `thanos/thanos-compactor.yaml`:
    - Changed `--retention.resolution-raw` from **3d** to **2d**.
    - Changed `--retention.resolution-5m` from **15d** to **10d**.

No breaking changes noted.

## 2024-02-09 – `5b6b2c3` by Andrey Bondarenko
- **New Configuration Files**:
  - Added `vault/spc-vault-database.yaml`: Defines `SecretProviderClass` for Vault integration.
  - Added `vault/values.yaml`: Specifies container resource limits and syncSecret configuration.
  - Added `vault/webapp-pod.yaml`: Configures a Pod for the web application with secrets management.

- **Vault Integration**:
  - Configured Vault address and role for database secrets retrieval in `spc-vault-database.yaml`.

- **Resource Management**:
  - Set CPU limits for `node-driver-registrar` in `values.yaml`.

- **Secrets Management**:
  - Implemented secrets volume mount in `webapp-pod.yaml` for secure access to Vault secrets.

## 2024-02-09 – `ca08a2f` by Andrey Bondarenko
- **Added Monitoring Job:**
  - Introduced `kubernetes-longhorn-manager` job configuration in `metrics/kubernetes-prometheus/config-map.yaml`.
  - Configures Kubernetes service discovery for Longhorn Manager pods.
  - Sets metrics path to `/metrics` and updates target address to port `9500`.

## 2024-02-09 – `aae19a9` by Andrey Bondarenko
- **Storage Configuration Update**
  - Increased storage request from 500Mi to 1500Mi in `clamav/clamav-pvc.yaml`.

## 2024-02-09 – `2eaa470` by Andrey Bondarenko
- **Documentation Update**
  - Changed "Prometheus Loki" to "Grafana Loki" in README.md.
  - Added "Plex" to the list of components in README.md.
  - Removed "Plex that lives on-prem at the moment" from TODO section in README.md.

## 2024-02-09 – `6e01330` by Andrey Bondarenko
- **Documentation Updates:**
  - Enhanced `README.md` with additional details on Minio storage configuration and updated `vm.swappiness` value.

- **New Deployment Guides:**
  - Added `bitwarden/README.md` for Bitwarden deployment instructions.
  - Introduced `collabora/README.md` for Collabora deployment via Helm.
  - Created `postgres/README.md` for PostgreSQL deployment instructions.
  - Added `registry/README.md` for Docker registry deployment.
  - Included `ttrss/README.md` for TT-RSS deployment via Helm.

- **File Structure Changes:**
  - Multiple new README files created for various services, enhancing clarity on deployment processes.

## 2024-02-09 – `041656c` by Andrey Bondarenko
- **New Documentation:**
  - Added `camera/README.md` detailing setup for Foscam dome camera with RTSP streaming and FTP integration.

- **Deprecation Notice:**
  - Added `rsyslog/README.md` indicating that Rsyslog is deprecated in favor of Loki.

## 2024-02-09 – `756fe6f` by Andrey Bondarenko
- **Documentation Updates**
  - Corrected typo in `redis/README.md`: changed "defaul!" to "defaults!".
  - Enhanced `registry/README.md` with additional notes on:
    - Memory and CPU requirements for large layers.
    - Ingress upload limits.
    - Password hash file format clarification (.htpasswd).

## 2024-02-17 – `ae6bf1e` by Andrey Bondarenko
- **Cron Job Update**
  - Changed schedule for `nextcloud` cron job from `*/15 * * * *` to `15 * * * *` in `cron/cronjob-nextcloud.yaml`.

## 2024-02-17 – `cb09049` by Andrey Bondarenko
- **Configuration Changes:**
  - Removed `rspamd-local` persistent volume claim from `mail/postfix-deployment.yaml`.

- **Container Updates:**
  - No changes to the `postfix-mail` container configuration; image remains `registry.andreybondarenko.com/postfix:latest`.

## 2024-02-17 – `7c936a0` by Andrey Bondarenko
- **Metrics Configuration:**
  - Removed `turris` job configuration from `metrics/kubernetes-prometheus/config-map.yaml`.

- **Unifi Poller Deployment:**
  - Updated `UP_UNIFI_DEFAULT_URL` to `https://192.168.1.1:443` in `unifi/unifi-poller-deployment.yaml`.
  - Added `UP_UNIFI_DEFAULT_SAVE_DPI` environment variable with value `"true"` in `unifi/unifi-poller-deployment.yaml`.

## 2024-02-17 – `3dbfb70` by Andrey Bondarenko
- **Documentation Update**
  - Updated NFS server address in `README.md` from `rapi.my.lan` to `w7.k8s.my.lan`.

## 2024-02-17 – `c079071` by Andrey Bondarenko
- **Thanos Compactor Configuration:**
  - Updated retention settings:
    - Changed `--retention.resolution-raw` from `2d` to `31d`
    - Changed `--retention.resolution-5m` from `10d` to `90d`

- **Thanos Queuer Configuration:**
  - Added `--query.auto-downsampling` option to the query parameters.

- **Files Modified:**
  - `thanos/thanos-compactor.yaml`
  - `thanos/thanos-queuer.yaml`

- **Breaking Changes:**
  - Retention periods for raw and 5-minute resolution data have been significantly increased, which may impact storage requirements.

## 2024-02-28 – `e312fe1` by Andrey Bondarenko
- **Metrics Update**:
  - Modified memory alert expression in `metrics/kubernetes-prometheus/config-map.yaml` to include `node_memory_SReclaimable_bytes` and `node_memory_Buffers_bytes` for improved accuracy.

## 2024-02-28 – `6347af5` by Andrey Bondarenko
- **Documentation Update:**
  - Changed installation command from `helm install` to `helm update` for NFS subdir external provisioner in `README.md`.

## 2024-03-11 – `9c91641` by Andrey Bondarenko
- **Security Enhancements:**
  - Added `securityContext` to `nginx` and `php` containers in `nginx-deployment.yaml` and `php-deployment.yaml`, respectively.
  - Set `allowPrivilegeEscalation: false` to enhance security posture.

- **File Updates:**
  - Modified `wordpress/nginx-deployment.yaml`
  - Modified `wordpress/php-deployment.yaml`

## 2024-03-18 – `04e1990` by Andrey Bondarenko
- **Security Enhancements:**
  - Added `securityContext` with `allowPrivilegeEscalation: false` to:
    - `mail/dovecot-deployment.yaml`
    - `mail/postfix-deployment.yaml`
    - `mail/rspamd-deployment.yaml`
    - `minecraft/minecraft-deployment.yaml`
    - `nextcloud/nginx-deployment.yaml`
    - `nextcloud/php-deployment.yaml`

- **Files Modified:**
  - Updated deployment configurations for mail services, Minecraft, and Nextcloud to improve security posture.

## 2024-03-18 – `48281a5` by Andrey Bondarenko
- **Alert Configuration Update**
  - Modified alert threshold for "High Node Memory" from 80% to 90% in `metrics/kubernetes-prometheus/config-map.yaml`.

## 2024-03-18 – `6fb254d` by Andrey Bondarenko
- **Database Configuration**:
  - Changed database provider from PostgreSQL to MariaDB in `bitwarden/bitwarden-deployment.yaml`.
  - Updated database server address to `mysql.db.svc.cluster.local`.
  - Changed database username from `postgres` to `root`.
  - Updated secret references for database password to `mysql-pass`.

- **New Environment Variables**:
  - Added `MARIADB_USER` and `MARIADB_PASSWORD` environment variables.

- **Security Context**:
  - Added `securityContext` to the Bitwarden deployment, setting `allowPrivilegeEscalation` to `false`.

- **File Affected**:
  - `bitwarden/bitwarden-deployment.yaml` is the only modified file.

## 2024-03-18 – `29df131` by Andrey Bondarenko
- **Deployment Configuration**:
  - Removed volume mounts for `backup` and `mysql-persistent-storage` in `mysql/cli-deployment.yaml`.
  - Eliminated environment variable `OUTPUT_DIR` set to `/backup`.
  - Removed associated volume definitions for `backup` and `mysql-persistent-storage`.

- **Impact**:
  - Changes may affect data persistence and backup functionality for MySQL CLI. Ensure alternative backup strategies are in place.

## 2024-03-22 – `c56970b` by Andrey Bondarenko
- **Database Configuration Changes**
  - Switched database provider from **MariaDB** to **PostgreSQL** in `bitwarden/bitwarden-deployment.yaml`.
  - Updated database server address to **postgres-postgresql.db.svc.cluster.local**.
  - Changed database username to **postgres** and updated password secret reference to **postgres-pass**.

- **Removed Legacy Configuration**
  - Removed environment variables related to **MariaDB** user and password.

## 2024-03-22 – `7d3f068` by Andrey Bondarenko
- **Documentation Updates:**
  - Added Redis installation instructions to `README.md`.
  - Included command for deploying Redis using Helm with specified values file.

## 2024-03-22 – `7c4c7bb` by Andrey Bondarenko
- **File Modification:**
  - Updated `plex/plex-pvc.yaml` to remove old PersistentVolumeClaims for `plex-conf-lh` and `plex-conf-old`.

- **Configuration Changes:**
  - Removed PersistentVolumeClaim definitions, potentially impacting storage configurations for Plex.

- **Breaking Changes:**
  - Deletion of PVCs may lead to data loss if not properly migrated or backed up before this change.

## 2024-03-22 – `f3f9cce` by Andrey Bondarenko
- **Deployment Configuration**:
  - Removed `plex-conf-old` volume configuration from `plex/plex-deployment.yaml`.
- **File Path**:
  - Updated file: `plex/plex-deployment.yaml`.

## 2024-03-22 – `398dd0d` by Andrey Bondarenko
- **Documentation Update**
  - Added `README.md` to `mastodon/` with installation instructions for Helm chart.
  - Included steps for restoring Persistent Volume Claims (PVCs) annotations and labels.

## 2024-03-22 – `ae0f14d` by Andrey Bondarenko
- **Configuration Update**
  - Changed `externalIPs` from `192.168.1.101` to `192.168.1.111` in `mail/postfix-tls-service.yaml`.

## 2024-03-22 – `2774087` by Andrey Bondarenko
- **Nginx Configuration Updates**:
  - Cleaned up formatting in `nextcloud/nginx-configMap.yaml` for better readability.
  - Maintained existing redirect rules for `.well-known` paths without functional changes.
  - Ensured 404 responses for specific directories and files remain intact.

- **File Affected**:
  - `nextcloud/nginx-configMap.yaml`

## 2024-04-01 – `55ccaab` by Andrey Bondarenko
### CHANGELOG for Commit 55ccaab

#### Resource Limit Updates
- Increased CPU and memory limits across multiple deployments:
  - **Dovecot**: CPU from 300m to 2000m, Memory from 296Mi to 521Mi.
  - **Postfix**: CPU from 300m to 2000m, Memory from 128Mi to 256Mi.
  - **Grafana**: CPU from 1000m to 4000m, Memory from 210Mi to 400Mi.
  - **Kubernetes Node Exporter**: CPU from 1000m to 2000m.
  - **Prometheus**: CPU from 2000m to 4000m.
  - **Minio**: CPU from 3000m to 4000m, Memory from 2000Mi to 4000Mi.
  - **MongoDB**: CPU from 1000m to 2000m, Memory from 600Mi to 600Mi.
  - **MySQL Exporter**: CPU from 1000m to 2000m.
  - **Postgres Exporter**: CPU from 500m to 2000m.
  - **Redis**: CPU from 300m to 4000m, Memory from 100Mi to 2000Mi.
  - **Registry**: CPU from 1000m to 2000m.
  - **TTRSS**: CPU from 800m to 2000m.
  - **Unifi Poller**: CPU from 1000m to 2000m.

#### Configuration Changes
- Updated **Postgres** values

## 2024-04-09 – `f2f08e3` by Andrey Bondarenko
- **Documentation Updates:**
  - Added installation instructions for Elastic in `README.md`.

- **Deployment Configuration:**
  - Updated `unifi/unifi-poller-deployment.yaml`:
    - Added `securityContext` to `unifi-poller` container to disallow privilege escalation.
    - Specified resource requests for memory (128Mi) and CPU (200m) for `unifi-poller` container.

## 2024-04-10 – `6fbb4d8` by Andrey Bondarenko
### CHANGELOG for Commit 6fbb4d8

#### Enhancements
- **Dovecot Deployment**:
  - Added `queue` and `rundir` empty directories with a size limit of 500Mi.
  - Mounted `rundir` at `/run/dovecot` and `queue` at `/var/lib/dovecot`.
  - Set `readOnlyRootFilesystem` to true for improved security.

- **Postfix Deployment**:
  - Introduced `queue` and `spool` empty directories with a size limit of 500Mi.
  - Mounted `queue` at `/var/lib/postfix` and `spool` at `/var/spool/postfix`.
  - Set `readOnlyRootFilesystem` to true for enhanced security.

#### Files Modified
- `mail/dovecot-deployment.yaml`
- `mail/postfix-deployment.yaml`
- `mail/rspamd-deployment.yaml` (security context updated)

#### Breaking Changes
- New volume mounts and security settings may require adjustments in existing configurations.

## 2024-04-10 – `7e305a9` by Andrey Bondarenko
- **Security Enhancements**
  - Added `readOnlyRootFilesystem: true` to `securityContext` in:
    - `minecraft/minecraft-deployment.yaml`
    - `unifi/unifi-poller-deployment.yaml`

- **File Updates**
  - Updated configurations for Minecraft and Unifi Poller deployments to enhance security posture.

## 2024-04-10 – `36efed9` by Andrey Bondarenko
- **Nginx Deployment Updates**:
  - Added `cache` and `run` empty directories with size limits to `nginx-deployment.yaml`.
  - Mounted `cache` at `/var/cache/nginx` and `run` at `/var/run` in Nginx container.
  - Set `readOnlyRootFilesystem` to `true` for enhanced security.

- **PHP Deployment Enhancements**:
  - Introduced `varrun`, `run`, and `tmp` empty directories with specified size limits in `php-deployment.yaml`.
  - Mounted `varrun` at `/var/run/php`, `run` at `/run`, and `tmp` at `/tmp` in PHP container.
  - Set `readOnlyRootFilesystem` to `true` for improved security.

- **Files Modified**:
  - `wordpress/nginx-deployment.yaml`
  - `wordpress/php-deployment.yaml`

- **Breaking Changes**: None noted.

## 2024-04-10 – `221e136` by Andrey Bondarenko
### CHANGELOG for Commit 221e136

#### Enhancements
- **Nginx Deployment**:
  - Added `cache` and `run` empty directories with size limits in `nextcloud/nginx-deployment.yaml`.
  - Mounted `cache` at `/var/cache/nginx` and `run` at `/var/run` for improved caching and runtime handling.
  - Set `readOnlyRootFilesystem` to `true` for enhanced security.

- **PHP Deployment**:
  - Introduced `varrun`, `varlib`, `run`, and `tmp` empty directories with size limits in `nextcloud/php-deployment.yaml`.
  - Mounted `varrun` at `/var/run/php`, `varlib` at `/var/lib/php/sessions`, `run` at `/run`, and `tmp` at `/tmp` for better session and temporary file management.
  - Set `readOnlyRootFilesystem` to `true` for improved security.

#### Files Modified
- `nextcloud/nginx-deployment.yaml`
- `nextcloud/php-deployment.yaml`

#### Breaking Changes
- None noted, but ensure compatibility with existing volume mounts and configurations.

## 2024-04-10 – `f04ad79` by Andrey Bondarenko
- **Kubernetes Configuration Updates**
  - Added `varlib` empty directory with a size limit of 10Mi in `wordpress/php-deployment.yaml`.
  - Mounted `varlib` to `/var/lib/php/sessions` in the deployment spec.

- **File Affected**
  - `wordpress/php-deployment.yaml`

## 2024-04-10 – `4649fd9` by Andrey Bondarenko
- **Security Context Updates**:
  - Added `securityContext` to `nextcloud/php-deployment.yaml` and `wordpress/php-deployment.yaml`.
    - Set `runAsUser`, `runAsGroup`, and `fsGroup` to `33` for both deployments.

- **Files Modified**:
  - `nextcloud/php-deployment.yaml`
  - `wordpress/php-deployment.yaml`

- **Breaking Change**:
  - Deployment configurations now enforce specific user and group IDs, which may affect file permissions.

## 2024-04-10 – `65574f8` by Andrey Bondarenko
- **Security Enhancements**
  - Added `securityContext` to `minecraft/minecraft-deployment.yaml`:
    - Set `runAsUser`, `runAsGroup`, and `fsGroup` to `1000`.

## 2024-04-10 – `38aef74` by Andrey Bondarenko
- **ClamAV Deployment Enhancements**
  - Added `securityContext` to `clamav` containers, enforcing user/group IDs and filesystem group settings.
  - Introduced `log` volume for `/var/log/clamav` in both `clamd` and `fresclam` containers.
  - Set `allowPrivilegeEscalation` to `false` and `readOnlyRootFilesystem` to `true` for improved security.

- **Postfix Deployment Updates**
  - Commented out `securityContext` settings for `postfix`, removing explicit user/group configurations.

## 2024-04-10 – `57604da` by Andrey Bondarenko
- **Deployment Enhancements**
  - Added `securityContext` to `conduit-deployment.yaml` and `nginx-deployment.yaml` to enforce `allowPrivilegeEscalation: false` and `readOnlyRootFilesystem: true`.

- **Volume Management**
  - Introduced two new `emptyDir` volumes in `nginx-deployment.yaml`:
    - `cache` with a size limit of 500Mi.
    - `run` with a size limit of 1Mi.

- **Container Configuration**
  - Updated `nginx` container in `nginx-deployment.yaml` to mount new `cache` and `run` volumes at `/var/cache/nginx` and `/var/run`, respectively.

## 2024-04-12 – `0bf5d0e` by Andrey Bondarenko
- **Nextcloud Updates:**
  - Changed `varlib` volume from `emptyDir` to `persistentVolumeClaim` using `nextcloud-sessions`.
  - Added PersistentVolumeClaim for `nextcloud-sessions` with 10Mi storage in `nextcloud/php-pvc.yaml`.

- **WordPress Updates:**
  - Changed `varlib` volume from `emptyDir` to `persistentVolumeClaim` using `wordpress-sessions`.
  - Added PersistentVolumeClaim for `wordpress-sessions` with 10Mi storage in `wordpress/php-pvc.yaml`.

- **File Changes:**
  - Updated `nextcloud/php-deployment.yaml`, `nextcloud/php-pvc.yaml`, `wordpress/php-deployment.yaml`, and `wordpress/php-pvc.yaml`.

## 2024-04-15 – `f57fcdf` by Andrey Bondarenko
- **Resource Configuration Update**
  - Increased memory requests from `100Mi` to `200Mi` in `wordpress/nginx-deployment.yaml`.
  - Increased memory limits from `100Mi` to `300Mi` in `wordpress/nginx-deployment.yaml`.

## 2024-04-15 – `e79b5ad` by Andrey Bondarenko
- **Dovecot Configuration Updates**
  - Changed log paths in `mail/dovecot-configMap.yaml` from `/var/log/mail.log` to `/var/lib/dovecot/mail.log` for `log_path`, `info_log_path`, and `debug_log_path`.

- **New Persistent Volume Claim**
  - Added `mail/postfix-pvc.yaml` for PersistentVolumeClaim named `queue-lh` with `1Gi` storage request using `longhorn` storage class.

## 2024-04-15 – `6a5df3c` by Andrey Bondarenko
- **Deployment Configuration Updates**
  - Replaced `queue` from `emptyDir` to `persistentVolumeClaim` with `claimName: queue-lh`.
  - Retained `spool` as a `persistentVolumeClaim` with `claimName: queue-lh`.

- **File Affected**
  - `mail/postfix-deployment.yaml` modified for persistent storage configuration.

- **Breaking Change**
  - `queue` storage type changed from ephemeral (`emptyDir`) to persistent, requiring existing deployments to adapt.

## 2024-04-16 – `f82daf7` by Andrey Bondarenko
- **Deployment Configuration**
  - Added `/tmp` volume mount to `clamav-deployment.yaml` for temporary file storage.
  - Introduced `tmp` emptyDir volume with a size limit of 600Mi.

- **File Modified**
  - Updated `clamav/clamav-deployment.yaml` to accommodate new volume configurations.

## 2024-04-16 – `b75fd51` by Andrey Bondarenko
- Marked `camera/README.md` as **OBSOLETE**.
- Updated documentation regarding Foscam camera capabilities.
- Clarified that the camera supports **RTSP streaming** and **FTP upload** on motion detection.

## 2024-04-16 – `9852ce1` by Andrey Bondarenko
- **New Secrets Added**:
  - Added PGP encrypted secrets for various services:
    - `bitwarden/secret.yaml.asc`
    - `camera/secret.yaml.asc`
    - `clamav/secret.yaml.asc`
    - `conduit/secret.yaml.asc`
    - `mail/secret.yaml.asc`
    - `mastodon/secret.yaml.asc`
    - `metrics/secret.yaml.asc`
    - `minecraft/secret.yaml.asc`
    - `minio-single/secret.yaml.asc`
    - `mongo/secret.yaml.asc`
    - `mysql/secret.yaml.asc`
    - `nextcloud/secret.yaml.asc`
    - `plex/secret.yaml.asc`
    - `postgres/secret.yaml.asc`
    - `redis/secret.yaml.asc`
    - `secret.yaml.asc`
    - `ttrss/secret.yaml.asc`
    - `unifi/secret.yaml.asc`
    - `wordpress/secret.yaml.asc`
    - `your-spotify/secret.yaml.asc`

- **Script Update**:
  - Updated `secrets.sh` to accommodate new secrets management.

- **File Structure**:
  - Introduced a consistent structure for secret files across multiple services, enhancing organization and security.

- **Breaking Changes**:
  - Ensure all services utilizing these secrets are updated to handle the new PGP encrypted format.

## 2024-04-25 – `6a19137` by Andrey Bondarenko
- **Configuration Changes**
  - Added `conduit-configmap.yaml` for Conduit configuration settings.
  - ConfigMap includes database path and backend settings.

- **Deployment Updates**
  - Updated `conduit-deployment.yaml` to mount the new ConfigMap as `/etc/conduit.toml`.
  - Added environment variable `CONDUIT_CONFIG` pointing to the new config file.

- **File Paths**
  - New ConfigMap located at `conduit/conduit-configmap.yaml`.
  - Deployment file modified at `conduit/conduit-deployment.yaml`.

## 2024-04-25 – `ed79115` by Andrey Bondarenko
- **Configuration Update**:
  - Increased `jit_buffer_size` and `opcache.jit_buffer_size` from `128M` to `256M` in `nextcloud/php-configmap.yaml`.

## 2024-04-26 – `a6907ab` by Andrey Bondarenko
- **Configuration Updates**
  - Changed storage configuration in `mastodon/mastodon-values.yaml` to use existing claims for assets and system storage.
  - Commented out previous settings for `accessMode` and `resources` under both `assets` and `system` sections.

- **Breaking Change**
  - The removal of `ReadWriteMany` access mode may affect scalability; ensure compatibility with existing deployments.

## 2024-04-30 – `7c9d355` by Andrey Bondarenko
- **Deployment Configuration Updates**
  - Updated `CONDUIT_DATABASE_PATH` in `conduit/conduit-deployment.yaml` to remove trailing slash.
  - Added new environment variables: `CONDUIT_PORT` (set to `6167`) and `CONDUIT_ADDRESS` (set to `0.0.0.0`).
  - Cleared `CONDUIT_CONFIG` value in `conduit/conduit-deployment.yaml`.

- **Ingress Configuration Change**
  - Changed `pathType` from `Prefix` to `ImplementationSpecific` for the `.well-known/matrix/` path in `conduit/matrix-ingress.yaml`.

## 2024-04-30 – `74b24fa` by Andrey Bondarenko
- **Documentation Updates:**
  - Removed Redis installation command from `README.md`.
  - Added new `clamav/README.md` detailing Calamav usage and configuration.
  - Updated `redis/README.md` to clarify usage instructions.
  - Introduced `unifi/README.md` marking it as obsolete and recommending Ubiquity appliance for production.

- **Configuration Changes:**
  - Modified `conduit/conduit-deployment.yaml` to remove commented-out `CONDUIT_ADDRESS` value.

- **Important Notes:**
  - Breaking change: `unifi` controller software is no longer recommended for production use in Kubernetes.

## 2024-05-13 – `f7f9108` by Andrey Bondarenko
- **Nginx Configuration Updates**:
  - Added support for `.mjs` file extension in `nginx-configMap.yaml`.
  - Set `default_type` for `.mjs` to `text/javascript`.
  - Updated regex in location block to include `.mjs` alongside existing file types.

- **File Affected**:
  - `nextcloud/nginx-configMap.yaml`

## 2024-05-14 – `02f0571` by Andrey Bondarenko
- **Deployment Changes:**
  - Changed `postfix` from a **Deployment** to a **DaemonSet** in `mail/postfix-deployment.yaml`.
  - Removed `replicas` setting; now runs on all nodes.

- **Volume Configuration:**
  - Replaced `persistentVolumeClaim` for `spool` with `emptyDir` (size limit: 500Mi) in `mail/postfix-deployment.yaml`.
  - Commented out `persistentVolumeClaim` for `queue`, now using `emptyDir` (size limit: 500Mi).

- **Service Configuration:**
  - Updated `postfix-tls-service.yaml` to set service type to **NodePort**.
  - Added `externalTrafficPolicy: Local` for better traffic management.

**Breaking Change:** The change from Deployment to DaemonSet may affect scaling and resource allocation.

## 2024-05-14 – `5a7c4a0` by Andrey Bondarenko
- **Deployment Changes**
  - Changed resource type from `DaemonSet` to `Deployment` in `mail/postfix-deployment.yaml`.
  - Added `nodeSelector` to specify node affinity for the deployment.

- **Volume Configuration**
  - Enabled `persistentVolumeClaim` for the `spool` volume, linking to `queue-lh`.
  - Removed commented-out lines for `persistentVolumeClaim` under `spool`.

- **Replicas Configuration**
  - Uncommented `replicas` setting, ensuring one replica is deployed.

## 2024-05-14 – `689982f` by Andrey Bondarenko
- **Nextcloud Configuration Updates**
  - Added custom `log_format` for access logs in `nextcloud/nginx-configMap.yaml`.
  - Changed `access_log` to use the new log format.
  - Disabled gzip compression (`gzip off`).

- **WordPress Configuration Updates**
  - Introduced custom `log_format` for access logs in `wordpress/nginx-configMap.yaml`.
  - Updated `access_log` to utilize the new log format.
  - Set `listen` directive to 80.

- **New NGINX ConfigMap**
  - Created `nginx/nginx-config.yaml` with settings for proxy protocol, body size, snippet annotations, and real IP handling.

- **Removed File**
  - Deleted `wordpress/nginx-ingress-configMap.yaml`.

**Note:** Ensure to review the impact of disabling gzip and the removal of the ingress configMap on existing deployments.

## 2024-05-14 – `792dd53` by Andrey Bondarenko
- **Nginx Configuration Update**
  - Enabled `gzip` compression in `nextcloud/nginx-configMap.yaml`.
  - Adjusted `gzip` settings for improved performance.

## 2024-05-14 – `ce9d754` by Andrey Bondarenko
- **Configuration Changes:**
  - Commented out `securityContext` section in `mail/postfix-deployment.yaml`.
  - Removed `runAsUser`, `runAsGroup`, and `fsGroup` settings from the deployment spec.

## 2024-05-14 – `13036b0` by Andrey Bondarenko
- **Nginx Configuration Updates**
  - Disabled `gzip` in `nextcloud/nginx-configMap.yaml`.
  - Set `client_max_body_size` to `2000M` and `client_body_buffer_size` to `512k`.
  - Added `gzip` settings in `nginx/nginx-config.yaml` with `use-gzip: "true"` and `gzip-level: "6"`.

- **File Changes**
  - Modified `nextcloud/nginx-configMap.yaml` to streamline gzip settings.
  - Updated `nginx/nginx-config.yaml` to enable gzip compression with specified level.

- **Breaking Change**
  - Gzip compression is now disabled by default in the Nextcloud configuration, which may affect performance.

## 2024-05-23 – `aa51bfa` by Andrey Bondarenko
### CHANGELOG for Commit aa51bfa

#### Nextcloud Updates
- **Deployment Changes**:
  - Updated labels in `nginx-deployment.yaml`, `php-deployment.yaml` to use `app: nextcloud` and `tier: frontend`.
  - Added pod affinity rules to `nginx-deployment.yaml`, `php-deployment.yaml`, and `cronjob-nextcloud.yaml` for better scheduling.

- **Service Adjustments**:
  - Modified selectors in `nginx-service.yaml`, `php-service.yml` to align with new labels.

- **Persistent Volume Claims**:
  - Changed access modes from `ReadWriteMany` to `ReadWriteOnce` in `php-pvc.yaml`.

#### WordPress Updates
- **Deployment Changes**:
  - Updated labels in `nginx-deployment.yaml`, `php-deployment.yaml` to use `app: wordpress` and `tier: frontend`.
  - Added pod affinity rules to `nginx-deployment.yaml`, `php-deployment.yaml`.

- **Service Adjustments**:
  - Modified selectors in `nginx-service.yaml`, `php-service.yml` to align with new labels.

- **Persistent Volume Claims**:
  - Changed access modes from `ReadWriteMany` to `ReadWriteOnce` in `php-pvc.yaml`.

#### Important Files
- Affected files include:
  - `cron/cronjob-nextcloud.yaml`
  - `nextcloud/nginx-deployment.yaml`
  - `wordpress/nginx-deployment.yaml`

#### Breaking Changes
- Access mode change in PVCs may affect storage behavior; ensure compatibility with existing setups.

## 2024-06-02 – `cca176b` by Andrey Bondarenko
- **Documentation Updates**
  - Added TODO items for Mail, Mastodon, MySQL, Ples(lib), Docker (RWO), Prometheus, Thanos (non-root containers), and relevant network policies in `README.md`.

- **Kubernetes PVC Changes**
  - Changed access mode from `ReadWriteMany` to `ReadWriteOnce` in:
    - `metrics/kubernetes-prometheus/prometheus-pvc.yaml`
    - `thanos/thanos-compactor-pvc.yaml`
    - `thanos/thanos-storage-gateway-pvc.yaml`

- **Storage Configuration**
  - All modified PVC files now specify `ReadWriteOnce` access mode, potentially impacting multi-node access configurations.

## 2024-06-02 – `387749c` by Andrey Bondarenko
- **Documentation Updates**
  - Updated README.md to reflect changes in mail, Mastodon, and Docker registry deployment.

- **Mail Services Enhancements**
  - Added `app` labels to `dovecot`, `postfix`, and `rspamd` deployment and service YAML files for better identification.
  - Set `nodeSelector` for `dovecot` and `rspamd` deployments to target specific nodes (`m.k8s.my.lan`).

- **Persistent Volume Claims (PVC) Changes**
  - Changed access modes from `ReadWriteMany` to `ReadWriteOnce` in `dovecot-pvc.yaml`, `mysql-pvc.yaml`, and `plex-pvc.yaml` to restrict volume access.

- **Breaking Changes**
  - PVC access mode changes may affect existing deployments relying on multi-writer access.

## 2024-06-03 – `7e62401` by Andrey Bondarenko
- **Documentation Updates**
  - Updated code block formatting in `README.md` for Helm installation command (added `bash` syntax highlighting).
  - Added new `cron/README.md` file outlining the status of cron scripts, noting they are mostly obsolete due to Longhorn's backup capabilities.

## 2024-06-03 – `a65c81a` by Andrey Bondarenko
- **Configuration Update**
  - Added `log_bin_trust_function_creators = 1` to `mysql/mysqld-exporter-configmap.yaml` for MySQL exporter configuration.

## 2024-06-06 – `44c29e5` by Andrey Bondarenko
- **Resource Configuration**
  - Updated memory limit from `512Mi` to `1024Mi` in `collabora/values.yaml`.

## 2024-06-06 – `e75e5c0` by Andrey Bondarenko
- **PVC Configuration Update**:
  - Changed access mode from `ReadWriteMany` to `ReadWriteOnce` in `clamav/clamav-pvc.yaml`.
  - Increased storage request from `1500Mi` to `15Gi` in `clamav/clamav-pvc.yaml`.

**Breaking Change**: The access mode change may affect multi-node access capabilities.

## 2024-06-06 – `07c3d9e` by Andrey Bondarenko
- **Configuration Update**
  - Changed SMTP port from `587` to `25` in `bitwarden/bitwarden-deployment.yaml`.

- **Image Reference**
  - Maintained image reference: `bitwarden/self-host:beta`.

## 2024-06-06 – `7a6fa21` by Andrey Bondarenko
- **Documentation Update**
  - Added installation instructions for the common chart in `README.md`.
  - Included specific configuration for `Chart.yaml` and `.lock`.

- **Configuration Changes**
  - Updated `mastodon-values.yaml` to set `accessMode` to `ReadWriteMany` for both `mastodon` and `system` sections.
  - Defined storage requests for `mastodon` (10Gi) and `system` (100Gi) with `StorageClassName: "longhorn"`.

- **Important Files**
  - `mastodon/README.md`: Installation instructions enhanced.
  - `mastodon/mastodon-values.yaml`: Configuration for storage access modes and requests modified.

## 2024-06-18 – `2ac0330` by Andrey Bondarenko
- **Conduit Configuration Updates**
  - Added server name and federation address to `conduit/conduit-configmap.yaml`.

- **Nginx Configuration Enhancements**
  - Updated `conduit/nginx-configMap.yaml` to include `server_name` and proxy settings for `/` location.
  - Configured proxy headers for improved request handling.

## 2024-06-18 – `a1af4a6` by Andrey Bondarenko
- **New Feature**: Added migration configuration for Mastodon.
  - Created `mastodon/migrate.yaml` for Pod deployment.
  - Utilizes `nginx:stable-alpine` image for migration tasks.
  - Configured volume mount for persistent storage using `mastodon-system` PVC.

## 2024-06-18 – `c608b58` by Andrey Bondarenko
- **Resource Configuration**:
  - Increased memory limit from `8145Mi` to `9145Mi` in `nextcloud/php-deployment.yaml`.

## 2024-06-18 – `a605780` by Andrey Bondarenko
- **Documentation Update**
  - Corrected command in `registry/README.md` from `upgrade` to `helm upgrade` for clarity.

## 2024-06-18 – `c8f0cb2` by Andrey Bondarenko
- **Configuration Update**
  - Changed MinIO endpoint in `mastodon/mastodon-values.yaml` from `minio.minio.svc.cluster.local` to `192.168.1.112:9000`.

**Note:** Ensure the new endpoint is accessible in your network configuration.

## 2024-06-20 – `bbbc01c` by Andrey Bondarenko
- **Configuration Changes**:
  - Updated `mastodon/mastodon-values.yaml` to enable S3 storage.
  - Changed S3 endpoint to `https://s3.andreybondarenko.com`.
  - Set `alias_host` to `s3.andreybondarenko.com/mastodon`.

- **Commented Out Sections**:
  - Commented out `system` storage configuration, including access mode and resource requests.
  - Commented out S3 access keys for security reasons.

- **File Path**:
  - Affected file: `mastodon/mastodon-values.yaml`.

## 2024-06-20 – `36280c8` by Andrey Bondarenko
- **Ingress Configuration**: Added `minio-ingress.yaml` for MinIO service.
  - Configures Ingress with NGINX controller and Let's Encrypt for TLS.
  - Sets up SSL redirection and custom header for forwarded requests.
  - Defines backend service pointing to MinIO on port 9000.
- **Annotations**: Includes settings for SSL, request size, and header manipulation.

## 2024-06-20 – `aa5836b` by Andrey Bondarenko
- **Deployment Configuration Updates**
  - Updated `CONDUIT_CONFIG` in `conduit/conduit-deployment.yaml` to point to `/etc/conduit.toml`.

- **Nginx Configuration Cleanup**
  - Removed unnecessary proxy settings in `conduit/nginx-configMap.yaml`.
  - Cleaned up JSON formatting in `.well-known` endpoints for consistency.

## 2024-06-21 – `0890ac2` by Andrey Bondarenko
- **Documentation Update**
  - Removed item from TODO list in `README.md`: "Mastodon, Docker registry - RWO if possible (Help deployment)"

## 2024-06-27 – `86f2070` by Andrey Bondarenko
- **Security Context Updates**
  - Added `securityContext` to both `nextcloud/nginx-deployment.yaml` and `wordpress/nginx-deployment.yaml`
    - `runAsUser`, `runAsGroup`, and `fsGroup` set to `33` for both deployments.

- **Files Modified**
  - `nextcloud/nginx-deployment.yaml`
  - `wordpress/nginx-deployment.yaml`

- **Breaking Change**
  - Ensure compatibility with user/group ID `33` for existing persistent volumes.

## 2024-06-27 – `5cdbb29` by Andrey Bondarenko
- **Configuration Update**:
  - Reduced `pm.max_children` from 240 to 120 in `nextcloud/php-configmap.yaml`.

- **File Affected**:
  - `nextcloud/php-configmap.yaml` - Adjusted PHP-FPM configuration for performance tuning.

## 2024-07-01 – `e8abc9f` by Andrey Bondarenko
- **Configuration Update**
  - Increased `client_max_body_size` from 200M to 250M in `wordpress/nginx-configMap.yaml`.

## 2024-07-01 – `7a50d40` by Andrey Bondarenko
- **Kubernetes Configuration Update**
  - Updated `nextcloud/php-pvc.yaml` to increase storage request from 100Gi to 200Gi.
  - Added label `app.kubernetes.io/instance: nextcloud` for better resource identification.

## 2024-07-01 – `dba50c1` by Andrey Bondarenko
- **Kubernetes Configuration**
  - Changed `accessModes` from `ReadWriteMany` to `ReadWriteOnce` in `minecraft/minecraft-pvc.yaml`.
  - This change may affect how multiple pods access the persistent volume.

## 2024-07-02 – `c2972e4` by Andrey Bondarenko
- **Storage Configuration**
  - Changed `accessModes` from `ReadWriteMany` to `ReadWriteOnce` in `conduit/matrix-pvc.yaml`.
- **File Affected**
  - `conduit/matrix-pvc.yaml` updated to reflect new access mode.
- **Breaking Change**
  - This change may affect applications relying on shared access to the PVC.

## 2024-07-02 – `619a4c2` by Andrey Bondarenko
- **Ingress Configuration**
  - Updated service name from `collabora-online` to `collabora-collabora-online` in `collabora/ingress.yaml`.
  - Ensure to update any references to the service name in related configurations.

## 2024-07-02 – `354b591` by Andrey Bondarenko
- **MongoDB PVC Configuration**
  - Changed access mode from `ReadWriteMany` to `ReadWriteOnce` in `mongo/mongo-pvc.yaml`.
  - Increased requested storage from `1000Mi` to `10Gi` in `mongo/mongo-pvc.yaml`.

**Breaking Change**: The access mode change may affect multi-pod deployments.

## 2024-07-02 – `47f7f7b` by Andrey Bondarenko
- **File Update**: Modified `plex/plex-pvc.yaml` to remove commented-out lines for clarity.
- **PersistentVolumeClaim**:
  - Changed access mode from `ReadWriteOnce` to `ReadWriteMany` for the existing PVC.
- **Namespace**: Ensured PVC is correctly configured under the `plex` namespace.

## 2024-07-02 – `9531f0f` by Andrey Bondarenko
- **PVC Configuration Update**
  - Changed access mode from `ReadWriteMany` to `ReadWriteOnce` in `plex/plex-pvc.yaml`.

**Note:** This change may affect how multiple pods access the PVC.

## 2024-07-24 – `a72a372` by Andrey Bondarenko
- **Deployment Configuration**
  - Updated `CUSTOM_SERVER` path in `minecraft/minecraft-deployment.yaml` from `/data/minecraft_server.1.20.4.jar` to `/data/server.jar`.

## 2024-07-24 – `80d6004` by Andrey Bondarenko
- **Nginx Configuration Updates**
  - Enabled `gzip` compression in `nextcloud/nginx-configMap.yaml` and `wordpress/nginx-configMap.yaml`.
  - Removed `gzip off;` directive from `nextcloud/nginx-configMap.yaml`.

## 2024-07-24 – `146b5f2` by Andrey Bondarenko
- **Removed**: Deleted `nginx/nginx-config.yaml` configuration file.
- **Impact**: This change removes the NGINX ingress controller configuration, which may affect deployment and traffic handling settings.

## 2024-07-24 – `7b3f640` by Andrey Bondarenko
- **Documentation Updates**
  - Removed NGINX ingress deployment instructions from `README.md`.
  - Added `argocd/README.md` to document services managed by Argocd.
  - Updated `collabora/README.md` to indicate management by Argocd.

- **Argocd Configuration**
  - Introduced new Argocd YAML files for various services:
    - `bitwarden.yaml`
    - `clamav.yaml`
    - `collabora.yaml`
    - `conduit.yaml`
    - `ingress-nginx.yaml`
    - `mail.yaml`
    - `minecraft.yaml`
    - `minio.yaml`
    - `mongo.yaml`
    - `nextcloud.yaml`
    - `plex.yaml`
    - `thanos.yaml`
    - `wordpress.yaml`
  - Each file specifies project, source repository, destination server, and sync policies.

- **Breaking Changes**
  - Removed `collabora/values.yaml` file; configuration now managed via Argocd.
  - Obsoleted services listed in `argocd/README.md`: camera, UniFi controller, TTRSS, Dashboard.

## 2024-07-24 – `38b30d7` by Andrey Bondarenko
- **ArgoCD Configuration**
  - Updated `collabora.yaml` to use `targetRevision: 1.1.20`.

- **Loki Configuration**
  - Added `loki/loki/values.yaml` with storage and replication settings.
  - Removed deprecated `loki/promtail.yaml`.
  - Introduced new `loki/promtail/promtail.yaml` with DaemonSet and ConfigMap definitions for Promtail.
  - Added RBAC resources: `ClusterRole`, `ServiceAccount`, and `ClusterRoleBinding` for Promtail.

**Breaking Changes:**
- Removal of `loki/promtail.yaml` may affect existing deployments relying on the previous configuration.

## 2024-07-24 – `d34c67b` by Andrey Bondarenko
### CHANGELOG for Commit d34c67b

#### New Features
- Added `argocd/cert-manager.yaml` for Argocd integration with cert-manager.
- Created `cert-manager/README.md` for documentation.

#### Deletions
- Removed multiple cert-manager deployment files:
  - `cert-manager/cert-manager-cainjector-deployment.yaml`
  - `cert-manager/cert-manager-deployment.yaml`
  - `cert-manager/cert-manager-exporter-service.yaml`
  - `cert-manager/cert-manager-namespace.yaml`
  - `cert-manager/cert-manager-webhook-deployment.yaml`

#### Notes
- Breaking change: Complete removal of existing cert-manager deployment configurations. Ensure to migrate to the new Argocd-based deployment method.

## 2024-07-24 – `8ccd921` by Andrey Bondarenko
- **Documentation Updates**
  - Removed installation instructions for the NFS volume provisioner from `README.md`.

- **New Configuration**
  - Added `argocd/nfs-provisioner.yaml` for automated deployment of the NFS subdir external provisioner.
  - Configured NFS server and path parameters in the new YAML file.

- **Important Paths**
  - `argocd/nfs-provisioner.yaml`: New file for ArgoCD integration.

## 2024-07-24 – `80d211b` by Andrey Bondarenko
- **Documentation Updates**
  - Updated `cert-manager/README.md` for clarity and accuracy.

## 2024-07-24 – `ed2fed0` by Andrey Bondarenko
- **Documentation Updates**
  - Removed outdated Letsencrypt deployment instructions from `README.md`.
  - Removed Elastic deployment instructions from `README.md`.

- **New Configuration**
  - Added new `argocd/elasticsearch.yaml` file for ArgoCD integration with Elasticsearch.
  - Configures Elasticsearch deployment from Bitnami chart repository.

## 2024-07-24 – `60f0223` by Andrey Bondarenko
- **File Deletion**:
  - Removed `metrics/graphana/Cluster load-1702377122035.json` (entire file).

- **Impact**:
  - This change may affect any dashboards or metrics relying on the deleted JSON configuration. Ensure to update references or configurations accordingly.

## 2024-07-24 – `dd89f21` by Andrey Bondarenko
- **New Configurations Added:**
  - Introduced `graphana.yaml` for Grafana deployment in the `monitoring` namespace.
  - Added `kube-state-metrics.yaml` for kube-state-metrics configuration.
  - Created `kubernetes-node-exporter.yaml` for node exporter setup.
  - Added `kubernetes-prometheus.yam` for Prometheus deployment.

- **Source Repository:**
  - All configurations source from `https://github.com/shaman007/home-k3s.git`, targeting `HEAD` revision.

- **Deployment Target:**
  - All resources are set to deploy to `https://kubernetes.default.svc` in the `monitoring` namespace with automated sync policy.

## 2024-07-24 – `47ed16e` by Andrey Bondarenko
- **Deployment Changes**
  - Added `unifi-poller-deployment.yaml` in `unifi/poller/` for new deployment configuration.
  - Removed legacy `unifi-poller-deployment.yaml` from `unifi/`.

- **Service Changes**
  - Added `unifi-poller-service.yaml` in `unifi/poller/` for new service configuration.
  - Removed legacy `unifi-poller-service.yaml` from `unifi/`.

- **Configuration Details**
  - Updated environment variables for `unifi-poller` deployment, including credentials and resource limits.
  - Container port set to `9130` for both deployment and service.

- **Breaking Changes**
  - Legacy deployment and service files have been removed; ensure to update references accordingly.

## 2024-07-24 – `bb48437` by Andrey Bondarenko
- **Documentation Updates**
  - Marked "Tiny-Tiny RSS" and "UniFi console" as OBSOLETE in `README.md`.
  - Added new services including "Rsyslog" in `argocd/README.md`.

- **TODO List Enhancements**
  - Expanded TODO items in both `README.md` and `argocd/README.md` to include services like "Loki", "Promtail", "MariaDB", "Postgres", and "Redis".

- **Repository Configuration**
  - Added command to add a Bitnami Helm repository in `argocd/README.md`.

## 2024-07-24 – `4f3e59f` by Andrey Bondarenko
### CHANGELOG for Commit 4f3e59f

- **Kubernetes RBAC Configuration**
  - Added `promtail-clusterrole.yaml`: Defines a ClusterRole for Promtail with permissions to get, watch, and list all resources.
  - Added `promtail-rolebinding.yaml`: Creates a ClusterRoleBinding for the Promtail service account.
  - Added `promtail-serviceaccount.yaml`: Defines a ServiceAccount for Promtail.

- **Promtail Configuration**
  - Added `promtail-configmap.yaml`: Configures Promtail with server settings, client URL, positions file, and scrape configurations for Kubernetes pod logs.

- **File Structure Update**
  - Removed old inline configuration from `promtail.yaml` and replaced it with a reference to the new ConfigMap.

**Note:** Ensure the new RBAC settings are compatible with existing cluster policies.

## 2024-07-24 – `ff8d9e1` by Andrey Bondarenko
- **New Configuration**: Added `promtail.yaml` for ArgoCD integration.
- **Source Configuration**:
  - Set `repoURL` to `https://github.com/shaman007/home-k3s.git`.
  - Defined `path` as `loki/promtail` and `targetRevision` as `HEAD`.
- **Destination Configuration**:
  - Configured `server` to `https://kubernetes.default.svc`.
  - Set `namespace` to `loki`.
- **Sync Policy**: Enabled automated sync policy for deployment.

## 2024-07-24 – `49f0dd7` by Andrey Bondarenko
- **Documentation Updates**
  - Removed "Promtail" and "Your-Spotify" from the TODO list in `argocd/README.md`.

- **New Configuration**
  - Added `your-spotify.yaml` for Spotify integration in ArgoCD, specifying:
    - Repository URL: `https://github.com/shaman007/home-k3s.git`
    - Target namespace: `spotify`
    - Automated sync policy enabled.

## 2024-07-24 – `fabd30d` by Andrey Bondarenko
- **Storage Configuration Update**
  - Increased MySQL PVC storage from 4000Mi to 10Gi in `mysql/mysql-pvc.yaml`.

## 2024-07-24 – `43585aa` by Andrey Bondarenko
- **Removed**: Deleted `mysql/migrate.yaml` file, which defined a Pod for database migration.
- **Impact**: This change may affect any existing migration processes relying on the removed configuration.

## 2024-07-24 – `aa92af1` by Andrey Bondarenko
- **Documentation Updates:**
  - Removed references to MariaDB and its exporters from `argocd/README.md`.

- **New Configuration:**
  - Added `argocd/mysql.yaml` for MySQL configuration in ArgoCD, specifying project, source repository, and sync policy.

## 2024-07-24 – `7f95664` by Andrey Bondarenko
- **File Changes**:
  - Deleted `argocd/kubernetes-prometheus.yam`.
  - Added `argocd/kubernetes-prometheus.yaml` (new file).

- **Configuration**:
  - Retained project configuration for Prometheus monitoring in Kubernetes.
  - Source and destination settings remain unchanged.

- **Breaking Change**:
  - Transition from `.yam` to `.yaml` file extension may affect existing references.

## 2024-07-24 – `8fb327c` by Andrey Bondarenko
- **Deployment Changes**
  - Removed `postgres/cli-deployment.yaml`.
  - Added `postgres/exporter/cli-deployment.yaml` with identical configuration.

- **Exporter Configuration**
  - Removed `postgres/postgres-exporter.yaml` and `postgres/postgres-exporter-service.yaml`.
  - Added `postgres/exporter/postgres-exporter.yaml` and `postgres/exporter/postgres-exporter-service.yaml` with identical configurations.

- **File Structure Update**
  - Consolidated CLI and exporter configurations under the `exporter` directory for better organization.

- **Breaking Changes**
  - The original `postgres/cli-deployment.yaml` and `postgres/postgres-exporter.yaml` files have been deleted; ensure to update any references accordingly.

## 2024-07-24 – `939c312` by Andrey Bondarenko
- **Documentation Update**
  - Removed mention of "exporters for postgres, etc." from `argocd/README.md`.

- **New Configuration**
  - Added `postgres-exporter.yaml` for PostgreSQL exporter configuration in ArgoCD.
    - Configures source repository and sync policy for deployment in the `db` namespace.

## 2024-07-24 – `369df70` by Andrey Bondarenko
- **New Features**
  - Added `argocd/postgres.yaml` for managing PostgreSQL deployment via ArgoCD.

- **Documentation Updates**
  - Updated `argocd/README.md` to reflect the removal of PostgreSQL installation instructions.
  - Revised `postgres/README.md` to indicate PostgreSQL is now managed by ArgoCD.

- **File Removals**
  - Removed `postgres/values.yaml`, consolidating configuration management under ArgoCD.

- **Breaking Changes**
  - Direct Helm installation of PostgreSQL is deprecated; users must now utilize ArgoCD for deployment.

## 2024-07-24 – `6a39f69` by Andrey Bondarenko
- **Deployment Changes:**
  - Removed `redis/cli-deployment.yaml`.
  - Added `redis/tools/cli-deployment.yaml` with identical configuration.
  - Removed `redis/redis-exporter-deployment.yaml` and `redis/redis-exporter-service.yaml`.
  - Added `redis/exporter/redis-exporter-deployment.yaml` and `redis/exporter/redis-exporter-service.yaml` with the same configuration.

- **Namespace:**
  - All changes are within the `redis` namespace.

- **Important Files:**
  - New files for Redis exporter are located in `redis/exporter/`.
  - CLI deployment configuration moved to `redis/tools/`.

- **Resource Limits:**
  - Both `redis-cli` and `redis-exporter` deployments have specified resource limits (memory and CPU).

- **Breaking Changes:**
  - The original paths for `redis-cli` and `redis-exporter` deployments have been altered; ensure to update any references accordingly.

## 2024-07-24 – `d22a81b` by Andrey Bondarenko
- **New Resource Addition**
  - Added `argocd/redis-exporter.yaml` for Redis exporter deployment.

- **Configuration Details**
  - Set project to `default`.
  - Configured source repo: `https://github.com/shaman007/home-k3s.git`, path: `redis/exporter`, target revision: `HEAD`.
  - Destination set to Kubernetes server at `https://kubernetes.default.svc`, namespace: `redis`.
  - Enabled automated sync policy.

## 2024-07-24 – `aff8325` by Andrey Bondarenko
- **Documentation Update:**
  - Added "Mastodon" and "Vault" to the services list in `argocd/README.md`.

## 2024-07-24 – `401cd80` by Andrey Bondarenko
- **Documentation Update**
  - Removed personal notes and installation command from `redis/README.md`.
  - Added note indicating management by Argocd.

## 2024-07-24 – `85fca02` by Andrey Bondarenko
- **Documentation Update**
  - Removed "Redis" from the TODO list in `argocd/README.md`.

## 2024-07-24 – `fce93c5` by Andrey Bondarenko
- **Documentation Update**
  - Corrected grammatical error in `argocd/README.md`: "that mean" → "that means".

## 2024-07-24 – `1d6755b` by Andrey Bondarenko
- **Documentation Update:**
  - Added Longhorn deployment link to `README.md`.

- **Cleanup Instructions:**
  - Updated Docker cleanup section in `README.md`.

## 2024-07-25 – `df60456` by Andrey Bondarenko
- **PostgreSQL Configuration Updates**
  - Added resource requests and limits for CPU and memory in `argocd/postgres.yaml`:
    - Requests: CPU 100m, Memory 100Mi
    - Limits: CPU 1, Memory 500Mi

- **Deployment Changes**
  - Removed `postgres/exporter/cli-deployment.yaml`.
  - Introduced new `postgres/tools/cli-deployment.yaml` with identical configuration to the removed file, ensuring continuity in deployment setup.

- **File Management**
  - Consolidated CLI deployment configuration into `postgres/tools/cli-deployment.yaml`.

## 2024-07-25 – `8660610` by Andrey Bondarenko
- **Deployment Changes**
  - Removed `mysql/cli-deployment.yaml`.
  - Added `mysql/tools/cli-deployment.yaml` with identical deployment configuration.

- **File Structure**
  - Moved MySQL CLI deployment configuration from `mysql/cli-deployment.yaml` to `mysql/tools/cli-deployment.yaml`.

## 2024-07-25 – `7adad35` by Andrey Bondarenko
- **Documentation Updates**
  - Added "Registry" and "external-secrets" to `argocd/README.md`.
  - Created `services/README.md` to document services for K3S.

- **New Configurations**
  - Introduced `argocd/external-secrets.yaml` for External Secrets integration.
  - Added `argocd/vault.yaml` for Vault Helm chart deployment.

- **Service Definition**
  - Created `services/vault-service.yaml` for Vault service configuration, exposing ports 8200 and 8201 with specified external IP.

## 2024-07-25 – `cadd60d` by Andrey Bondarenko
- **New Features:**
  - Added `mysql-secret.yaml` for managing MySQL password via ExternalSecrets.
  - Introduced `secret-store.yaml` to configure Vault as a SecretStore for external secrets.

- **Configuration:**
  - `mysql-secret.yaml` references Vault for password retrieval from the `db` namespace.
  - `secret-store.yaml` specifies Vault server details and authentication method.

- **Important Files:**
  - `mysql/mysql-secret.yaml`
  - `mysql/secret-store.yaml`

- **Breaking Changes:**
  - None noted in this commit.

## 2024-07-25 – `47b9dd8` by Andrey Bondarenko
- **New Feature**: Added `mongo/mongo-secret.yaml` for MongoDB external secrets configuration.
  - Defines `ExternalSecret` for MongoDB credentials with properties for `MONGO_PASSWORD`, `MONGO_ROOT_PASSWORD`, `MONGO_ROOT_USERNAME`, `MONGO_USERNAME`, and `MONGO_USERS_LIST`.

- **Removal**: Deleted `mongo/secret.yaml.asc`, removing the previous PGP encrypted secrets file.

- **Namespace**: The new secret is created in the `db` namespace, referencing the `vault-secret-store`.

- **Breaking Change**: Transition from PGP encrypted secrets to external secrets management; ensure compatibility with existing deployments.

## 2024-07-25 – `18e2b90` by Andrey Bondarenko
- **New Feature**: Added `mysql/registry-secret.yaml` for managing Docker registry secrets using External Secrets.
  - Configures an ExternalSecret named `my-private-registry` in the `db` namespace.
  - Integrates with `vault-secret-store` for secret management.
  - Sets a refresh interval of 1 minute for secret updates.

## 2024-07-25 – `550b911` by Andrey Bondarenko
- **New Features**
  - Added `bitwarden-secret.yaml` with three `ExternalSecret` definitions for `id`, `key`, and `password`.
  - Introduced `secret-store.yaml` defining `SecretStore` for Vault integration.

- **Configuration**
  - Configured Vault server connection in `secret-store.yaml` with server URL and authentication details.

- **Namespace**
  - All resources are created under the `bitwarden` namespace.

- **Important Files**
  - `bitwarden/bitwarden-secret.yaml`
  - `bitwarden/secret-store.yaml`

- **Breaking Changes**
  - None noted in this commit.

## 2024-07-25 – `bbe01d8` by Andrey Bondarenko
- **MySQL Configuration**
  - Removed unnecessary line from `mysql/mysql-secret.yaml`.

## 2024-07-25 – `8e3b1af` by Andrey Bondarenko
- **New Service Configuration**:
  - Added `longhorn-frontend-ip` service in `services/longhorn-system.yaml`.
  - Exposes port 8011 (HTTP) targeting port 8000 for `longhorn-ui`.
  - Configured with external IP `192.168.1.105` in the `longhorn-system` namespace.

## 2024-07-25 – `fcc98bd` by Andrey Bondarenko
- **New Features**
  - Added `clamav/registry-secret.yaml`: Defines an ExternalSecret for Docker registry credentials.
  - Added `clamav/secret-store.yaml`: Configures a SecretStore using Vault for secret management.

- **Configuration**
  - `registry-secret.yaml` references `vault-secret-store` for secret retrieval.
  - `secret-store.yaml` specifies Vault server details and authentication method.

- **Important Paths**
  - `clamav/registry-secret.yaml`
  - `clamav/secret-store.yaml`

- **Breaking Changes**
  - None noted in this commit.

## 2024-07-25 – `fc14d28` by Andrey Bondarenko
- **Secret Store Updates**
  - Renamed `vault-secret-store` to `vault-secret-store-registry` in `clamav/registry-secret.yaml`.
  - Introduced new file `clamav/secret-store-registry.yaml` for the updated SecretStore configuration.
  - Removed deprecated `clamav/secret-store.yaml`.

- **Configuration Changes**
  - Updated Vault token reference in the new registry secret store configuration.

## 2024-07-25 – `aaf419e` by Andrey Bondarenko
- **New Feature**: Added `clamav/secret-store.yaml` for external secrets management.
  - Configures a `SecretStore` using Vault as the provider.
  - Specifies server URL, path, and authentication details.

## 2024-07-25 – `f0f618e` by Andrey Bondarenko
- **Configuration Updates**
  - Updated `bitwarden-secret.yaml`: Changed `secretStoreRef.name` from `vault-secret-store` to `vault-secret-store-postgres`.
  - Modified remote reference key in `bitwarden-secret.yaml` from `bitwarden` to `postgres-access`.

- **New Resource Addition**
  - Added new file `bitwarden/secret-store-postgres.yaml` defining a `SecretStore` with Vault configuration for PostgreSQL.

- **Important Paths**
  - `bitwarden/bitwarden-secret.yaml`
  - `bitwarden/secret-store-postgres.yaml`

- **Breaking Change**
  - The `secretStoreRef` name change may affect existing integrations relying on the previous name.

## 2024-07-25 – `df29b65` by Andrey Bondarenko
- **Removed**: `clamav/secret-store.yaml` file deleted.
- **Impact**: Configuration for Vault Secret Store no longer exists; ensure alternative secret management is in place.

## 2024-07-25 – `6e0c832` by Andrey Bondarenko
- **Configuration Update**
  - Changed `key` from `clamav` to `registry-access` in `clamav/registry-secret.yaml`.

**Note:** Ensure the new key aligns with your registry access configurations.

## 2024-07-25 – `cc5ec46` by Andrey Bondarenko
- **Renamed SecretStore**: Updated `name` from `vault-secret-store` to `vault-secret-store-db` in `bitwarden/secret-store-postgres.yaml`.
- **File Affected**: `bitwarden/secret-store-postgres.yaml`.

## 2024-07-25 – `e2bdd7f` by Andrey Bondarenko
- **Configuration Update**
  - Changed `secretStoreRef.name` from `vault-secret-store-postgres` to `vault-secret-store-db` in `bitwarden/bitwarden-secret.yaml`.

- **Impact**
  - Ensure compatibility with the new secret store configuration.

## 2024-07-25 – `f18ae22` by Andrey Bondarenko
- **Configuration Update**
  - Changed `postgres-access` key to `db` in `bitwarden/bitwarden-secret.yaml`.
  - Updated property from `password` to `postgres-pass`.

- **File Affected**
  - `bitwarden/bitwarden-secret.yaml` modified.

## 2024-07-25 – `845706a` by Andrey Bondarenko
- **Secret Configuration Update**
  - Renamed `postgres-pass` to `password` in `bitwarden/bitwarden-secret.yaml`.
  - Updated `secretKey` from `password` to `postgres-pass`.
  - Changed `property` reference from `postgres-pass` to `postgress-pass`.

**Note**: Ensure downstream services are updated to reflect these changes.

## 2024-07-25 – `cc5af53` by Andrey Bondarenko
- **Configuration Updates**:
  - Renamed target secret from `password` to `postgres-pass` in `bitwarden/bitwarden-secret.yaml`.
  - Updated `secretKey` from `postgres-pass` to `password` in the same file.

- **File Affected**:
  - `bitwarden/bitwarden-secret.yaml`

## 2024-07-26 – `9e8831e` by Andrey Bondarenko
- **Documentation Update**
  - Corrected wording in `services/README.md` for clarity.

- **New Service Configuration**
  - Added `services/argocd.yaml` to define ArgoCD frontend service with external IP configuration.
  - Configured service to route traffic from port 8012 to ArgoCD server on port 8080.

## 2024-07-26 – `368bc99` by Andrey Bondarenko
- **Documentation:**
  - Added `vault/README.md` for project overview.

- **Configuration Changes:**
  - Removed `vault/spc-vault-database.yaml`, `vault/values.yaml`, and `vault/webapp-pod.yaml` files, indicating a significant restructuring or removal of related configurations.

**Breaking Changes:**
- Deletion of multiple configuration files may impact deployment and functionality of the vault service.

## 2024-07-29 – `9520a5f` by Andrey Bondarenko
- **Resource Configuration Update**
  - Increased CPU limit for PostgreSQL from `1` to `2` in `argocd/postgres.yaml`.

## 2024-07-29 – `2c8ecc6` by Andrey Bondarenko
- **Storage Configuration Update**
  - Increased PVC storage request from 1000Mi to 10Gi (10737418240 bytes) in `minecraft/minecraft-pvc.yaml`.

## 2024-07-29 – `8a36b86` by Andrey Bondarenko
- **New Files Added:**
  - Created `conduit/redis-secret.yaml` for Redis password management using ExternalSecrets.
  - Created `conduit/secret-store.yaml` to define a SecretStore for Vault integration.
  - Created `mastodon/redis-secret.yaml` for Redis password management in Mastodon.
  - Created `mastodon/secret-store.yaml` for Vault SecretStore configuration in Mastodon.

- **Configuration Details:**
  - Both SecretStores reference a Vault server at `http://192.168.1.111:8200` with KV version 2.
  - Redis passwords are managed under the same name (`redis-password`) in both namespaces.

- **Namespaces:**
  - `conduit` and `mastodon` namespaces are utilized for secret management.

- **Important Note:**
  - Ensure Vault server is accessible and properly configured for the new SecretStore references.

## 2024-07-29 – `6f4cd5d` by Andrey Bondarenko
- **Documentation Updates**
  - Added "Vault" and "Argocd" to the main README.md.
  - Removed "Vault" from the argocd/README.md.

- **General Notes**
  - Updated TODO section in README.md to include "Vault for secrets" as a future task.

## 2024-07-30 – `6bd0dc4` by Andrey Bondarenko
- **Secret Store Updates**
  - Renamed `vault-secret-store` to `vault-secret-store-registry` in `mysql/registry-secret.yaml`.
  - Updated `vault-secret-store` to `vault-secret-store-registry` in `mysql/secret-store.yaml`.

- **Token Reference Change**
  - Changed token reference from `vault-token` to `vault-token-registry` in `mysql/secret-store.yaml`.

- **File Modifications**
  - Updated `mysql/registry-secret.yaml` and `mysql/secret-store.yaml` to reflect new naming conventions.

## 2024-07-30 – `b24d0bd` by Andrey Bondarenko
- **Secret Store Configuration**
  - Added new `SecretStore` definition for Vault in `mysql/secret-store.yaml`.
  - Configured Vault server details, including server URL and authentication token reference.

- **File Path**
  - Updated file: `mysql/secret-store.yaml`.

- **Breaking Change**
  - Introduced a new API version (`external-secrets.io/v1beta1`), ensure compatibility with existing setups.

## 2024-07-30 – `ad84404` by Andrey Bondarenko
- **Configuration Update**
  - Changed `key` from `db` to `registry` in `mysql/registry-secret.yaml`.

- **File Affected**
  - `mysql/registry-secret.yaml` updated to reflect new registry key configuration.

## 2024-07-30 – `fb95726` by Andrey Bondarenko
- **Configuration Update**
  - Changed `key` from `registry` to `registry-access` in `mysql/registry-secret.yaml`.

- **File Affected**
  - `mysql/registry-secret.yaml` updated to reflect new key for remote reference.

## 2024-07-30 – `f88dc2b` by Andrey Bondarenko
- **New Features**
  - Added `registry-secret.yaml` to define an `ExternalSecret` for private registry access in the `mail` namespace.
  - Introduced `secret-store-registry.yaml` to configure a `SecretStore` using Vault for secret management.

- **Configuration**
  - `ExternalSecret` references a secret key `mysecret` from Vault for Docker registry credentials.
  - `SecretStore` specifies Vault server details and authentication method via token reference.

- **Important Files**
  - `mail/registry-secret.yaml`
  - `mail/secret-store-registry.yaml`

- **Breaking Changes**
  - None noted in this commit.

## 2024-07-30 – `780cf7c` by Andrey Bondarenko
- **New External Secrets**:
  - Added `mail/mail-secret.yaml` for `andreybondarenko.key` and `passwd` secrets.
  - Added `minecraft/registry-secret.yaml` for private registry access.
  - Added `nextcloud/registry-secret.yaml` for private registry access.

- **Secret Store Configuration**:
  - Introduced `mail/secret-store.yaml` and `mail/secret-store-registry.yaml` for Vault integration.
  - Introduced `minecraft/secret-store-registry.yaml` for Vault integration.
  - Introduced `nextcloud/secret-store.yaml` and `nextcloud/secret-store-registry.yaml` for Vault integration.

- **File Deletion**:
  - Removed `mail/secret-store-registry.yaml`.

- **Important Paths**:
  - All new files are located under `mail`, `minecraft`, and `nextcloud` directories.

## 2024-07-30 – `90af722` by Andrey Bondarenko
- **Secret Files Updates**:
  - Updated PGP messages in `bitwarden/secret.yaml.asc`, `camera/secret.yaml.asc`, `clamav/secret.yaml.asc`, and `conduit/secret.yaml.asc`.
  - Changes include modifications to encrypted content across multiple services.

- **Affected Services**:
  - Services impacted include Bitwarden, Camera, ClamAV, and Conduit, among others.

- **File Modifications**:
  - Total of 20 files modified, primarily focused on `secret.yaml.asc` files for various services, indicating a bulk update of sensitive configurations.

- **Security Note**:
  - Ensure to review and securely manage the updated PGP keys and secrets post-update.

## 2024-07-30 – `16133e0` by Andrey Bondarenko
- **New Secrets Management**:
  - Added `ExternalSecret` for private registry in `plex` namespace (`plex/registry-secret.yaml`).
  - Added `ExternalSecret` for private registry in `wordpress` namespace (`wordpress/registry-secret.yaml`).

- **Secret Store Configuration**:
  - Introduced `SecretStore` for Vault integration in `plex` namespace (`plex/secret-store.yaml`).
  - Introduced `SecretStore` for Vault integration in `wordpress` namespace (`wordpress/secret-store.yaml`).

- **Vault Configuration**:
  - Both `SecretStore` configurations point to Vault server at `http://192.168.1.111:8200`, using KV version 2 for secrets retrieval.

## 2024-07-30 – `16eb8ee` by Andrey Bondarenko
- **Documentation Update**
  - Marked TT-RSS deployment instructions in `ttrss/README.md` as **OBSOLETE**.

## 2024-07-30 – `2262603` by Andrey Bondarenko
### CHANGELOG for Commit 2262603

#### New Features
- **Mastodon**: Added multiple `ExternalSecret` configurations for managing secrets (e.g., AWS keys, OTP, and database passwords) in `mastodon/mastodon-secrets.yaml`.
- **Minio**: Introduced `ExternalSecret` for private registry access in `minio-single/registry-secret.yaml`.
- **Postgres**: Added `ExternalSecret` for PostgreSQL exporter in `postgres/exporter/pg-secret.yaml`.
- **Redis**: Created `ExternalSecret` for private registry access in `redis/registry-secret.yaml`.

#### Updates
- **Secret Stores**: New `SecretStore` configurations for Mastodon, Minio, and Redis in their respective `secret-store.yaml` files, pointing to a Vault server for secret management.

#### Removals
- **MySQL**: Removed `registry-secret.yaml` and `secret-store.yaml` files, indicating a shift in secret management strategy.

#### Namespace Changes
- **Plex to Redis**: Updated namespace for `my-private-registry` from `plex` to `redis` in `plex/registry-secret.yaml`.

#### Important Files
- `mastodon/mastodon-secrets.yaml`
- `minio-single/registry-secret.yaml`
- `postgres/exporter/pg-secret.yaml`
- `redis/registry-secret.yaml`

#### Breaking Changes
- Removal of MySQL secret management files may affect deployments relying on those configurations.

## 2024-07-30 – `a2ddab4` by Andrey Bondarenko
- **New Secrets Configuration:**
  - Added `minecraft/minecraft-secret.yaml` for managing secrets in the Minecraft namespace.
  - Introduced `unifi/poller/unifi-secret.yaml` for Unifi password management.

- **Secret Store Definitions:**
  - Created `minecraft/secret-store.yaml` to define the vault secret store for Minecraft.
  - Added `unifi/poller/secret-store.yaml` for Unifi's secret store configuration.

- **Removed Legacy Files:**
  - Deleted `minecraft/registry-secret.yaml` and `minecraft/secret-store-registry.yaml` as they are now obsolete.

- **Important Notes:**
  - All new configurations utilize the external-secrets.io API.
  - Ensure the vault server at `http://192.168.1.111:8200` is accessible for the new secret stores.

## 2024-07-30 – `f5d7a46` by Andrey Bondarenko
- **New Resources**:
  - Added `metrics/objstore-secret.yaml`: Defines `ExternalSecret` for Thanos object storage.
  - Added `metrics/secret-store.yaml`: Configures `SecretStore` for Vault integration.

- **Configuration Details**:
  - `ExternalSecret` references `vault-secret-store` for secret management.
  - Vault server configured at `http://192.168.1.111:8200`, using KV version 2.

- **Namespace**: Both resources are created under the `monitoring` namespace.

## 2024-07-30 – `3b7e715` by Andrey Bondarenko
- **Deployment Changes**
  - Updated `plex/plex-deployment.yaml`: Removed commented-out image reference for registry.

- **Secret Management**
  - Deleted `plex/registry-secret.yaml`: Removed external secret configuration for private registry.
  - Deleted `plex/secret-store.yaml`: Removed secret store configuration for Vault.
  - Deleted `plex/secret.yaml.asc`: Removed PGP encrypted secret file.

**Breaking Changes**: Removal of secret management files may affect deployments relying on external secrets and Vault integration.

## 2024-07-30 – `b25faa2` by Andrey Bondarenko
- **MySQL Secrets Configuration**
  - Added `ExternalSecret` for MySQL password in `mysql/mysql-secret.yaml`.
  - Introduced `ExternalSecret` for private registry access in `mysql/mysql-secret.yaml`.

- **Secret Store Setup**
  - Created `SecretStore` for Vault in `mysql/secret-store.yaml` (namespace: `db`).
  - Added `SecretStore` for private registry in `mysql/secret-store.yaml` (namespace: `clamav`).

- **Networking**
  - Configured Vault server address (`http://192.168.1.111:8200`) in both `SecretStore` entries.

- **Breaking Changes**
  - New dependencies on external secrets management; ensure compatibility with existing configurations.

## 2024-07-30 – `82e1ddc` by Andrey Bondarenko
- **Namespace Update**: Changed `namespace` from `clamav` to `db` in `mysql/secret-store.yaml`.
- **File Affected**: `mysql/secret-store.yaml` updated to reflect new namespace configuration.

## 2024-07-30 – `bc4e80e` by Andrey Bondarenko
- **New Resources**:
  - Added `argocd/redis.yaml` for ArgoCD configuration of Redis chart.
  - Introduced `redis/registry-secret.yaml` with `ExternalSecret` for managing Redis password.
  - Created `redis/secret-store.yaml` defining `SecretStore` for Vault integration.

- **Configuration Updates**:
  - Configured `ExternalSecret` to pull `redis-password` from Vault.
  - Set up `SecretStore` to connect to Vault at `http://192.168.1.111:8200`.

- **Namespace**:
  - All new resources are deployed in the `redis` namespace.

- **Breaking Changes**:
  - Introduced dependency on external secrets management; ensure Vault is properly configured and accessible.

## 2024-07-30 – `ec84ead` by Andrey Bondarenko
- **Postgres**:
  - Added `postgres-secret.yaml` for managing PostgreSQL password via External Secrets.

- **Redis**:
  - Updated `registry-secret.yaml`:
    - Changed target name from `redis` to `redis-password`.
    - Updated secret key from `redis-password` to `password`.

- **Files Affected**:
  - `postgres/postgres-secret.yaml` (new)
  - `redis/registry-secret.yaml` (modified)

- **Note**: Ensure compatibility with existing secret management configurations due to key and target name changes.

## 2024-07-31 – `d849378` by Andrey Bondarenko
- **Image Update**: Changed Thanos container image from `quay.io/thanos/thanos:v0.30.0` to `quay.io/thanos/thanos:latest` in:
  - `thanos-compactor.yaml`
  - `thanos-queuer.yaml`
  - `thanos-storage-gateway.yaml`

- **Log Level Change**: Updated log level from `debug` to `info` in:
  - `thanos-compactor.yaml`
  - `thanos-queuer.yaml`
  - `thanos-storage-gateway.yaml`

- **File Paths**: Modified configurations in:
  - `thanos/thanos-compactor.yaml`
  - `thanos/thanos-queuer.yaml`
  - `thanos/thanos-storage-gateway.yaml`

No breaking changes noted.

## 2024-07-31 – `f9f8036` by Andrey Bondarenko
- **Image Version Update**:
  - Updated Thanos container image from `latest` to `v0.35.1` in:
    - `thanos/thanos-compactor.yaml`
    - `thanos/thanos-queuer.yaml`
    - `thanos/thanos-storage-gateway.yaml`

- **Configuration Consistency**:
  - Ensured all Thanos components use the same image version for consistency and stability.

## 2024-07-31 – `9b27eea` by Andrey Bondarenko
- **Image Version Downgrade**:
  - Updated `thanos` image from `v0.35.1` to `v0.30.0` in:
    - `thanos/thanos-compactor.yaml`
    - `thanos/thanos-queuer.yaml`
    - `thanos/thanos-storage-gateway.yaml`

- **Configuration Files Modified**:
  - Changes applied to all three Thanos configuration files affecting container specifications.

## 2024-07-31 – `7f39dfd` by Andrey Bondarenko
- **Upgrade Thanos Images**:
  - Updated Thanos container image from `v0.30.0` to `v0.35.1` in:
    - `thanos/thanos-compactor.yaml`
    - `thanos/thanos-queuer.yaml`
    - `thanos/thanos-storage-gateway.yaml`

- **Files Affected**:
  - `thanos/thanos-compactor.yaml`
  - `thanos/thanos-queuer.yaml`
  - `thanos/thanos-storage-gateway.yaml`

- **Breaking Changes**: None noted in the diff.

## 2024-07-31 – `138f04a` by Andrey Bondarenko
- **Dependency Update**
  - Updated Thanos image version from `v0.31.0` to `v0.35.1` in `metrics/kubernetes-prometheus/prometheus-deployment.yaml`.

## 2024-07-31 – `21267ce` by Andrey Bondarenko
- **Enhancements:**
  - Added `initContainers` to `thanos-compactor.yaml` and `thanos-storage-gateway.yaml` for volume ownership adjustment.
  - Included `volume-mount-hack` init container using `busybox` to change ownership of `/data` to UID 1001.

- **Affected Files:**
  - `thanos/thanos-compactor.yaml`
  - `thanos/thanos-storage-gateway.yaml`

- **Breaking Change:**
  - Ensure that the `/data` directory is accessible with the correct permissions post-deployment.

## 2024-07-31 – `387ad4c` by Andrey Bondarenko
### CHANGELOG for Commit 387ad4c

#### Configuration Changes
- Renamed `prometheus.yaml.tmpl` to `prometheus.yaml` in `metrics/kubernetes-prometheus/config-map.yaml`.
- Updated Prometheus configuration file path in `prometheus-deployment.yaml` from `/etc/prometheus-shared/prometheus.yaml` to `/etc/prometheus/prometheus.yaml`.

#### Deployment Updates
- Changed Prometheus image tag to `latest` in `prometheus-deployment.yaml`.
- Removed deprecated reloader configuration options in `prometheus-deployment.yaml`.

#### Resource Management
- Set size limit of `emptyDir` for `prometheus-config-shared` to 10Mi in `prometheus-deployment.yaml`.

### Breaking Changes
- Configuration file path changes may require updates to existing deployments.

## 2024-07-31 – `c52c82a` by Andrey Bondarenko
- **Documentation Updates**
  - Removed TODO item for "Prometheus, Thanos - non-root containers" from `README.md`.

## 2024-07-31 – `395c5cb` by Andrey Bondarenko
- **Documentation Update**
  - Removed mention of "Prometheus operator" from README.md.

## 2024-07-31 – `648be85` by Andrey Bondarenko
- **Documentation Updates:**
  - Updated `README.md` to include `kubectl apply` command for Longhorn installation.
  - Changed code block formatting in `argocd/README.md` to specify `bash` for clarity.

- **File Changes:**
  - Modified `README.md` and `argocd/README.md` for improved command usage and readability.

## 2024-07-31 – `9466efe` by Andrey Bondarenko
- **Secret Files Updated**:
  - Updated PGP messages in 17 secret.yaml.asc files across various services:
    - `bitwarden/secret.yaml.asc`
    - `camera/secret.yaml.asc`
    - `clamav/secret.yaml.asc`
    - `conduit/secret.yaml.asc`
    - `mail/secret.yaml.asc`
    - `mastodon/secret.yaml.asc`
    - `metrics/secret.yaml.asc`
    - `minecraft/secret.yaml.asc`
    - `minio-single/secret.yaml.asc`
    - `mysql/secret.yaml.asc`
    - `nextcloud/secret.yaml.asc`
    - `postgres/secret.yaml.asc`
    - `redis/secret.yaml.asc`
    - `ttrss/secret.yaml.asc`
    - `unifi/secret.yaml.asc`
    - `wordpress/secret.yaml.asc`
    - `your-spotify/secret.yaml.asc`

- **Security**:
  - All updated files contain new PGP encrypted content, enhancing security for sensitive configurations.

## 2024-07-31 – `be0dcac` by Andrey Bondarenko
- **Configuration Update**
  - Increased `tmp` directory `sizeLimit` from 100Mi to 256Mi in `nextcloud/php-deployment.yaml`.

## 2024-07-31 – `14c4a61` by Andrey Bondarenko
- **Resource Configuration Update**:
  - Increased memory requests from **800Mi** to **1000Mi** in `mysql/mysql-deployment.yaml`.
  - Increased memory limits from **1200Mi** to **3200Mi** in `mysql/mysql-deployment.yaml`.

## 2024-08-01 – `baa8e5e` by Andrey Bondarenko
- **Added External Secrets**:
  - Introduced `redis-password` and `rspamd-redis` ExternalSecrets in `mail/mail-secret.yaml` for Redis integration.
  - Configured `rspamd-redis` with a custom Redis configuration template.

- **New Secret Store**:
  - Created `vault-secret-store-redis` in `mail/secret-store.yaml` for managing Redis secrets via Vault.

- **Configuration**:
  - Set `refreshInterval` to "1m" for both ExternalSecrets.
  - Specified Vault server details and authentication in the new SecretStore.

- **Breaking Changes**:
  - New dependencies on external secrets management; ensure compatibility with existing configurations.

## 2024-08-01 – `423a4fd` by Andrey Bondarenko
- **Configuration Changes:**
  - Renamed `php-fpm-config` to `php-fpm-config-template` in `php-configmap.yaml`.
  - Updated session handling from files to Redis in `php-configmap.yaml`.

- **Deployment Updates:**
  - Changed volume source for `phpini` from ConfigMap to Secret in `php-deployment.yaml`.
  - Added new volume `wwwconf` for the updated ConfigMap in `php-deployment.yaml`.

- **Secret Management:**
  - Introduced `php-secret.yaml` for managing Redis password via External Secrets.
  - Added `vault-secret-store-redis` configuration in `secret-store.yaml` for external secret management.

- **Breaking Changes:**
  - Existing configurations relying on `php-fpm-config` will need to be updated to use `php-fpm-config-template`.
  - Session storage method has changed to Redis, requiring Redis setup and configuration.

## 2024-08-01 – `0876467` by Andrey Bondarenko
- **Configuration Management**
  - Added `php-configmap.yaml` for PHP-FPM configuration settings.
  - Introduced `php-secret.yaml` to manage secrets for PHP-FPM using External Secrets.

- **Deployment Updates**
  - Modified `php-deployment.yaml` to mount PHP configuration from the new ConfigMap.
  - Updated volume mounts to include `phpini` for PHP settings, removed `varlib` session storage.

- **Secret Store Configuration**
  - Added `vault-secret-store-redis` in `secret-store.yaml` for managing Redis secrets.

- **Breaking Changes**
  - Removal of `varlib` volume may affect session handling; ensure session management is updated accordingly.

## 2024-08-01 – `c6dc533` by Andrey Bondarenko
- **Secret Updates**:
  - Updated PGP messages in 17 `secret.yaml.asc` files across various services including:
    - `bitwarden`
    - `camera`
    - `clamav`
    - `conduit`
    - `mail`
    - `mastodon`
    - `metrics`
    - `minecraft`
    - `minio-single`
    - `mysql`
    - `nextcloud`
    - `postgres`
    - `redis`
    - `ttrss`
    - `unifi`
    - `wordpress`
    - `your-spotify`

- **Security**:
  - All updated files contain new encrypted PGP messages, ensuring enhanced security for sensitive configurations.

- **File Paths**:
  - Changes made in multiple directories, indicating a broad update across the application’s configuration files.

- **Breaking Changes**:
  - Ensure to update any dependent systems or configurations that rely on the previous PGP messages as they have been completely replaced.

## 2024-08-01 – `98acf44` by Andrey Bondarenko
- **Configuration Updates:**
  - Added Redis configuration to `nextcloud/php-configmap.yaml`.
  - Updated session save path format in `nextcloud/php-configmap.yaml`.

- **Deployment Changes:**
  - Set `imagePullPolicy: Always` in `nextcloud/php-deployment.yaml`.
  - Adjusted volume mounts for PHP configuration files in `nextcloud/php-deployment.yaml`.

- **File Modifications:**
  - `nextcloud/php-configmap.yaml` and `nextcloud/php-deployment.yaml` updated for improved Redis integration and configuration management.

## 2024-08-01 – `c7da43a` by Andrey Bondarenko
- **Nextcloud:**
  - Increased replicas from 1 to 4 in `nextcloud/php-deployment.yaml`.

- **WordPress:**
  - Increased replicas from 1 to 2 in `wordpress/nginx-deployment.yaml` and `wordpress/php-deployment.yaml`.
  - Added new `www.conf` configuration to `wordpress/php-configmap.yaml` for PHP-FPM settings.
  - Updated volume mounts in `wordpress/php-deployment.yaml` to include `www.conf` alongside existing `php.ini`.

**Important Files:**
- `nextcloud/php-deployment.yaml`
- `wordpress/nginx-deployment.yaml`
- `wordpress/php-configmap.yaml`
- `wordpress/php-deployment.yaml`

**Breaking Changes:**
- Increased resource allocation may require adjustments in infrastructure to handle new replica counts.

## 2024-08-01 – `148a333` by Andrey Bondarenko
- **Configuration Changes**:
  - Updated `memory_limit` in `wordpress/php-configmap.yaml` from `-1` to `256` in the first instance.
  - Adjusted `memory_limit` from `-1` to `236` in the second instance.

- **Impact**:
  - Limits PHP memory usage, potentially affecting performance and resource allocation.

## 2024-08-10 – `4292cd6` by Andrey Bondarenko
- **Deployment Configuration**
  - Added `emptyDir` volume named `tmp` with a size limit of 100Mi in `minecraft/minecraft-deployment.yaml`.
  - Mounted `tmp` volume at `/tmp` in the container.

- **Environment Variables**
  - Introduced environment variable `CREATE_CONSOLE_IN_PIPE` set to `"TRUE"` in the container configuration.

## 2024-08-20 – `7f2a1bb` by Andrey Bondarenko
### CHANGELOG for Commit 7f2a1bb

- **New Configuration Files:**
  - Added `.yamllint` for YAML linting configuration.

- **ArgoCD Configuration Updates:**
  - Added `project: default` and `source.repoURL` entries to multiple YAML files in `argocd/`:
    - `bitwarden.yaml`, `cert-manager.yaml`, `clamav.yaml`, `collabora.yaml`, `conduit.yaml`, `elasticsearch.yaml`, `external-secrets.yaml`, `graphana.yaml`, `ingress-nginx.yaml`, `kube-state-metrics.yaml`, `kubernetes-node-exporter.yaml`, `kubernetes-prometheus.yaml`, `mail.yaml`, `minecraft.yaml`, `minio.yaml`, `mongo.yaml`, `mysql.yaml`, `nextcloud.yaml`, `nfs-provisioner.yaml`, `plex.yaml`, `postgres-exporter.yaml`, `postgres.yaml`, `promtail.yaml`, `redis-exporter.yaml`, `redis.yaml`, `thanos.yaml`, `vault.yaml`, `wordpress.yaml`, `your-spotify.yaml`.

- **Bitwarden Updates:**
  - Introduced `bitwarden-secret.yaml` with `ExternalSecret` configuration.

### Important Notes:
- Ensure compatibility with existing configurations due to the addition of `project` and `source` fields across multiple files.
- Review the new `.yamllint` settings to align with project standards.

## 2024-08-21 – `f628dce` by Andrey Bondarenko
- **Pre-commit Configuration Updates**
  - Removed commented-out hooks for `check-json`, `forbid-submodules`, and `pretty-format-json`.
  - Added `detect-private-key` hook to enhance security checks.
  - Integrated `gitleaks` repository for secret detection, version updated to `v8.16.1`.

## 2024-08-29 – `16a0ee5` by Andrey Bondarenko
- **Deployment Configuration**
  - Changed `replicas` from 4 to 1 in `nextcloud/php-deployment.yaml`.
  - This reduces the number of PHP backend instances for Nextcloud.

## 2024-09-16 – `a9acd5b` by Andrey Bondarenko
- **Removed PersistentVolumeClaims**:
  - Deleted `nextcloud-sessions` PVC from `nextcloud/php-pvc.yaml`.
  - Deleted `wordpress-sessions` PVC from `wordpress/php-pvc.yaml`.

- **Updated Storage Requests**:
  - `nextcloud` PVC storage request set to `200Gi`.
  - `wordpress` PVC storage request set to `1Gi`.

- **Files Affected**:
  - `nextcloud/php-pvc.yaml`
  - `wordpress/php-pvc.yaml`

- **Breaking Changes**:
  - Removal of session PVCs may affect session persistence for both Nextcloud and WordPress deployments.

## 2024-09-16 – `4eed550` by Andrey Bondarenko
- **New Resource**: Added ArgoCD application configuration for Longhorn.
  - **File**: `argocd/longhorn.yaml`
  - **Details**:
    - Application named `longhorn` in the `argocd` namespace.
    - Sources from Longhorn Helm chart repository (`https://charts.longhorn.io/`, version `v1.7.0`).
    - Sync policy includes `CreateNamespace=true`.
    - Destination set to `longhorn-system` namespace in the Kubernetes cluster.

## 2024-09-16 – `d41f602` by Andrey Bondarenko
- **Dependency Update**
  - Updated Longhorn chart version from `v1.7.0` to `v1.7.1` in `argocd/longhorn.yaml`.

## 2024-09-19 – `988cc36` by Andrey Bondarenko
- **Resource Configuration Update**
  - Increased Redis CPU limit from `2000m` to `4000m` in `redis/redis-values.yaml`.

## 2024-09-19 – `9424f21` by Andrey Bondarenko
- **Dependency Update**
  - Updated `targetRevision` for `vault` chart from `1.4.16` to `1.17.2` in `argocd/vault.yaml`.

## 2024-09-19 – `948554b` by Andrey Bondarenko
- **Documentation Updates**
  - Updated `vault/README.md` for clarity and accuracy.

## 2024-09-19 – `cd3a38c` by Andrey Bondarenko
- **Dependency Update**
  - Updated `targetRevision` for Vault chart in `argocd/vault.yaml` from `1.17.2` to `1.4.22`.

**Note:** Ensure compatibility with the new chart version.

## 2024-09-19 – `d913fac` by Andrey Bondarenko
- **Resource Configuration Updates**:
  - Added CPU resource requests and limits for master and replica in `argocd/redis.yaml`.
    - `master.resources.requests.cpu`: 400m
    - `master.resources.limits.cpu`: 4000m
    - `replica.resources.requests.cpu`: 400m
    - `replica.resources.limits.cpu`: 4000m

## 2024-09-19 – `d05d66f` by Andrey Bondarenko
- **Configuration Updates**
  - Added Helm parameters for Vault deployment in `argocd/vault.yaml`:
    - Set `server.replicaCount` to `1`.
    - Defined CPU resource requests and limits for `server` and `injector` components:
      - `server.resources.requests.cpu`: 400m
      - `server.resources.limits.cpu`: 4000m
      - `injector.resources.requests.cpu`: 400m
      - `injector.resources.limits.cpu`: 2000m

## 2024-09-19 – `619825e` by Andrey Bondarenko
- **Resource Configuration Updates**:
  - Increased `primary.resources.requests.memory` from `100Mi` to `150Mi` in `argocd/postgres.yaml`.
  - Increased `primary.resources.limits.cpu` from `2` to `4` in `argocd/postgres.yaml`.

**Note**: Ensure adequate resource availability in the environment to accommodate increased limits.

## 2024-09-19 – `acd4793` by Andrey Bondarenko
- **Dependency Update**
  - Updated `targetRevision` for Elasticsearch from `21.0.1` to `21.3.17` in `argocd/elasticsearch.yaml`.

- **Resource Configuration**
  - Added CPU resource requests and limits for:
    - Coordinating nodes
    - Master nodes
    - Data nodes
    - Ingest nodes

- **File Modified**
  - `argocd/elasticsearch.yaml` updated with new Helm parameters for resource management.

## 2024-09-19 – `5878504` by Andrey Bondarenko
- **PostgreSQL Configuration (argocd/postgres.yaml)**
  - Added `auth.existingSecret` with value `postgres-password`.
  - Introduced `auth.secretKeys.adminPasswordKey` set to `password`.
  - Increased memory limit from `500Mi` to `1500Mi`.
  - Added CPU requests and limits for metrics: `100m` and `500m` respectively.

- **Unifi Poller Deployment (unifi/poller/unifi-poller-deployment.yaml)**
  - Increased CPU limit from `2000m` to `2500m`.

**Note:** Ensure resource limits are compatible with your cluster's capacity.

## 2024-09-19 – `4fd28dc` by Andrey Bondarenko
- **PostgreSQL Resource Configuration**
  - Updated CPU limit from `500m` to `1000m` in `argocd/postgres.yaml`.

## 2024-09-19 – `c5e7639` by Andrey Bondarenko
- **Resource Configuration Update**
  - Increased CPU limit from `1300m` to `4000m` in `wordpress/php-deployment.yaml`.

## 2024-09-19 – `54545fb` by Andrey Bondarenko
- **Deployment Changes:**
  - Removed pod affinity settings from `nginx-deployment.yaml` and `php-deployment.yaml`.

- **Persistent Volume Claim Update:**
  - Changed access mode from `ReadWriteOnce` to `ReadWriteMany` in `php-pvc.yaml`.

- **Resource Limits:**
  - No changes to resource limits; existing configurations retained.

## 2024-09-19 – `36ef25e` by Andrey Bondarenko
- **Deployment Changes:**
  - Increased replicas from 1 to 3 for both `nginx-deployment.yaml` and `php-deployment.yaml`.
  - Removed pod affinity rules from both deployment files.

- **Persistent Volume Claim Update:**
  - Changed access mode from `ReadWriteOnce` to `ReadWriteMany` in `php-pvc.yaml`.

- **Files Modified:**
  - `nextcloud/nginx-deployment.yaml`
  - `nextcloud/php-deployment.yaml`
  - `nextcloud/php-pvc.yaml`

- **Breaking Change:**
  - The change in PVC access mode may affect existing volume usage and compatibility with other components.

## 2024-09-19 – `0cb06f8` by Andrey Bondarenko
- **Deployment Scaling**
  - Increased replicas from 2 to 3 for both Nginx (`wordpress/nginx-deployment.yaml`) and PHP (`wordpress/php-deployment.yaml`) deployments.

## 2024-10-11 – `c12cd1b` by Andrey Bondarenko
- **Documentation Update**
  - Updated image link in `README.md` to reflect new rack photo.

## 2024-10-16 – `ec5d83d` by Andrey Bondarenko
- **Configuration Update**
  - Increased `tmp` volume `sizeLimit` from 256Mi to 512Mi in `nextcloud/php-deployment.yaml`.

## 2024-10-16 – `eb10f13` by Andrey Bondarenko
- **Service Configuration**
  - Removed empty line in `plex/plex-service.yaml` for cleaner formatting.

## 2024-10-16 – `84bcce2` by Andrey Bondarenko
- **Deployment Configuration**
  - Removed `imagePullSecrets` section from `plex/plex-deployment.yaml`.
- **Volume Configuration**
  - No changes made to volume definitions.

## 2024-10-16 – `ca0452a` by Andrey Bondarenko
- **New Service Configuration**: Added `rancher-service.yaml` for Rancher service deployment.
  - Defines a Kubernetes Service of type `NodePort` for the Rancher application.
  - Exposes port `1443` mapped to target port `443`.
  - Uses external IP `192.168.1.105` for accessibility.
  - Labels and selectors configured for proper service identification.

## 2024-10-16 – `76ccad7` by Andrey Bondarenko
- **New Resources Added:**
  - Created `ClusterRoleBinding` in `rancher/rancher-crb.yaml` for default service account with cluster-admin privileges.
  - Added `Deployment` in `rancher/rancher-deployment.yaml` for Rancher application, including resource requests and limits.
  - Introduced `PersistentVolumeClaim` in `rancher/rancher-pvc.yaml` for Rancher with a storage request of 2Gi using Longhorn.
  - Defined `ServiceAccount` in `rancher/rancher-service-acc.yaml` for default namespace.

- **File Structure:**
  - All new files are located in the `rancher` directory.

## 2024-10-16 – `b4e9168` by Andrey Bondarenko
- **Documentation Update**
  - Corrected namespace in `README.md` for Kubernetes secret retrieval: changed from `default` to `mail`.

## 2024-10-16 – `5132085` by Andrey Bondarenko
- **New Configuration**: Added `argocd/rancher.yaml` for ArgoCD integration.
  - Configures project to use default namespace.
  - Sets source repository to `https://github.com/shaman007/home-k3s.git` with path `rancher`.
  - Targets Kubernetes cluster at `https://kubernetes.default.svc` in `rancher` namespace.

## 2024-10-16 – `8a5f956` by Andrey Bondarenko
- **Configuration Updates**
  - Added `90-sieve` plugin configuration to `dovecot-configMap.yaml` for Sieve script management.

- **Deployment Adjustments**
  - Updated `dovecot-deployment.yaml` to include `90-sieve` configMap and mount it at `/etc/dovecot/conf.d/90-sieve.conf`.

- **File Changes**
  - New configuration file: `90-sieve.conf` created in the Dovecot configuration directory.

## 2024-10-16 – `68ef8e5` by Andrey Bondarenko
- **ArgoCD Configuration Updates:**
  - Added YAML front matter (`---`) to `argocd/longhorn.yaml` and `argocd/rancher.yaml`.

- **Mail Configuration:**
  - Updated `mail/dovecot-configMap.yaml` (details not specified in the diff).

- **Rancher Role and Service Updates:**
  - Modified `rancher/rancher-crb.yaml`, `rancher/rancher-pvc.yaml`, and `rancher/rancher-service-acc.yaml` (details not specified in the diff).

No breaking changes noted.

## 2024-10-17 – `13e4ff5` by Andrey Bondarenko
- **Secret Configuration Updates**:
  - Increased `refreshInterval` from `1m` to `15m` for multiple secret configurations across various namespaces including:
    - `bitwarden`, `clamav`, `conduit`, `mail`, `mastodon`, `metrics`, `minecraft`, `minio-single`, `mongo`, `mysql`, `nextcloud`, `postgres`, and `redis`.

- **Files Affected**:
  - Key files modified include:
    - `bitwarden/bitwarden-secret.yaml`
    - `clamav/registry-secret.yaml`
    - `mail/mail-secret.yaml`
    - `mastodon/mastodon-secrets.yaml`
    - `postgres/postgres-secret.yaml`

- **Namespace Impact**:
  - Changes affect multiple namespaces: `bitwarden`, `clamav`, `mail`, `mastodon`, `minecraft`, `nextcloud`, `db`, and `monitoring`.

- **Breaking Changes**:
  - None identified; however, increased refresh intervals may impact secret update frequency.

## 2024-10-17 – `b8feddd` by Andrey Bondarenko
- **New Configuration**: Added `argocd/loki.yaml` for ArgoCD deployment of Loki with specified Helm chart settings.
- **Documentation**: Created `loki/loki/README.md` indicating management by ArgoCD.
- **Removed Values**: Deleted `loki/loki/values.yaml`, removing previous configuration settings for Loki.

**Note**: Ensure to update deployment processes as the values file is no longer available.

## 2024-10-17 – `5ba3262` by Andrey Bondarenko
### CHANGELOG for Commit 5ba3262

#### Argocd
- **Updated README.md**: Added `twuni` Helm repository.
- **New registry.yaml**: Introduced configuration for deploying Docker Registry via Argocd.

#### Registry
- **Removed registry-values.yaml**: Configuration file deleted; now managed directly in `registry.yaml`.
- **Updated README.md**: Simplified content to indicate management by Argocd.

#### Breaking Changes
- **Registry Configuration**: Migration from `registry-values.yaml` to `registry.yaml` may require updates to deployment scripts or processes.

## 2024-10-22 – `5556f48` by Andrey Bondarenko
- **New Features**
  - Added `longhorn-crypto-per-volume` StorageClass for encrypted volumes in `longhorn/longhorn-encryption.yaml`.
  - Introduced `vault-secret-store` and `ExternalSecret` configurations in `test.yaml` for external secret management.

- **New Resources**
  - Created PersistentVolumeClaim and Deployment configurations in `test.yaml` for application deployment using Longhorn storage.

- **Secrets Management**
  - Added a `Secret` resource in `test.yaml` for Vault token management.

- **File Additions**
  - New files: `longhorn/longhorn-encryption.yaml`, `test.yaml`.

## 2024-10-22 – `265fd44` by Andrey Bondarenko
- **Removed Configuration**:
  - Deleted `test.yaml`, which included:
    - `SecretStore` and `ExternalSecret` definitions for Vault integration.
    - `PersistentVolumeClaim` for storage allocation.
    - `Deployment` configuration for an application container.
    - `Secret` for Vault token storage.

- **Impact**:
  - All related Kubernetes resources for the `test` namespace are now removed, affecting deployments and secret management.

## 2024-10-23 – `f4b7b3a` by Andrey Bondarenko
- **Configuration Update**
  - Added `ignoreDifferences` section to `argocd/vault.yaml` to exclude changes in `MutatingWebhookConfiguration` webhooks.
  - Updated path: `argocd/vault.yaml`.

## 2024-10-30 – `5c70feb` by Andrey Bondarenko
- **Resource Configuration**
  - Increased memory limit for Prometheus from 3000M to 5000M in `metrics/kubernetes-prometheus/prometheus-deployment.yaml`.

## 2024-10-30 – `f811df1` by Andrey Bondarenko
### CHANGELOG for Commit f811df1

#### ArgoCD Applications
- Added `apiVersion` and `kind` metadata to multiple YAML files for ArgoCD applications:
  - `bitwarden.yaml`
  - `cert-manager.yaml`
  - `clamav.yaml`
  - `collabora.yaml`
  - `conduit.yaml`
  - `elasticsearch.yaml`
  - `external-secrets.yaml`
  - `graphana.yaml`
  - `ingress-nginx.yaml`
  - `loki.yaml`
- Each application now includes:
  - `name` and `namespace` fields under `metadata`
  - `spec` section defining project and source repository

#### Documentation Updates
- Updated `argocd/README.md` to include a note on the Mastodon Helm chart.
- Corrected formatting in `registry/README.md` header.

### Note
- No breaking changes identified.

## 2024-10-31 – `b82aed0` by Andrey Bondarenko
- **Documentation Updates:**
  - Removed Longhorn installation instructions from `README.md`.

- **Docker Cleanup:**
  - Added section for Docker cleanup in `README.md`.

## 2024-11-06 – `273df1a` by Andrey Bondarenko
- **Security Enhancements**
  - Added `securityContext` to Prometheus deployment in `metrics/kubernetes-prometheus/prometheus-deployment.yaml`.
    - Set `runAsUser` and `runAsGroup` to `65534` (nobody).

- **File Updated**
  - `metrics/kubernetes-prometheus/prometheus-deployment.yaml` modified to improve security configurations.

## 2024-11-06 – `023fecd` by Andrey Bondarenko
- **Deployment Changes**
  - Updated `app` label from `mongo-exporter` to `mongodb` in `mongo/mongo-exporter-deployment.yaml`.

- **Service Changes**
  - Changed `app` label from `mongo-exporter` to `mongodb` in `mongo/mongo-exporter-service.yaml`.

- **File Updates**
  - Both deployment and service YAML files reflect consistent naming for the application.

## 2024-11-07 – `04c6f92` by Andrey Bondarenko
- **Thanos Image Update**:
  - Updated Thanos image version from `v0.35.1` to `v0.36.1` in:
    - `thanos/thanos-compactor.yaml`
    - `thanos/thanos-queuer.yaml`
    - `thanos/thanos-storage-gateway.yaml`

- **Prometheus Deployment Update**:
  - Updated Thanos image version from `v0.35.1` to `v0.36.1` in `metrics/kubernetes-prometheus/prometheus-deployment.yaml`.

- **Files Changed**:
  - `metrics/kubernetes-prometheus/prometheus-deployment.yaml`
  - `thanos/thanos-compactor.yaml`
  - `thanos/thanos-queuer.yaml`
  - `thanos/thanos-storage-gateway.yaml`

No breaking changes noted.

## 2024-11-07 – `8ffbeee` by Andrey Bondarenko
- **New Feature**: Added `rancher-k3s-update.yaml` for K3s upgrade plans.
  - **Server Plan**: Configured with concurrency, cordon, and node selector for control-plane nodes.
  - **Agent Plan**: Similar configuration with a prepare step for server plan execution.
- **Versioning**: Both plans specify K3s version `v1.31.2+k3s1`.
- **Service Account**: Utilizes `system-upgrade` service account for upgrade operations.

## 2024-11-07 – `3a69566` by Andrey Bondarenko
- **Storage Configuration Update**
  - Increased MySQL PVC storage request from 10Gi to 25Gi in `mysql/mysql-pvc.yaml`.

## 2024-11-07 – `21c579f` by Andrey Bondarenko
- **Storage Configuration Update**
  - Increased storage request from 50Gi to 100Gi in `metrics/kubernetes-prometheus/prometheus-pvc.yaml`.

## 2024-11-07 – `4f305df` by Andrey Bondarenko
- **Storage Configuration**
  - Updated `clamav/clamav-pvc.yaml`: Increased storage request from **15Gi** to **25Gi**.

## 2024-11-07 – `be50b41` by Andrey Bondarenko
- **Metrics Configuration**
  - Updated storage request in `metrics/kubernetes-prometheus/prometheus-pvc.yaml` from `100Gi` to `107374182400` bytes (100 GiB).

- **File Affected**
  - `metrics/kubernetes-prometheus/prometheus-pvc.yaml`

## 2024-11-07 – `2831082` by Andrey Bondarenko
- **Deployment Changes**:
  - Updated `mongo-exporter-deployment.yaml` to change label from `app: mongodb` to `app: mongo-exporter`.

- **Service Changes**:
  - Modified `mongo-exporter-service.yaml` to update label and selector from `app: mongodb` to `app: mongo-exporter`.

- **Impact**:
  - Ensure all references to the MongoDB exporter use the new label `mongo-exporter` to maintain functionality.

## 2024-11-08 – `27d8dbb` by Andrey Bondarenko
- **Updated Dependency**:
  - Changed MongoDB exporter image from `percona/mongodb_exporter:0.40` to `percona/mongodb_exporter:0.42` in `mongo/mongo-exporter-deployment.yaml`.

- **File Affected**:
  - `mongo/mongo-exporter-deployment.yaml`

## 2024-11-11 – `3c90803` by Andrey Bondarenko
- **Deployment Configuration:**
  - Added `dawarich-deploy.yaml` for Kubernetes deployment configuration, defining two containers: `dawarich` and `dawarich-sidekiq`.
  - Configured environment variables for database and Redis connections, including secrets for passwords.

- **External Secrets Management:**
  - Introduced `dawarich-external-secrets.yaml` to manage external secrets for PostgreSQL and Redis passwords using ExternalSecrets.
  - Set refresh interval to 15 minutes for both secrets.

- **Persistent Volume Claims:**
  - Created `dawarich-pvc.yaml` with four PVCs for `public`, `gem-cache`, `gem-sidekiq`, and `watched`, each requesting 500Mi of storage.

- **Secret Store Definition:**
  - Added `dawarich-secret-store.yaml` for defining the SecretStore for external secrets management (file truncated).

**Note:** Ensure the correct setup of the external secrets backend (e.g., Vault) as this introduces dependencies on external services.

## 2024-11-13 – `ac03ef4` by Andrey Bondarenko
- **Persistent Volume Claims Update**:
  - Increased storage request from **500Mi** to **15Gi** in `dawarich/dawarich-pvc.yaml` for multiple PVC definitions.

- **File Affected**:
  - `dawarich/dawarich-pvc.yaml` - All instances of storage requests updated.

## 2024-11-13 – `720d714` by Andrey Bondarenko
- **New Service Configuration**:
  - Added `dawarich-service.yaml` to define a new Kubernetes Service for the `dawarich` application.
  - Service exposes TCP port 3000, targeting the same port on the application.
  - Configured under the `dawarich` namespace with appropriate labels and selectors.

## 2024-11-13 – `958a9a0` by Andrey Bondarenko
- **Ingress Configuration**
  - Added `dawarich-ingress.yaml` for Kubernetes Ingress resource.
  - Configured NGINX ingress with SSL redirection and rewrite rules.
  - Set up TLS with Let's Encrypt for `dawarich.andreybondarenko.com`.
  - Defined backend service routing to `dawarich` on port 3000.

## 2024-11-15 – `9f19560` by Andrey Bondarenko
- **Deployment Configuration (dawarich-deploy.yaml)**:
  - Updated `APPLICATION_HOSTS` to include `"dawarich.andreybondarenko.com, localhost"`.
  - Increased `RAILS_MIN_THREADS` from `1` to `5` and `RAILS_MAX_THREADS` from `1` to `10`.
  - Adjusted `BACKGROUND_PROCESSING_CONCURRENCY` from `2` to `10`.

- **Resource Management**:
  - Added resource requests for memory (`1Gi`) and CPU (`250m`) for both application and Sidekiq containers.
  - Increased memory limit for application from `3Gi` to `3.5Gi` and CPU limit from `1500m` to `2000m`.

- **Image Update**:
  - Updated Docker image from `freikin/dawarich:0.16.3` to `freikin/dawarich:0.16.4`.

**Note**: Ensure compatibility with new resource settings and application host configurations.

## 2024-11-15 – `46764be` by Andrey Bondarenko
- **Secret Store Configuration**
  - Added `vault-secret-store-registry` in `dawarich-secret-store.yaml` for external secrets management.

- **Photon Deployment**
  - Introduced `photon-deployment.yaml` for deploying the Photon application with a single replica.
  - Configured container to use image `registry.andreybondarenko.com/photon:latest` and mounted persistent volume.

- **Persistent Storage**
  - Created `photon-pvc.yaml` for a PersistentVolumeClaim named `photon-data`, requesting 200Gi of storage.

- **Service Exposure**
  - Added `photon-service.yaml` to expose the Photon application on TCP port 2322.

- **Registry Secret Management**
  - Implemented `registry-secret.yaml` to manage Docker registry credentials via an ExternalSecret linked to the new SecretStore.

## 2024-11-21 – `9d83ad6` by Andrey Bondarenko
### CHANGELOG for Commit 9d83ad6

#### Deployment Configuration Updates
- **Updated `dawarich-deploy.yaml`:**
  - Changed `PHOTON_API_HOST` from `photon.komoot.io` to `photon.dawarich.svc.cluster.local`.
  - Set `PHOTON_API_USE_HTTPS` to `false`.
  - Updated Docker image version from `freikin/dawarich:0.16.4` to `freikin/dawarich:0.16.8`.
  - Adjusted `RAILS_MIN_THREADS` and `RAILS_MAX_THREADS` from `5` and `10` to `1` each.
  - Increased memory limit from `3Gi` to `4Gi`.

#### Service Configuration Changes
- **Modified `photon-service.yaml`:**
  - Changed service port from `2322` to `80`.

#### Breaking Changes
- **Service Port Change:** The photon service is now exposed on port `80`, which may affect existing client configurations.

## 2024-11-28 – `fc7ffe8` by Andrey Bondarenko
- **Dependency Updates**
  - Updated Redis Helm chart version in `argocd/redis.yaml` from `19.1.3` to `20.3.0`.

- **Deployment Configuration**
  - Added deployment strategy `Recreate` in `dawarich/dawarich-deploy.yaml`.

- **Environment Variables**
  - Modified `REDIS_URL` in `dawarich/dawarich-deploy.yaml` to remove the password placeholder for the main and sidekiq containers.
  - Updated `REDIS_URL` for sidekiq to include password placeholder.

- **Image Versioning**
  - Changed Docker image tag from `0.16.8` to `latest` in `dawarich/dawarich-deploy.yaml` for both main and sidekiq containers.

**Note:** Ensure compatibility with Redis version `20.3.0` and validate the impact of using `latest` image tag.

## 2024-12-06 – `7cea544` by Andrey Bondarenko
- **Documentation Updates**
  - Updated README files for `clamav`, `collabora`, `loki`, and `mastodon` to reflect recent changes and improvements.

- **Deployment Configurations**
  - Modified `dawarich-deploy.yaml` and `photon-deployment.yaml` for enhanced deployment strategies.
  - Updated `rancher-k3s-update.yaml` to streamline k3s update processes.

- **YAML Linting**
  - Adjusted `.yamllint` configuration for improved YAML validation.

- **Metrics Templates**
  - Added new metrics template: `Cluster load-1702377122035.json` in `metrics/graphana/termplates`.

- **Script Updates**
  - Revised `secrets.sh` for better security practices and management.

## 2024-12-06 – `eab881d` by Andrey Bondarenko
- **Ingress NGINX Configuration**
  - Enabled metrics collection by adding `controller.metrics.enabled: 'true'` in `argocd/ingress-nginx.yaml`.

- **Prometheus Configuration**
  - Added new scrape job for Ingress NGINX metrics in `metrics/kubernetes-prometheus/config-map.yaml`:
    - Job name: `ingress-nginx`
    - Scrape interval: 45s
    - Scrape timeout: 30s
    - Target: `nginx-ingress-ingress-nginx-controller-metrics.ingress-nginx.svc.cluster.local:10254`

## 2024-12-06 – `7c0bc2a` by Andrey Bondarenko
- **Deployment Updates:**
  - Added `strategy: type: Recreate` to all Thanos and Prometheus deployment configurations.

- **Image Version Upgrade:**
  - Updated Thanos image from `v0.36.1` to `v0.37.1` in:
    - `thanos/thanos-compactor.yaml`
    - `thanos/thanos-queuer.yaml`
    - `thanos/thanos-storage-gateway.yaml`
    - `metrics/kubernetes-prometheus/prometheus-deployment.yaml`

- **Files Modified:**
  - `metrics/kubernetes-prometheus/prometheus-deployment.yaml`
  - `thanos/thanos-compactor.yaml`
  - `thanos/thanos-queuer.yaml`
  - `thanos/thanos-storage-gateway.yaml`

## 2024-12-06 – `d21c09c` by Andrey Bondarenko
- **ArgoCD Application Definitions**:
  - Added `apiVersion`, `kind`, `metadata`, and `spec` sections to 22 YAML files for ArgoCD applications.
  - Updated applications include: `kube-state-metrics`, `kubernetes-node-exporter`, `kubernetes-prometheus`, `mail`, `minecraft`, `minio`, `mongo`, `mysql`, `nextcloud`, `nfs-provisioner`, `plex`, `postgres-exporter`, `postgres`, `promtail`, `rancher`, `redis-exporter`, `redis`, `registry`, `thanos`, `vault`, `wordpress`, `your-spotify`.

- **File Changes**:
  - All modified files are located in the `argocd/` directory, reflecting the new application structure.

- **Breaking Changes**:
  - The introduction of the `kind: Application` and associated metadata may require updates to deployment processes or CI/CD pipelines that interact with these configurations.

## 2024-12-06 – `32023d4` by Andrey Bondarenko
- **Deployment Configuration Updates**
  - Updated `REDIS_URL` in `dawarich-deploy.yaml` to use `valueFrom` with `secretKeyRef` for `redis-uri`.
  - Adjusted `REDIS_URL` in multiple deployment specs to reference the new secret.

- **External Secrets Configuration**
  - Added new `ExternalSecret` resource in `dawarich-external-secrets.yaml` for `redis-uri`.
  - Configured `ExternalSecret` to pull `redis-uri` from `vault-secret-store-redis` with a refresh interval of 15 minutes.

- **Breaking Changes**
  - `REDIS_URL` now requires the `redis-uri` secret to be defined in the Kubernetes cluster.

## 2024-12-11 – `1ad2abc` by Andrey Bondarenko
- **Docker Image Update**
  - Changed Docker image from `freikin/dawarich:latest` to `freikin/dawarich:0.19.5` in `dawarich/dawarich-deploy.yaml`.

- **Deployment Configuration**
  - Updated image reference in multiple locations within the deployment spec.

## 2024-12-11 – `2528c80` by Andrey Bondarenko
- **Deployment Update**
  - Updated Docker image version from `0.19.5` to `0.19.6` in `dawarich/dawarich-deploy.yaml` for both application and Sidekiq configurations.
  - Ensured `imagePullPolicy` remains set to `Always`.

## 2024-12-13 – `971bc0a` by Andrey Bondarenko
- **Deployment Configuration Updates**
  - Added node affinity and pod anti-affinity rules to `dawarich/photon-deployment.yaml` to prevent scheduling on specific nodes and avoid co-locating with `php-nextcloud` and `nginx-nextcloud`.
  - Updated `nextcloud/nginx-deployment.yaml`:
    - Reduced replicas from 3 to 1.
    - Added node affinity and pod anti-affinity rules similar to photon deployment.
  - Updated `nextcloud/php-deployment.yaml`:
    - Reduced replicas from 3 to 2.
    - Added node affinity and pod anti-affinity rules similar to photon deployment.

- **Important Files Modified**
  - `dawarich/photon-deployment.yaml`
  - `nextcloud/nginx-deployment.yaml`
  - `nextcloud/php-deployment.yaml`

- **Breaking Changes**
  - Reduced replicas for `nginx` and `php` deployments may affect availability and load handling.

## 2024-12-13 – `e4cdebd` by Andrey Bondarenko
- **Configuration Update**
  - Reduced `storage` request from `200Gi` to `15Gi` in `thanos/thanos-compactor-pvc.yaml`.

## 2024-12-17 – `2aa9e44` by Andrey Bondarenko
- **Documentation Update**:
  - Corrected namespace in `README.md` for retrieving TLS certificates from `wordpress` instead of `mail`.

- **File Affected**:
  - `README.md`

## 2024-12-17 – `4b9b3dd` by Andrey Bondarenko
- **Resource Configuration Update**:
  - Increased CPU request from `10m` to `500m` in `clamav/clamav-deployment.yaml`.
  - Raised CPU limit from `2000m` to `4000m` in `clamav/clamav-deployment.yaml`.

- **File Affected**:
  - `clamav/clamav-deployment.yaml`

## 2024-12-17 – `b6c5de7` by Andrey Bondarenko
- **Deployment Configuration Updates**
  - Updated Docker image from `freikin/dawarich:0.19.6` to `freikin/dawarich:latest` in `dawarich/dawarich-deploy.yaml`.
  - Ensured `imagePullPolicy` is set to `Always` for both instances of the image.

**Note:** This change may introduce breaking changes if the latest image contains incompatible updates.

## 2024-12-17 – `84858d2` by Andrey Bondarenko
- **Retention Policy Updates**:
  - Changed `--retention.resolution-raw` from `31d` to `14d`.
  - Changed `--retention.resolution-5m` from `90d` to `30d`.
  - Changed `--retention.resolution-1h` from `365d` to `10950d` (approximately 30 years).

- **File Modified**:
  - `thanos/thanos-compactor.yaml` updated with new retention settings.

## 2024-12-28 – `b18c05c` by Andrey Bondarenko
- **Configuration Update**:
  - Added `--delete-delay=24h` to the Thanos Compactor configuration in `thanos/thanos-compactor.yaml`.

## 2024-12-30 – `73e37a9` by Andrey Bondarenko
- **Storage Configuration**
  - Increased `storage` request from `15Gi` to `150Gi` in `thanos/thanos-compactor-pvc.yaml`.

## 2025-01-01 – `4fc6a42` by Andrey Bondarenko
- **Configuration Update**
  - Reduced `storage` request from `150Gi` to `50Gi` in `thanos/thanos-compactor-pvc.yaml`.

## 2025-01-01 – `d8f2aa6` by Andrey Bondarenko
- **Configuration Update**
  - Increased storage request from 200Gi to 220Gi in `nextcloud/php-pvc.yaml`.

## 2025-01-01 – `4b556b1` by Andrey Bondarenko
- **Configuration Update**
  - Increased storage request in `nextcloud/php-pvc.yaml` from `220Gi` to `236223201280` bytes (approximately 220Gi).

## 2025-01-02 – `4624c25` by Andrey Bondarenko
- **Configuration Update**
  - Increased storage request from 50Gi to 125Gi in `thanos/thanos-compactor-pvc.yaml`.

## 2025-01-10 – `7d4192c` by Andrey Bondarenko
- **Documentation Update**:
  - Removed instructions for bringing back disks in `mastodon/README.md`.

- **File Affected**:
  - `mastodon/README.md` - Significant reduction in content related to PVC annotations and labels.

## 2025-01-10 – `8cc60a0` by Andrey Bondarenko
- **Configuration Update**: Modified `mastodon/mastodon-values.yaml` for improved settings.
- **File Change**: Only `mastodon/mastodon-values.yaml` was altered in this commit.

## 2025-01-10 – `8733722` by Andrey Bondarenko
- **Nginx Configuration Updates:**
  - Increased `client_max_body_size` from 2000M to 10000M in `nginx-configMap.yaml`.
  - Updated `nginx.ingress.kubernetes.io/proxy-body-size` from 1000m to 10000m in `nginx-ingress.yaml`.

- **PHP Configuration Changes:**
  - Raised `upload_max_filesize` from 2048M to 8048M in `php-configmap.yaml`.

**Note:** These changes significantly increase file upload limits across the application.

## 2025-01-11 – `2cc73d8` by Andrey Bondarenko
- **Deployment Configuration Updates (dawarich-deploy.yaml)**:
  - Replaced `dev-entrypoint.sh` with `web-entrypoint.sh` for web service.
  - Updated Sidekiq command to use `sidekiq-entrypoint.sh` and `bundle exec sidekiq`.
  - Removed volume mounts for `gem-cache` and `gem-sidekiq`.
  - Removed associated persistent volume claims for `gem-cache` and `gem-sidekiq`.

- **Resource Management**:
  - Retained resource requests for memory and CPU for web and Sidekiq services.

## 2025-01-12 – `d895dc8` by Andrey Bondarenko
- **Enhancements to NGINX Deployment**
  - Added `livenessProbe` and `readinessProbe` configurations to `wordpress/nginx-deployment.yaml` for improved health checks.
  - Probes configured to check HTTP path `/` on port `80` with specified delays and thresholds.

## 2025-01-12 – `f0c35e4` by Andrey Bondarenko
- **Deployment Configuration**
  - Updated liveness probe path in `wordpress/nginx-deployment.yaml` from `/` to `/wp-json/wp-site-health/v1`.

## 2025-01-12 – `59d2883` by Andrey Bondarenko
- **Health Checks**:
  - Added `livenessProbe` and `readinessProbe` configurations to `dawarich/dawarich-deploy.yaml`.
  - Liveness probe checks `/api/v1/health` on port 3000.
  - Readiness probe checks `/` on port 3000.

- **Configuration Parameters**:
  - Set `initialDelaySeconds`, `periodSeconds`, `timeoutSeconds`, and `failureThreshold` for both probes.

## 2025-01-13 – `6ca1503` by Andrey Bondarenko
- **Added Monitoring Job:**
  - Introduced new job configuration for `trivy` in `metrics/kubernetes-prometheus/config-map.yaml`.
  - Set `scrape_interval` to 60s and `scrape_timeout` to 30s.
  - Target set to `trivy-operator.trivy-system.svc.cluster.local:8080`.

## 2025-01-14 – `78b6540` by Andrey Bondarenko
- **MongoDB Deployment Update**
  - Updated MongoDB image from `mongo:4.4.0` to `mongo:latest` in `mongo/mongo-deployment.yaml`.
  - Ensure compatibility with the latest MongoDB features and security updates.

## 2025-01-15 – `c939fe3` by Andrey Bondarenko
- **New Configuration**: Added `argocd/trivy.yaml` for Thanos application deployment.
- **Helm Parameters**: Configured service monitor and resource limits for Trivy.
- **Source Repository**: Points to `https://github.com/aquasecurity/trivy-operator` for Helm chart.
- **Deployment Namespace**: Targets `trivy-system` in Kubernetes.

## 2025-01-15 – `51cba83` by Andrey Bondarenko
- **Plex Deployment Updates:**
  - Changed deployment strategy to `Recreate` in `plex/plex-deployment.yaml`.
  - Updated Plex image from `greensheep/plex-server-docker-rpi:latest` to `linuxserver/plex:latest`.

- **Trivy Configuration:**
  - Added new ConfigMap `trivy/trivy-configmap.yaml` for managing private registry scan secrets.

## 2025-01-22 – `6f6934e` by Andrey Bondarenko
- **Dependency Update**
  - Updated Longhorn chart version from `v1.7.1` to `v1.8.0` in `argocd/longhorn.yaml`.

- **File Affected**
  - `argocd/longhorn.yaml`

## 2025-01-24 – `d2f39a3` by Andrey Bondarenko
- **Resource Limits Update**:
  - Increased CPU limit for Trivy from `1500m` to `5500m`.
  - Updated Trivy server CPU limit from `2` to `3`.
  - Set memory limit for Trivy to `2500M` and for Trivy server to `3Gi`.

- **New Configuration Parameters**:
  - Added `operator.scanJobTimeout` set to `125m`.
  - Introduced `trivy.timeout` with a value of `125m`.
  - Added `operator.valuesFromConfigMap` pointing to `trivy-system`.
  - Set `operator.scanJobsConcurrentLimit` to `5`.

- **File Affected**:
  - Modified `argocd/trivy.yaml`.

## 2025-01-26 – `d8698cc` by Andrey Bondarenko
- **Configuration Update**
  - Added `operator.scannerReportTTL` with value `128h` to `argocd/trivy.yaml`.

## 2025-03-01 – `8de41ad` by Andrey Bondarenko
- **Deployment Changes:**
  - Renamed volume mounts in `plex/plex-deployment.yaml`:
    - `plex-conf-lh` → `plex-conf-lh2`
  - Updated `persistentVolumeClaim` references accordingly.

- **PVC Configuration Updates:**
  - Swapped names in `plex/plex-pvc.yaml`:
    - `plex-conf-lh` → `plex-lib-lh`
    - `plex-lib-lh` → `plex-conf-lh2`
  - Changed access modes and storage class:
    - `plex-conf-lh2`: `ReadWriteMany` → `ReadWriteOnce`, `nfs-client` → `longhorn`
    - `plex-lib-lh`: `ReadWriteOnce` → `ReadWriteMany`, `longhorn` → `nfs-client`
  - Adjusted storage request for `plex-conf-lh2` from `100Gi` to `25Gi`.

- **Breaking Change:**
  - Volume names and access modes have been modified, requiring updates to dependent configurations.

## 2025-03-01 – `fa8e360` by Andrey Bondarenko
- **Configuration Update**
  - Changed `externalIPs` for `longhorn-ui` from `192.168.1.105` to `192.168.1.104` in `services/longhorn-system.yaml`.

## 2025-03-07 – `1741637` by Andrey Bondarenko
- **Configuration Update**
  - Increased `server.replicaCount` from `1` to `5` in `argocd/vault.yaml`.

## 2025-03-07 – `5a5e506` by Andrey Bondarenko
- **Storage Configuration Update**
  - Changed `storage` request from `2Gi` to `3221225472` in `conduit/matrix-pvc.yaml`.
- **File Affected**
  - `conduit/matrix-pvc.yaml`

## 2025-03-08 – `34861fd` by Andrey Bondarenko
- **Dependency Update**
  - Updated Longhorn chart version from `v1.8.0` to `v1.8.1` in `argocd/longhorn.yaml`.

## 2025-03-10 – `5674843` by Andrey Bondarenko
- **Configuration Changes**:
  - Replaced `VAPID_PUBLIC_KEY` with `ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY` in `mastodon/mastodon-secrets.yaml`.
  - Added new secret keys:
    - `ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT`
    - `ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY`
  - Updated remote references for new keys to `PRIMARY_KEY` and `KEY_DERIVATION_SALT`.

- **File Affected**:
  - `mastodon/mastodon-secrets.yaml` - significant changes to encryption key management.

## 2025-03-12 – `3915021` by Andrey Bondarenko
- **Configuration Update**
  - Updated `mastodon.streaming.image.repository` to `ghcr.io/mastodon/mastodon-streaming`.
  - Set `mastodon.streaming.image.tag` to `latest`.

- **File Affected**
  - Modified `mastodon/mastodon-values.yaml`.

## 2025-03-13 – `7935c40` by Andrey Bondarenko
- **Dependency Update**
  - Updated `targetRevision` in `argocd/elasticsearch.yaml` from `21.3.17` to `21.4.8`.

## 2025-03-13 – `81c3e9d` by Andrey Bondarenko
- **File Management**
  - Added `.gitignore` in `mastodon/` to ignore `chart` directory.

## 2025-03-13 – `c29e32b` by Andrey Bondarenko
- **Dependency Updates:**
  - Updated `cert-manager` to version **v1.17.1** in `argocd/cert-manager.yaml`.
  - Updated `collabora` to version **1.1.36** in `argocd/collabora.yaml`.
  - Updated `external-secrets` to version **0.14.4** in `argocd/external-secrets.yaml`.
  - Updated `loki` to version **6.28.0** in `argocd/loki.yaml`.

- **Files Modified:**
  - `argocd/cert-manager.yaml`
  - `argocd/collabora.yaml`
  - `argocd/external-secrets.yaml`
  - `argocd/loki.yaml`

No breaking changes identified.

## 2025-03-19 – `abf3926` by Andrey Bondarenko
- **Alert Configuration**:
  - Added new alert for "PVC is full!" in `metrics/kubernetes-prometheus/config-map.yaml`.
  - Trigger condition: `longhorn_volume_actual_size_bytes/longhorn_volume_capacity_bytes > 0.85` for 1 minute.
  - Severity level set to "mail" with appropriate summary annotations.

## 2025-03-19 – `c929e79` by Andrey Bondarenko
- **Resource Configuration Update**
  - Increased CPU limit from `300m` to `1000m` in `your-spotify/web-deployment.yaml`.

## 2025-03-20 – `d8e2e58` by Andrey Bondarenko
- **Storage Configuration Update**
  - Increased storage request from `100Gi` to `150Gi` in `metrics/kubernetes-prometheus/prometheus-pvc.yaml`.

## 2025-03-20 – `fe6dda3` by Andrey Bondarenko
- **Metrics Configuration Update**
  - Increased storage request in `metrics/kubernetes-prometheus/prometheus-pvc.yaml` from 160Gi to 170Gi.

## 2025-03-20 – `ba92ffd` by Andrey Bondarenko
- **Enhancements to ArgoCD Configuration**
  - Added `ignoreDifferences` section in `argocd/registry.yaml` to exclude `haSharedSecret` from comparison for `registry-docker-registry-secret`.

## 2025-03-20 – `aa0a037` by Andrey Bondarenko
- **Deployment Configuration Changes**:
  - Updated `CONDUIT_ALLOW_REGISTRATION` to `"true"` in `conduit/conduit-deployment.yaml`.
  - Changed `readOnlyRootFilesystem` to `false` in the security context.

**Breaking Change**: Enabling registration may affect user access and security configurations.

## 2025-03-20 – `14fc993` by Andrey Bondarenko
- **Kubernetes Deployment Update**
  - Removed `securityContext` settings from `conduit/conduit-deployment.yaml`:
    - `allowPrivilegeEscalation: false`
    - `readOnlyRootFilesystem: false`
- **Impact**: Potential security implications due to removal of privilege escalation restrictions.

## 2025-03-21 – `1b9dd52` by Andrey Bondarenko
- **Deployment Updates:**
  - Added `securityContext` to `prometheus-deployment.yaml` to run as user/group `65534`.
  - Updated Thanos image from `v0.37.1` to `v0.37.2`.
  - Introduced `initContainers` to set ownership of `/prometheus` directory.

- **Persistent Volume Changes:**
  - Changed storage request in `prometheus-pvc.yaml` from `182536110080` to `50Gi`.

- **Files Modified:**
  - `metrics/kubernetes-prometheus/prometheus-deployment.yaml`
  - `metrics/kubernetes-prometheus/prometheus-pvc.yaml`

- **Breaking Change:**
  - Storage size reduction may impact existing data retention.

## 2025-03-21 – `e46a575` by Andrey Bondarenko
- **Configuration Update**
  - Added `preset: small_node_cluster` to `elasticsearch` settings in `mastodon/mastodon-values.yaml`.

## 2025-03-21 – `184de36` by Andrey Bondarenko
- **Resource Allocation Update**:
  - Increased memory request from **1Gi** to **2Gi** in `dawarich/dawarich-deploy.yaml`.
  - Increased memory limit from **3.5Gi** to **7Gi** in `dawarich/dawarich-deploy.yaml`.

## 2025-03-21 – `4e99455` by Andrey Bondarenko
- **Configuration Changes**
  - Removed `CONDUIT_LOG` environment variable from `conduit/conduit-deployment.yaml`.

- **File Affected**
  - `conduit/conduit-deployment.yaml` updated to streamline logging configuration.

## 2025-03-21 – `4bc0451` by Andrey Bondarenko
- **Configuration Update**
  - Modified `argocd/registry.yaml` to enhance `ignoreDifferences` for `registry-docker-registry-secret`.
  - Added `namespace` and `jsonPointers` fields for better specificity in secret handling.

## 2025-03-24 – `7fb9447` by Andrey Bondarenko
- **Ingress Configuration:**
  - Updated host from `matrix.andreybondarenko.com` to `shaman007.com` in `conduit/matrix-ingress.yaml`.

- **Persistent Volume Claim:**
  - Renamed PVC from `matrix1-lh` to `matrix-lh` in `conduit/matrix-pvc.yaml`.
  - Increased storage request from `3Gi` to `30Gi`.

- **Service Configuration:**
  - Changed service type to `LoadBalancer` in `conduit/matrix-service.yaml`.
  - Updated port configuration: changed service port to `8448` and added `externalIPs`.

- **Nginx Configuration:**
  - Updated server name and well-known paths to reflect new domain `shaman007.com` in `conduit/nginx-configMap.yaml`.
  - Added proxy settings for `/sync` paths to improve handling of requests.

**Breaking Change:** The domain change may affect existing clients and integrations relying on the previous domain.

## 2025-03-24 – `78b00bb` by Andrey Bondarenko
- **Kubernetes Deployment Update**
  - Added node affinity to `plex/plex-deployment.yaml` to prevent scheduling on node `w4.k8s.my.lan`.

## 2025-03-24 – `c32e521` by Andrey Bondarenko
- **Removed Configurations:**
  - Deleted `conduit/conduit-configmap.yaml` and `conduit/conduit-deployment.yaml` files.

- **New Tools Added:**
  - Introduced new SQL script: `conduit/tools/CREATE DATABASE synapse.sql`.
  - Added Python scripts for various operations:
    - `conduit/tools/check.py`: Fetches device information from a homeserver.
    - `conduit/tools/dehydrated.py`: Handles device key management for a dehydrated device.
    - `conduit/tools/rehydrate.py`: Rehydrates a device using a dehydrated device ID.
    - `conduit/tools/reset.py`: Deletes specific account data from a user account.

- **Important Notes:**
  - Ensure to configure `HOMESERVER` and `ACCESS_TOKEN` in the new Python scripts for proper functionality.

## 2025-03-26 – `854ac4e` by Andrey Bondarenko
- **Deployment Configuration**:
  - Removed volume mount for `/var/log/bitwarden` in `bitwarden/bitwarden-deployment.yaml`.
  - Deleted associated volume definition for `logs-lh`.

**Breaking Change**: Logging volume is no longer available; ensure logging is handled externally.

## 2025-03-26 – `79f0bb3` by Andrey Bondarenko
- **Resource Adjustments:**
  - Increased memory requests for ClamAV from 100Mi to 1500Mi and 100Mi to 1000Mi in `clamav/clamav-deployment.yaml`.
  - Updated memory requests for Prometheus from 300M to 2000M in `metrics/kubernetes-prometheus/prometheus-deployment.yaml`.
  - Raised memory requests for MinIO from 300Mi to 1300Mi in `minio-single/minio-single-deployment.yaml`.
  - Enhanced memory request for Plex from 100Mi to 1500Mi in `plex/plex-deployment.yaml`.

- **Deployment Files Modified:**
  - `clamav/clamav-deployment.yaml`
  - `metrics/kubernetes-prometheus/prometheus-deployment.yaml`
  - `minio-single/minio-single-deployment.yaml`
  - `plex/plex-deployment.yaml`

No breaking changes noted.

## 2025-03-26 – `7588e77` by Andrey Bondarenko
- **New Feature**: Added `synapse-deployment.yaml` for deploying Matrix Synapse.
- **Deployment Configuration**:
  - Configures a single replica deployment in the `matrix` namespace.
  - Uses `docker.io/matrixdotorg/synapse:latest` image.
  - Sets resource requests and limits for CPU and memory.
- **Volume Management**:
  - Defines persistent volume claims for data storage and configuration.
  - Includes an init container to fix permissions on the data directory.
- **Environment Variables**: Sets `SYNAPSE_CONFIG_PATH` for Synapse configuration.

## 2025-03-26 – `3b1921d` by Andrey Bondarenko
- **Resource Allocation Changes**:
  - Updated memory request from **2Gi** to **3.5Gi** in `dawarich/dawarich-deploy.yaml`.
  - Adjusted memory limit from **7Gi** to **4Gi** in `dawarich/dawarich-deploy.yaml`.

- **File Affected**:
  - `dawarich/dawarich-deploy.yaml`

## 2025-03-26 – `767ad67` by Andrey Bondarenko
- **Alert Expression Updates**:
  - Modified `KubePersistentVolumeFillingUp` alert expressions for improved clarity and performance.
  - Changed threshold from 3% to 15% for available bytes in persistent volumes.

- **File Affected**:
  - `metrics/kubernetes-prometheus/config-map.yaml` updated with new alert conditions.

## 2025-03-26 – `32906bc` by Andrey Bondarenko
- **ClamAV Deployment**:
  - Increased memory request from `1000Mi` to `1500Mi` in `clamav/clamav-deployment.yaml`.

- **Photon Deployment**:
  - Added resource requests and limits for memory (`1500Mi`, `1600Mi`) and CPU (`250m`, `2`) in `dawarich/photon-deployment.yaml`.

- **MySQL Deployment**:
  - Adjusted memory request from `1000Mi` to `1600Mi` and reduced memory limit from `3200Mi` to `1600Mi` in `mysql/mysql-deployment.yaml`.

- **Redis Configuration**:
  - Reduced memory limits for master from `2000Mi` to `100Mi` and for replica from `1000Mi` to `300Mi` in `redis/redis-values.yaml`.

## 2025-03-27 – `c568ac2` by Andrey Bondarenko
### CHANGELOG for Commit c568ac2

#### Resource Adjustments
- **dawarich-deploy.yaml**: Reduced memory requests from 3.5Gi to 1.5Gi and limits from 4Gi to 2Gi.
- **dovecot-deployment.yaml**: Memory limits decreased from 521Mi to 296Mi.
- **postfix-deployment.yaml**: Memory limits reduced from 256Mi to 128Mi.
- **graphana.yaml**: Memory requests adjusted from 210Mi to 200Mi; limits reduced from 400Mi to 200Mi.
- **prometheus-deployment.yaml**: Increased memory requests from 300M to 3000M; limits adjusted from 3000M to 3500M.
- **minecraft-deployment.yaml**: Memory requests reduced from 812Mi to 1512Mi; limits decreased from 1812Mi to 1512Mi.
- **minio-single-deployment.yaml**: Memory requests increased from 1300Mi to 1500Mi; limits reduced from 4000Mi to 2000Mi.
- **mongo-deployment.yaml**: Memory requests decreased from 300Mi to 200Mi; limits reduced from 600Mi to 200Mi.

#### Files Affected
- Multiple deployment configurations in `dawarich`, `mail`, `metrics`, `minecraft`, `minio-single`, and `mongo` directories.

#### Notes
- Ensure to validate resource allocations post-deployment due to significant changes in memory limits and requests across multiple services.

## 2025-03-29 – `d3f5cb1` by Andrey Bondarenko
- **Bitwarden**:
  - Removed `bitwarden-logs-pvc.yaml` file (PersistentVolumeClaim for logs).

- **Dawarich**:
  - Changed deployment strategy from `Recreate` to `RollingUpdate` in `dawarich-deploy.yaml`.
  - Configured `RollingUpdate` parameters: `maxUnavailable: 1`, `maxSurge: 0`.
  - Increased memory request from `1.5Gi` to `2Gi` in deployment spec.

## 2025-04-04 – `a30e32f` by Andrey Bondarenko
- **Deployment Updates**:
  - Added new volume mount for `/var/app/storage` in `dawarich-deploy.yaml` for both web and sidekiq containers.

- **Persistent Volume Claim**:
  - Introduced `storage` PVC in `dawarich-pvc.yaml` with `15Gi` storage request and `longhorn` storage class.

- **File Changes**:
  - `dawarich/dawarich-deploy.yaml`: Updated to include new storage mount.
  - `dawarich/dawarich-pvc.yaml`: New PVC definition added.

## 2025-04-08 – `f3e402b` by Andrey Bondarenko
- **Persistent Volume Claims:**
  - Added `keys-lh` PVC for data protection keys in `bitwarden/bitwarden-data-pvc.yaml`.

- **Deployment Configuration:**
  - Updated `bitwarden/bitwarden-deployment.yaml`:
    - Added environment variable `DOTNET_DataProtection__PersistKeysToFileSystem`.
    - Mounted `keys-lh` PVC to `/app/Notifications/.aspnet`.
    - Configured `promtail` container with resource limits and volume mounts for logs.

- **Promtail Configuration:**
  - Introduced new `promtail.yaml` ConfigMap in `bitwarden/promtail.yaml` for log scraping configuration targeting Bitwarden logs.

**Note:** Ensure to review the addition of the new PVC and its impact on existing deployments.

## 2025-04-10 – `72d6385` by Andrey Bondarenko
- **Environment Configuration**
  - Added `SELF_HOSTED` environment variable with value `true` in `dawarich/dawarich-deploy.yaml` for both deployment and development environments.

## 2025-04-12 – `3f9beaa` by Andrey Bondarenko
- **Image Source Update**
  - Changed image repository from `registry.andreybondarenko.com` to `harbor.andreybondarenko.com/library` for multiple services:
    - Camera: `lighttpd`, `vsftpd`
    - ClamAV: `clamav`
    - Cron jobs: `minecraft-cli`, `mysql-cli`, `nextcloud`, `postgres-cli`, `redis-cli`
    - Dawarich: `photon`
    - Mail: `dovecot`, `postfix`

- **Dovecot Configuration Changes**
  - Updated log paths in `dovecot-configMap.yaml` from `/var/lib/dovecot/mail.log` to `/var/log/maillog`.
  - Changed `readOnlyRootFilesystem` to `false` in `dovecot-deployment.yaml`.

- **New Harbor Configuration**
  - Added `harbor/values.yaml` for Harbor deployment configuration, including node selectors and ingress settings.

- **Breaking Change**
  - Image repository change may require updates to deployment configurations and CI/CD pipelines to reflect the new image source.

## 2025-04-12 – `bc03a16` by Andrey Bondarenko
- **Container Image Update**
  - Changed NGINX image from `nginx` to `harbor.andreybondarenko.com/dockerhub/nginx:latest` in `wordpress/nginx-deployment.yaml`.

- **Security Context**
  - No changes made to the security context settings for the NGINX container.

## 2025-04-12 – `b2dfa0c` by Andrey Bondarenko
- **Metrics Configuration Updates**:
  - Removed job configurations for `registry` and `trivy` from `metrics/kubernetes-prometheus/config-map.yaml`.
  - Retained existing configurations for `redis` and `unifi`.

- **File Affected**:
  - `metrics/kubernetes-prometheus/config-map.yaml`

## 2025-04-12 – `c5695cb` by Andrey Bondarenko
- **Kubernetes Configuration**
  - Added `imagePullSecrets` to `wordpress/nginx-deployment.yaml` for private registry access.
  - Configured with secret name `my-private-registry`.

No breaking changes noted.

## 2025-04-12 – `b8096fa` by Andrey Bondarenko
- **Container Image Update**
  - Changed Nginx image to `harbor.andreybondarenko.com/dockerhub/nginx:latest` in `nextcloud/nginx-deployment.yaml`.

- **Image Pull Secrets**
  - Added `imagePullSecrets` configuration for private registry access in `nextcloud/nginx-deployment.yaml`.

- **Security Context**
  - Maintained security context settings for the Nginx container.

## 2025-04-12 – `139c439` by Andrey Bondarenko
- **Deployment Configuration Updates**
  - Changed Docker image reference in `dawarich-deploy.yaml` to `harbor.andreybondarenko.com/dockerhub/freikin/dawarich:latest` from `freikin/dawarich:latest`.
  - Added `imagePullSecrets` configuration for private registry access in `dawarich-deploy.yaml`.

- **External Secrets Configuration**
  - Introduced new `ExternalSecret` resource in `dawarich-external-secrets.yaml` for managing Docker registry credentials.
  - Configured secret store reference to `vault-secret-store-registry` for accessing registry credentials.

## 2025-04-12 – `acd41d4` by Andrey Bondarenko
- **Deployment Updates**
  - Updated Bitwarden deployment image to `harbor.andreybondarenko.com/dockerhub/bitwarden/self-host:beta`.
  - Updated Promtail image to `harbor.andreybondarenko.com/dockerhub/grafana/promtail:latest`.

- **New Configuration**
  - Added `bitwarden/registry-secret.yaml` for managing private registry credentials via External Secrets.

## 2025-04-12 – `ca0c9c6` by Andrey Bondarenko
- **Bitwarden Deployment Updates**
  - Added `imagePullSecrets` for private registry in `bitwarden-deployment.yaml`.

- **Registry Secret Configuration**
  - Reduced `refreshInterval` from "15m" to "1m" in `registry-secret.yaml`.
  - Introduced `SecretStore` configuration for Vault integration in `registry-secret.yaml`.

- **Dawarich Secret Store Changes**
  - Removed `tokenSecretRef` configuration in `dawarich-secret-store.yaml`.
  - Updated `SecretStore` API version to `external-secrets.io/v1beta1` in `dawarich-secret-store.yaml`.

**Important Files:**
- `bitwarden/bitwarden-deployment.yaml`
- `bitwarden/registry-secret.yaml`
- `dawarich/dawarich-secret-store.yaml`

**Breaking Changes:**
- Updated API version for `SecretStore` may require adjustments in dependent configurations.

## 2025-04-12 – `c421640` by Andrey Bondarenko
- **Added Configuration Files:**
  - Introduced `loki/promtail/longhorn/longhorn-encryption.yaml` for Longhorn storage class with encryption enabled.
  - Added `loki/promtail/longhorn/longhorn-service-monitor.yaml` for monitoring Longhorn with Prometheus.

- **Removed Legacy Files:**
  - Deleted `longhorn/longhorn-encryption.yaml` (moved to `loki/promtail`).
  - Removed `longhorn/longhorn-service-monitor.yaml` (moved to `loki/promtail`).

- **Breaking Changes:**
  - Configuration files for Longhorn encryption and service monitoring have been relocated; ensure updates to references in deployment scripts.

## 2025-04-12 – `fa40bd8` by Andrey Bondarenko
- **Removed CronJob Configuration**
  - Deleted `cron/cronjob-conduit.yaml`, which defined a CronJob for backing up the matrix database.
  - The CronJob was scheduled to run daily at 1:05 AM and utilized Ubuntu for backup operations.

## 2025-04-12 – `39db73e` by Andrey Bondarenko
- **New Additions**:
  - Added `README.md` files in `DEPRECATED/` directories for documentation on deprecated components.
  - Introduced ArgoCD application configurations for:
    - `rancher` in `DEPRECATED/argocd/rancher.yaml`
    - `registry` in `DEPRECATED/argocd/registry.yaml`
    - `trivy` in `DEPRECATED/argocd/trivy.yaml`
  - Added camera deployment and ingress configurations in `DEPRECATED/camera/`:
    - `lighttpd-deployment.yaml`
    - `lighttpd-ingress.yaml`

- **Documentation Updates**:
  - Updated `README.md` in `DEPRECATED/camera/` to clarify the obsolescence of the CCTV setup.

- **Resource Specifications**:
  - Defined resource limits and requests for containers in `lighttpd-deployment.yaml`.

- **Important Notes**:
  - All changes are in deprecated directories; no active components were modified.
  - Ensure to review the new configurations for potential integration into existing workflows.

## 2025-04-13 – `0f676cc` by Andrey Bondarenko
- **Container Image Update**
  - Changed MongoDB image from `mongo:latest` to `harbor.andreybondarenko.com/dockerhub/mongo:latest` in `mongo/mongo-deployment.yaml`.

- **Image Pull Secrets**
  - Added `imagePullSecrets` with `name: my-private-registry` to `mongo/mongo-deployment.yaml`.

- **File Affected**
  - `mongo/mongo-deployment.yaml` updated for private registry access.

## 2025-04-13 – `ac10dbd` by Andrey Bondarenko
- **Deployment Configuration (mysql/mysql-deployment.yaml)**
  - Updated MySQL image from `mysql:8.0` to `harbor.andreybondarenko.com/dockerhub/mysql:latest`.
  - Added `imagePullSecrets` for private registry access.
- **Environment Variables**
  - No changes made to environment variables.

## 2025-04-13 – `045e8ce` by Andrey Bondarenko
- **Deployment Configuration Updates**
  - Updated `mongo-exporter` image to `harbor.andreybondarenko.com/dockerhub/percona/mongodb_exporter:latest`.
  - Set `imagePullPolicy` to `Always` for the `mongo-exporter` container.
  - Added `imagePullSecrets` to use `my-private-registry` for image retrieval.

- **File Affected**
  - `mongo/mongo-exporter-deployment.yaml`

## 2025-04-13 – `3b1fd6c` by Andrey Bondarenko
- **MySQL Deployment Update**
  - Updated MySQL image version from `latest` to `8.0.41` in `mysql/mysql-deployment.yaml`.

## 2025-04-13 – `8425449` by Andrey Bondarenko
- **Image Update**
  - Changed MongoDB exporter image version from `latest` to `0.44.0` in `mongo/mongo-exporter-deployment.yaml`.

## 2025-04-13 – `47b876f` by Andrey Bondarenko
- **Image Update**: Changed container image from `quay.io/prometheuscommunity/postgres-exporter:latest` to `harbor.andreybondarenko.com/quay/prometheuscommunity/postgres-exporter:latest` in `postgres/exporter/postgres-exporter.yaml`.
- **Image Pull Secrets**: Added `imagePullSecrets` section with `my-private-registry` to `postgres/exporter/postgres-exporter.yaml`.

## 2025-04-13 – `185b051` by Andrey Bondarenko
- **Refactor Plex Configuration**
  - Removed deprecated Plex configuration files from `DEPRECATED/plex/`:
    - `plex-deployment.yaml`
    - `plex-pvc.yaml`
    - `plex-service.yaml`
  - Added new Plex configuration files in `plex/`:
    - `plex-deployment.yaml`
    - `plex-pvc.yaml`
    - `plex-service.yaml`

- **Deployment Changes**
  - Updated deployment strategy to `Recreate`.
  - Maintained node affinity settings to prevent scheduling on specific nodes.

- **Persistent Volume Claims**
  - Retained PVC definitions for `plex-lib-lh` and `plex-conf-lh2` with specified storage classes and access modes.

- **Service Configuration**
  - Configured service ports for Plex, including UDP protocols for various functionalities.

**Breaking Changes:**
- Removal of deprecated files may affect existing deployments relying on the old configuration.

## 2025-04-13 – `108563e` by Andrey Bondarenko
- **Deployment Configuration**
  - Updated container image to `harbor.andreybondarenko.com/dockerhub/itzg/minecraft-server:latest` in `minecraft/minecraft-deployment.yaml`.
  - Added `imagePullSecrets` for private registry access.

- **Resource Management**
  - Maintained existing resource limits for CPU and memory in the deployment spec.

## 2025-04-13 – `7119d65` by Andrey Bondarenko
- **Deployment Configuration**
  - Updated `redis-exporter` image to use private registry: `harbor.andreybondarenko.com/dockerhub/oliver006/redis_exporter`.
  - Added `imagePullSecrets` for private registry access.

- **File Modified**
  - `redis/exporter/redis-exporter-deployment.yaml` updated for deployment settings.

## 2025-04-13 – `ab38964` by Andrey Bondarenko
- **Deployment Update**
  - Changed `mysqld-exporter` image source to `harbor.andreybondarenko.com/quay/prometheus/mysqld-exporter:main` in `mysql/mysqld-exporter-deployment.yaml`.
  - Added `imagePullSecrets` configuration for private registry access.

## 2025-04-13 – `f81f117` by Andrey Bondarenko
- **New Configuration Files**
  - Added `thanos/registry-secret.yaml` for managing Docker registry secrets using External Secrets.
  - Added `thanos/SecretStore` configuration for Vault integration.

- **Image Updates**
  - Updated image references in `thanos-compactor.yaml`, `thanos-queuer.yaml`, and `thanos-storage-gateway.yaml` from `quay.io/thanos/thanos:v0.37.1` to `harbor.andreybondarenko.com/quay/thanos/thanos:v0.37.1`.

- **Image Pull Secrets**
  - Added `imagePullSecrets` referencing `my-private-registry` in `thanos-compactor.yaml`, `thanos-queuer.yaml`, and `thanos-storage-gateway.yaml`.

## 2025-04-13 – `7874281` by Andrey Bondarenko
- **Container Configuration**
  - Updated Grafana image source to `harbor.andreybondarenko.com/dockerhub/grafana/grafana:latest` in `metrics/graphana/graphana.yaml`.
  - Added `imagePullSecrets` for private registry access.

- **File Affected**
  - `metrics/graphana/graphana.yaml`

## 2025-04-13 – `b546cf4` by Andrey Bondarenko
- **Image Update**: Changed `image` for `node-exporter` from `prom/node-exporter` to `harbor.andreybondarenko.com/dockerhub/prom/node-exporter` in `metrics/kubernetes-node-exporter/daemonset.yaml`.
- **Image Pull Secrets**: Added `imagePullSecrets` section with `my-private-registry` to `daemonset.yaml`.
- **File Modified**: Only `metrics/kubernetes-node-exporter/daemonset.yaml` was changed.

## 2025-04-13 – `9f6960e` by Andrey Bondarenko
- **Image Updates**:
  - Changed `alertmanager` image to `harbor.andreybondarenko.com/dockerhub/prom/alertmanager:latest`.
  - Changed `prometheus` image to `harbor.andreybondarenko.com/dockerhub/prom/prometheus:latest`.
  - Changed `thanos` image to `harbor.andreybondarenko.com/quay/thanos/thanos:v0.37.2`.
  - Changed `busybox` image to `harbor.andreybondarenko.com/dockerhub/busybox`.

- **Configuration Changes**:
  - Added `imagePullSecrets` for both `alertmanager` and `prometheus` deployments to use `my-private-registry`.

- **File Paths**:
  - Updated files:
    - `metrics/kubernetes-prometheus/alertmanager-depliyment.yaml`
    - `metrics/kubernetes-prometheus/prometheus-deployment.yaml`

- **Breaking Changes**:
  - Deployment images now sourced from a private registry; ensure access to `my-private-registry`.

## 2025-04-13 – `32a3608` by Andrey Bondarenko
- **Deployment Update**
  - Removed obsolete file: `metrics/kubernetes-prometheus/alertmanager-depliyment.yaml`.
  - Added new file: `metrics/kubernetes-prometheus/alertmanager-deployment.yaml` (corrected spelling).

- **Configuration**
  - Deployment configuration for Alertmanager remains unchanged, ensuring continuity in resource requests, limits, and volume mounts.

## 2025-04-13 – `8c9c939` by Andrey Bondarenko
- **Deployment Configuration Updates**
  - Updated Plex container image to use private registry: `harbor.andreybondarenko.com/dockerhub/linuxserver/plex:latest` in `plex/plex-deployment.yaml`.
  - Added `imagePullSecrets` to deployment for private registry access.

- **New Secret Management**
  - Introduced `registry-secret.yaml` for managing Docker registry credentials via External Secrets.
  - Configured `ExternalSecret` and `SecretStore` to pull secrets from Vault at `http://192.168.1.111:8200`.

- **Namespace Specification**
  - Both new resources are created in the `plex` namespace.

## 2025-04-13 – `52d302e` by Andrey Bondarenko
- **Argocd Configuration Updates:**
  - Added Prometheus ServiceMonitor support in `argocd/cert-manager.yaml`.
  - Updated image repository and tags for cert-manager components to `v1.17.1`.

- **Collabora Configuration Updates:**
  - Specified image repository and pull secrets in `argocd/collabora.yaml`.

- **New Registry Secrets:**
  - Introduced `cert-manager/registry-secret.yaml` and `collabora/registry-secret.yaml` for managing private registry access via ExternalSecrets.
  - Configured `vault-secret-store-registry` for both cert-manager and collabora namespaces.

- **Thanos Registry Secret Update:**
  - Removed redundant secret store configuration in `thanos/registry-secret.yaml`.

## 2025-04-13 – `f64c325` by Andrey Bondarenko
- **New Configuration:**
  - Added `registry-secret.yaml` for managing Docker registry credentials using External Secrets.
  - Introduced `SecretStore` configuration for Vault integration.

- **Deployment Updates:**
  - Updated `server-deployment.yaml` and `web-deployment.yaml` to use images from the private registry (`harbor.andreybondarenko.com`).
  - Added `imagePullSecrets` to both deployments to allow access to the private registry.

- **Important Files:**
  - `your-spotify/registry-secret.yaml`
  - `your-spotify/server-deployment.yaml`
  - `your-spotify/web-deployment.yaml`

- **Breaking Changes:**
  - Image paths have changed; ensure the new private registry is accessible.

## 2025-04-13 – `addc65a` by Andrey Bondarenko
- **Argocd Configuration Updates**
  - Added parameters for image registry and security settings in `argocd/elasticsearch.yaml`:
    - `global.imageRegistry`: Set to `harbor.andreybondarenko.com/dockerhub`
    - `image.pullSecrets[0].name`: Set to `my-private-registry`
    - `global.security.allowInsecureImages`: Set to `'true'`

- **New Registry Secret Management**
  - Introduced `elastic/registry-secret.yaml`:
    - Created `ExternalSecret` for `my-private-registry` with a refresh interval of 15 minutes.
    - Configured `SecretStore` for Vault integration, pointing to `http://192.168.1.111:8200`.

- **Breaking Change**
  - New dependency on external secrets management; ensure Vault is properly configured for `elastic` namespace.

## 2025-04-13 – `2a58682` by Andrey Bondarenko
- **Promtail Configuration Updates**
  - Changed Promtail image to `harbor.andreybondarenko.com/dockerhub/grafana/promtail` in `loki/promtail/promtail.yaml`.
  - Added `imagePullSecrets` for private registry access in `loki/promtail/promtail.yaml`.

- **New Registry Secret Configuration**
  - Introduced `loki/promtail/registry-secret.yaml` to manage Docker registry credentials via External Secrets.
  - Configured `SecretStore` for Vault integration, specifying server and authentication details.

- **Breaking Change**
  - Promtail now requires access to a private Docker registry; ensure `my-private-registry` secret is configured.

## 2025-04-13 – `661a553` by Andrey Bondarenko
- **Deployment Updates**
  - Updated `nginx` image to `harbor.andreybondarenko.com/dockerhub/nginx:latest` in `conduit/nginx-deployment.yaml`.
  - Updated `synapse` image to `harbor.andreybondarenko.com/dockerhub/matrixdotorg/synapse:latest` in `conduit/synapse-deployment.yaml`.

- **Secret Management**
  - Added `registry-secret.yaml` to define `ExternalSecret` and `SecretStore` for private registry access.
  - Introduced `imagePullSecrets` in both `nginx` and `synapse` deployments to utilize `my-private-registry`.

- **File Additions**
  - New file: `conduit/registry-secret.yaml` for managing Docker registry credentials.

## 2025-04-13 – `a6387fb` by Andrey Bondarenko
- **Configuration Updates**
  - Added `image.registry` with value `harbor.andreybondarenko.com/dockerhub` to `argocd/redis.yaml`.
  - Added `image.pullSecrets[0].name` with value `my-private-registry` to `argocd/redis.yaml`.

- **File Affected**
  - Updated `argocd/redis.yaml`.

## 2025-04-13 – `56dd79f` by Andrey Bondarenko
- **Configuration Updates**:
  - Updated `repoURL` format in `argocd/loki.yaml`.
  - Added image repository parameters for `memcachedExporter`, `memcached`, and `loki` with new registry paths.
  - Introduced `imagePullSecrets` for private registry access.

- **Deployment Adjustments**:
  - Set `auth_enabled` to `false` for `loki`.
  - Retained `backend` and `write` replicas at `0`, ensuring no write operations.

- **General Cleanup**:
  - Removed unnecessary quotes from URLs and types for consistency.

## 2025-04-13 – `85057c9` by Andrey Bondarenko
- **ArgoCD Configuration Updates**
  - Added image repository configuration for PostgreSQL in `argocd/postgres.yaml`.
  - Introduced image pull secret reference for private registry in `argocd/postgres.yaml`.

- **Longhorn Registry Secret Management**
  - Created `longhorn/registry-secret.yaml` for managing Docker registry credentials via External Secrets.
  - Defined `ExternalSecret` and `SecretStore` for Vault integration in `longhorn/registry-secret.yaml`.

- **New Dependencies**
  - Introduced dependency on `external-secrets.io` for secret management.

- **Breaking Changes**
  - Ensure compatibility with the new secret management approach; existing registry access methods may need updates.

## 2025-04-14 – `e27b723` by Andrey Bondarenko
- **New External Secrets Configuration:**
  - Added `ExternalSecret` and `SecretStore` for `argocd`, `mastodon`, and `unifi` namespaces to manage private registry access.
  - Each namespace uses the same `vault-secret-store-registry` configuration pointing to Vault at `http://192.168.1.111:8200`.

- **Postgres Exporter Resource Requests:**
  - Updated `postgres-exporter.yaml` to include resource requests for memory (`100Mi`) and CPU (`100m`).

- **Unifi Poller Deployment Update:**
  - Changed image source in `unifi-poller-deployment.yaml` from `ghcr.io` to `harbor.andreybondarenko.com`.
  - Added `imagePullSecrets` to reference `my-private-registry` for image pulling.

- **New Files Created:**
  - `argocd/registry-secret.yaml`, `mastodon/registry-secret.yaml`, `unifi/poller/registry-secret.yaml` for external secrets management.

## 2025-04-14 – `ff8e305` by Andrey Bondarenko
- **Image Updates**:
  - Replaced `quay.io` images with `harbor.andreybondarenko.com` for `argocd` and `dex` components.
  - Updated Redis image to use `harbor.andreybondarenko.com/dockerhub`.

- **Image Pull Secrets**:
  - Added `imagePullSecrets` configuration for private registry access across multiple components.

- **File Added**:
  - New patch file created: `argocd/install.patch`.

## 2025-04-14 – `660744b` by Andrey Bondarenko
- **Loki Configuration**
  - Added sidecar image configuration in `argocd/loki.yaml` for enhanced logging capabilities.

- **Postgres Configuration**
  - Updated metrics image registry in `argocd/postgres.yaml` to use the private registry `harbor.andreybondarenko.com/dockerhub`.

## 2025-04-14 – `ad526dc` by Andrey Bondarenko
- **Deployment Configuration**
  - Updated image tag in `unifi/poller/unifi-poller-deployment.yaml` to remove `:latest` suffix.

- **Resource Management**
  - Reduced memory request from `128Mi` to `100Mi` in `unifi/poller/unifi-poller-deployment.yaml`.

## 2025-04-14 – `cf3fb20` by Andrey Bondarenko
- **Deployment Update**
  - Updated `unifi-poller` image to `harbor.andreybondarenko.com/github/unpoller/unpoller:latest` in `unifi/poller/unifi-poller-deployment.yaml`.

## 2025-04-14 – `b80bd64` by Andrey Bondarenko
- **Resource Configuration**
  - Updated memory limit for Minecraft deployment from **1512Mi** to **3512Mi** in `minecraft/minecraft-deployment.yaml`.

## 2025-04-16 – `973a673` by Andrey Bondarenko
- **Argocd Configuration Updates:**
  - Removed hardcoded image repository and tags from `argocd/cert-manager.yaml`.
  - Updated `argocd/nfs-provisioner.yaml` to use a new values format for NFS server and path.
  - Changed `repoURL` in `argocd/vault.yaml` to point to a private Docker registry.

- **Redis Configuration:**
  - Removed image pull secret from `argocd/redis.yaml`.

- **MySQL Deployment:**
  - Removed image pull secret from `mysql/mysql-deployment.yaml`.

**Breaking Changes:**
- Removal of image pull secrets may affect deployments relying on private registries.

## 2025-04-16 – `6094084` by Andrey Bondarenko
- **Configuration Update**
  - Added `apiVersion` and `kind` for `SecretStore` in `dawarich/dawarich-secret-store.yaml`.

- **File Path**
  - Modified `dawarich/dawarich-secret-store.yaml`.

## 2025-04-16 – `c750d26` by Andrey Bondarenko
- **Configuration Update**
  - Updated Prometheus scrape target for NGINX ingress controller in `metrics/kubernetes-prometheus/config-map.yaml`:
    - Changed from `nginx-ingress-ingress-nginx-controller-metrics` to `ingress-nginx-controller-metrics`.

## 2025-04-16 – `8a09c77` by Andrey Bondarenko
- **Mastodon Configuration Updates**
  - Changed image repository for Mastodon and streaming from `ghcr.io` to `harbor.andreybondarenko.com`.
  - Updated secret names in `secret-store.yaml`:
    - `vault-token` renamed to `vault-redis-token`.
    - `vault-token-mastodon` renamed to `vault-token`.

- **Mongo Deployment Adjustments**
  - Increased memory limit from `200Mi` to `2000Mi` in `mongo/mongo-deployment.yaml`.

- **Longhorn Service Modification**
  - Updated external IP from `192.168.1.104` to `192.168.1.105` in `services/longhorn-system.yaml`.

**Important Files:**
- `mastodon/mastodon-values.yaml`
- `mastodon/secret-store.yaml`
- `mongo/mongo-deployment.yaml`
- `services/longhorn-system.yaml`

**Breaking Changes:**
- Image repository change may affect deployment configurations.

## 2025-04-16 – `5726625` by Andrey Bondarenko
- **New Script Addition**
  - Added `create_secrets.sh` for managing Kubernetes secrets and ExternalSecrets.

- **Functionality**
  - Checks for existing `vault-token-registry`, `my-private-registry`, and `vault-secret-store-registry` secrets in all namespaces.
  - Creates `vault-token-registry` secret if it does not exist.
  - Creates `ExternalSecret` named `my-private-registry` if it does not exist.
  - Creates `SecretStore` named `vault-secret-store-registry` if it does not exist.

- **Kubernetes Integration**
  - Utilizes `kubectl` commands for secret management and resource creation.
  - Configures `ExternalSecret` to reference a Vault server for secret retrieval.

- **Important Note**
  - Ensure the Vault server address and token are correctly set in the script for proper functionality.

## 2025-04-17 – `62810a4` by Andrey Bondarenko
- **Mastodon Configuration:**
  - Updated Elasticsearch hostname in `mastodon/mastodon-values.yaml` from `elastic-elasticsearch.elastic.svc.cluster.local` to `elasticsearch.elastic.svc.cluster.local`.

- **Nextcloud Deployment:**
  - Increased `tmp` volume size limit in `nextcloud/php-deployment.yaml` from `512Mi` to `1512Mi`.

## 2025-04-17 – `8930158` by Andrey Bondarenko
- **Deployment Configuration Changes**
  - Reduced `replicas` from 2 to 1 in `nextcloud/php-deployment.yaml`.

- **Node Selector Update**
  - Changed `nodeSelector` operator from `NotIn` to `In`.
  - Updated node value from `w4.k8s.my.lan` to `w386.k8s.my.lan`.

- **File Affected**
  - `nextcloud/php-deployment.yaml` modified.

## 2025-04-18 – `d046bc2` by Andrey Bondarenko
- **Configuration Update**
  - Increased storage request from `1Gi` to `3Gi` in `wordpress/php-pvc.yaml`.

## 2025-04-18 – `2cfacee` by Andrey Bondarenko
- **Configuration Update**
  - Updated storage request in `nextcloud/php-pvc.yaml` from `236223201280` to `268435456ki` (256Gi).

## 2025-04-18 – `02b7e46` by Andrey Bondarenko
- **Configuration Update**
  - Changed storage request format in `nextcloud/php-pvc.yaml`:
    - Updated `storage: 268435456ki` to `storage: 268435456k`.

## 2025-05-14 – `b514efd` by Andrey Bondarenko
- **Documentation Updates**
  - Added "Dawarich to replace Google Maps Timeline" to the list of tools in README.md.
  - Added a TODO item regarding the decision on separate databases for applications.

## 2025-05-14 – `e2523c2` by Andrey Bondarenko
- **Documentation Updates**
  - Added "Harbor as image registry" to the README.
  - Updated TODO list: clarified decision on separate databases and added "Move to Graphana Alloy".

## 2025-05-15 – `0410d9c` by Andrey Bondarenko
- **New Feature**: Added PersistentVolumeClaim for PostgreSQL.
  - File: `postgres/postgresql-pvc.yaml`
  - Namespace: `db`
  - Storage: `25Gi` with `ReadWriteOnce` access mode using `longhorn` storage class.

## 2025-05-16 – `432334e` by Andrey Bondarenko
- **Documentation Updates**
  - Added badges for K3s, Helm, Longhorn, Prometheus, and Grafana to `README.md` for enhanced visibility of project dependencies and tools.

## 2025-05-21 – `cf6340d` by Andrey Bondarenko
- **Connectivity Exporter Setup**
  - Added `connectivity-exporter-configmap.yaml`: ConfigMap for connectivity checks with multiple endpoints.
  - Added `connectivity-exporter-deployment.yaml`: Deployment configuration for the connectivity exporter service.
  - Added `connectivity-exporter-service.yaml`: Service definition exposing the connectivity exporter on port 9090.

- **Prometheus Integration**
  - Updated `config-map.yaml`: Added new job for scraping connectivity exporter metrics every 45 seconds.

**Important Files:**
- `connectivity-exporter/connectivity-exporter-configmap.yaml`
- `connectivity-exporter/connectivity-exporter-deployment.yaml`
- `connectivity-exporter/connectivity-exporter-service.yaml`
- `metrics/kubernetes-prometheus/config-map.yaml`

**Breaking Changes:**
- None noted in this commit.

## 2025-05-21 – `93d4251` by Andrey Bondarenko
- **Storage Configuration Update**
  - Increased `storage` request from `125Gi` to `155692564480` in `thanos/thanos-compactor-pvc.yaml`.

## 2025-05-23 – `d9210cd` by Andrey Bondarenko
### CHANGELOG for Commit d9210cd

#### New Features
- **Chrome Deployment**: Added `chrome-deployment.yaml` and `chrome-service.yaml` for running a Chrome instance with remote debugging enabled.
- **Karakeep Deployment**: Introduced `karakeep-deployment.yaml`, deploying the Karakeep application with persistent storage.
- **Meilisearch Deployment**: Added `meilisearch-deployment.yaml` and `meilisearch-service.yaml` for Meilisearch integration.

#### Configuration
- **Persistent Volume Claims**: Created `karakeep-data-pvc.yaml` and `meili-data-pvc.yaml` for persistent storage management.
- **Environment Configuration**: Added `karakeep-env-configmap.yaml` for environment variable management.

#### Ingress
- **Ingress Configuration**: Introduced `karakeep-ingres.yaml` for routing traffic to the Karakeep service with SSL support.

#### Services
- **Service Definitions**: Added `karakeep-service.yaml` for exposing the Karakeep application and `chrome-service.yaml` for the Chrome instance.

#### Notes
- All new files are located in the `karakeep` directory.
- Ensure to configure the necessary secrets for Meilisearch and Karakeep.

## 2025-05-23 – `5eca6c8` by Andrey Bondarenko
- **New Resources**:
  - Added `DaemonSet` for Alloy in `loki/alloy/alloy-daemonset.yaml`.
  - Added `ServiceAccount` and associated RBAC roles in `loki/alloy/alloy-serviceaccount.yaml`.

- **Configuration**:
  - `DaemonSet` runs Alloy container with specified image and mounts for configuration and logs.
  - `ServiceAccount` created for Alloy with necessary permissions to access pods, nodes, namespaces, and jobs.

- **RBAC**:
  - Defined `ClusterRole` and `ClusterRoleBinding` for Alloy to enable required access rights.

- **Namespace**:
  - All resources are deployed in the `monitoring` namespace.

## 2025-05-23 – `cc9685d` by Andrey Bondarenko
- **Deployment Strategy Change**
  - Changed deployment strategy from `RollingUpdate` to `Recreate` in `dawarich/dawarich-deploy.yaml`.

- **Removed Rolling Update Parameters**
  - Removed `maxUnavailable` and `maxSurge` settings from deployment configuration.

**Breaking Change**: This change alters the deployment behavior, affecting application availability during updates.

## 2025-05-23 – `f18b4e0` by Andrey Bondarenko
- **Documentation Updates**
  - Added "Karakeep for bookmarks" to the README.md.
  - Added "Connectivity checker" to the README.md.

## 2025-06-02 – `1e2f6fb` by Andrey Bondarenko
- **Deployment Configuration (dawarich-deploy.yaml)**:
  - Added environment variables for database paths: `QUEUE_DATABASE_PATH`, `CACHE_DATABASE_PATH`, `CABLE_DATABASE_PATH`.
  - Mounted new volume `dawarich-db-data` at `/dawarich_db_data`.

- **Persistent Volume Claim (dawarich-pvc.yaml)**:
  - Introduced new PVC named `dawarich-db-data` with `ReadWriteOnce` access mode and `longhorn` storage class.

- **Breaking Change**:
  - New database paths and PVC may require updates to existing configurations or deployments.

## 2025-06-02 – `0281709` by fossabot
- **Documentation Updates**
  - Added FOSSA status badges to `README.md` for project license tracking.
  - Introduced a new "License" section in `README.md`.

## 2025-06-07 – `9688945` by Andrey Bondarenko
- **Environment Variables**:
  - Removed `REDIS_URL`, `REDIS_PASSWORD`, `RAILS_MIN_THREADS`, and `RAILS_MAX_THREADS` from deployment configuration in `dawarich/dawarich-deploy.yaml`.

- **Resource Limits**:
  - Increased memory limit for the main container from `2Gi` to `4Gi`.

- **Container Configuration**:
  - Removed entire configuration for `dawarich-sidekiq` container, including environment variables and resource settings.

- **File Affected**:
  - `dawarich/dawarich-deploy.yaml` is the only modified file.

- **Breaking Change**:
  - Removal of `dawarich-sidekiq` container may impact background processing functionality.

## 2025-06-08 – `271d528` by Andrey Bondarenko
- **New Ingress Configuration**
  - Added `plex/plex-ingress.yaml` for NGINX ingress setup.
  - Configures TLS with Let's Encrypt for `plex.andreybondarenko.com`.
  - Sets up routing to `plex` service on port `32400`.
  - Includes annotations for SSL redirection and body size limits.

## 2025-06-09 – `4549244` by Andrey Bondarenko
- **New ConfigMap Creation**
  - Added `alloy-configmap.yaml` in `loki/alloy/` for Alloy configuration.

- **Livedebugging and Discovery Configuration**
  - Enabled livedebugging and configured Kubernetes pod discovery with relabeling rules.

- **Log Processing Stages**
  - Defined log processing stages for Kubernetes pods and cluster events, including decolorization and dropping specific paths.

- **Loki Write Configuration**
  - Configured Loki write endpoint for log ingestion at `http://loki.loki.svc.cluster.local:3100/loki/api/v1/push`.

- **File Structure**
  - New file introduces a comprehensive configuration structure for monitoring and logging within Kubernetes environments.

## 2025-06-10 – `3ba8366` by Andrey Bondarenko
- **Configuration Update**
  - Changed `collabora.server_name` value in `argocd/collabora.yaml` from `office.andreybondarenko.com:443` to `office.andreybondarenko.com`.

## 2025-06-11 – `27d6558` by Andrey Bondarenko
- **Image Source Updates:**
  - Updated Chrome container image to `harbor.andreybondarenko.com/google/zenika-hub/alpine-chrome:123` in `chrome-deployment.yaml`.
  - Changed Karakeep web container image to `harbor.andreybondarenko.com/github/karakeep-app/karakeep:release` in `karakeep-deployment.yaml`.
  - Modified Meilisearch container image to `harbor.andreybondarenko.com/dockerhub/getmeili/meilisearch:v1.13.3` in `meilisearch-deployment.yaml`.

- **Files Affected:**
  - `karakeep/chrome-deployment.yaml`
  - `karakeep/karakeep-deployment.yaml`
  - `karakeep/meilisearch-deployment.yaml`

## 2025-06-11 – `a944ba8` by Andrey Bondarenko
- **Deployment Configuration (dawarich-deploy.yaml)**:
  - Added `REDIS_URL` and `REDIS_PASSWORD` environment variables for Redis connection.
  - Introduced `RAILS_MIN_THREADS` and `RAILS_MAX_THREADS` settings.
  - Removed database path environment variables for SQLite.
  - Added a new `dawarich-sidekiq` container with specific environment variables and resource limits.

- **External Secrets Configuration (dawarich-external-secrets.yaml)**:
  - Reduced `refreshInterval` from `15m` to `1m` for all secrets.
  - Updated `property` for `redis-uri` to `redis-dawarich-uri`.

- **Breaking Changes**:
  - Removed SQLite database path configurations; ensure migration to PostgreSQL is complete.
  - Adjusted secret properties; verify external secret configurations.

## 2025-06-17 – `fedf611` by Andrey Bondarenko
- **Dependency Update**
  - Updated `targetRevision` for `ingress-nginx` from `4.11.1` to `4.12.3` in `argocd/ingress-nginx.yaml`.

## 2025-06-17 – `bec84d8` by Andrey Bondarenko
- **Service Configuration Updates**
  - Updated `externalIPs` for `argocd` service from `192.168.1.105` to `192.168.1.111` in `services/argocd.yaml`.
  - Updated `externalIPs` for `longhorn-ui` service from `192.168.1.105` to `192.168.1.111` in `services/longhorn-system.yaml`.

- **File Changes**
  - Modified `services/argocd.yaml` and `services/longhorn-system.yaml`.

## 2025-06-17 – `07dfa82` by Andrey Bondarenko
- **Resource Limits Update**:
  - Increased memory limit for deployment from **2Gi** to **20Gi** in `dawarich/dawarich-deploy.yaml`.
  - Increased memory limit for another deployment from **4Gi** to **8Gi** in the same file.

- **File Affected**:
  - `dawarich/dawarich-deploy.yaml`

## 2025-06-17 – `175f775` by Andrey Bondarenko
- **Added Monitoring Job**: Introduced new job configuration for external metrics scraping.
  - **Job Name**: `external`
  - **Scrape Interval**: 45 seconds
  - **Scrape Timeout**: 30 seconds
  - **Metrics Path**: `/metrics`
  - **Target**: `backup.andreybondarenko.com:9090`

- **File Modified**: `metrics/kubernetes-prometheus/config-map.yaml`

## 2025-06-19 – `486112a` by Andrey Bondarenko
- **Resource Adjustments:**
  - Updated memory requests and limits across multiple deployments, notably:
    - **Bitwarden**: Reduced memory from 1344Mi to 1000Mi.
    - **ClamAV**: Increased memory request to 3202Mi.
    - **Conduit Nginx/Synapse**: Reduced memory to 166Mi.
    - **Dawarich**: Adjusted requests to 2405Mi and limits to 2405Mi.
    - **Karakeep**: Added resource requests for Chrome, Karakeep, and Meilisearch deployments.

- **File Changes:**
  - **Dovecot**:
    - Deleted `dovecot-lmtp-service.yaml` and replaced with a new version.
    - Adjusted memory requests in `dovecot-deployment.yaml` from 296Mi to 238Mi.

- **New Files:**
  - Introduced `dovecot-lmtp-service.yaml` with updated service configuration.

- **Deployment Updates:**
  - Adjusted resource configurations for deployments in **Dawarich**, **Karakeep**, and **Loki** to optimize performance and resource usage.

- **Breaking Changes:**
  - The removal of the old `dovecot-lmtp-service.yaml` may affect existing configurations relying on the previous setup.

## 2025-06-19 – `6c5ed3c` by Andrey Bondarenko
- **API Version Upgrade**
  - Updated `apiVersion` from `external-secrets.io/v1beta1` to `external-secrets.io/v1` across multiple files, including:
    - `argocd/registry-secret.yaml`
    - `bitwarden/*.yaml`
    - `cert-manager/registry-secret.yaml`
    - `clamav/*.yaml`
    - `collabora/registry-secret.yaml`
    - `conduit/*.yaml`
    - `dawarich/*.yaml`

- **Secret Management**
  - Modified `ExternalSecret` and `SecretStore` definitions to align with the new API version.

- **Script Update**
  - Updated `create_secrets.sh` to reflect the new API version for `ExternalSecret` and `SecretStore` creation.

**Breaking Change**: Ensure compatibility with `external-secrets.io/v1` as previous versions (`v1beta1`) are no longer supported.

## 2025-06-20 – `52006da` by Andrey Bondarenko
- **Resource Adjustments**:
  - Updated CPU and memory requests/limits for various services:
    - Elasticsearch: Reduced CPU requests from 500m to 52m; memory requests increased to 779Mi.
    - Ingress NGINX: Added CPU (70m) and memory (229Mi) requests.
    - Postgres: Increased CPU requests from 100m to 163m; memory requests increased to 1634Mi.
    - Redis: Reduced CPU requests from 400m to 54m; memory requests set to 100Mi.
    - Vault: Reduced CPU requests from 400m to 90m; memory requests set to 399Mi.

- **New Configurations**:
  - Added `redis-dawarich.yaml` for a new Redis deployment with specified resource requests.
  - Introduced `namespance.yaml` for cert-manager with default resource limits.

- **Version Updates**:
  - Updated Loki target revision from 6.28.0 to 6.30.1.

- **File Changes**:
  - Modified 19 files across multiple services including Argocd, Cert-Manager, and Connectivity Exporter.

- **Breaking Changes**:
  - Significant changes in resource configurations may impact performance; review resource allocation for production readiness.

## 2025-06-21 – `44410cd` by Andrey Bondarenko
- **Dependency Update**
  - Updated `targetRevision` in `argocd/cert-manager.yaml` from `v1.17.1` to `v1.18.1`.

## 2025-06-21 – `56d64a0` by Andrey Bondarenko
- **Bitwarden Deployment**:
  - Increased CPU requests from `10m` to `288m` and memory from `1000Mi` to `1150Mi`.
  - Adjusted Promtail resource requests: CPU from `10m` to `177m`, memory from `100Mi` to `107Mi`.

- **Harbor Configuration**:
  - Updated database memory requests from `113Mi` to `250Mi`.
  - Added resource requests for registry: CPU `124m`, memory `100Mi`.

- **Thanos Queuer**:
  - Enhanced resource requests: CPU from `10m` to `854m`, memory from `700Mi` to `905Mi`.

**Note**: No breaking changes identified.

## 2025-06-21 – `d6a8f16` by Andrey Bondarenko
- **Dependency Update**
  - Updated PostgreSQL Helm chart `targetRevision` from `15.5.19` to `16.6.3` in `argocd/postgres.yaml`.

- **File Affected**
  - `argocd/postgres.yaml`

## 2025-06-21 – `1a54f3d` by Andrey Bondarenko
- **Argocd Configuration (collabora.yaml)**:
  - Updated Helm values format for Collabora configuration.
  - Set resource requests and limits for CPU and memory.

- **Mastodon Configuration (mastodon-values.yaml)**:
  - Defined resource limits and requests for Sidekiq, Streaming, and Web containers.
  - Removed commented-out resource configurations for clarity.

- **Prometheus Deployment (prometheus-deployment.yaml)**:
  - Increased memory requests and limits from 2550Mi to 2864Mi for Prometheus container.

**Note**: No breaking changes identified.

## 2025-06-21 – `e9d470f` by Andrey Bondarenko
- **Resource Configuration Update**
  - Increased CPU request from `10m` to `171m` in `argocd/collabora.yaml`.

## 2025-06-21 – `22d00c6` by Andrey Bondarenko
- **Image Updates**
  - Changed image repository from `quay.io` to `harbor.andreybondarenko.com` for multiple Argocd and Dex images.
  - Updated Argocd images to versions `v2.14.6` and `v3.0.6`.

- **Resource Management**
  - Added resource requests and limits for various components:
    - CPU requests: 10m, 67m, 127m.
    - Memory requests: 100Mi, 121Mi, 142Mi, 151Mi, 537Mi.

- **Image Pull Secrets**
  - Introduced `imagePullSecrets` with `my-private-registry` for private image access across multiple components.

- **File Affected**
  - Modifications made in `argocd/install.patch`.

## 2025-06-24 – `2c1133a` by Andrey Bondarenko
- **Resource Allocation Updates**
  - Increased memory requests and limits for `karakeep-deployment.yaml` from 3238Mi to 5238Mi.
  - Increased memory requests and limits for `meilisearch-deployment.yaml` from 245Mi to 750Mi.

- **Files Modified**
  - `karakeep/karakeep-deployment.yaml`
  - `karakeep/meilisearch-deployment.yaml`

No breaking changes noted.

## 2025-07-07 – `7d11a8e` by Andrey Bondarenko
- **Deployment Configuration**
  - Updated `plex/plex-deployment.yaml` to change node selector operator from `NotIn` to `In` for hostname matching.
  - Changed matched hostname value from `w4.k8s.my.lan` to `w386.k8s.my.lan`.

- **Container Image**
  - No changes made to the container image reference.

## 2025-07-17 – `9c5f8b7` by Andrey Bondarenko
- **Service Configuration Update**
  - Updated label from `name: longhorn` to `app.kubernetes.io/name: longhorn` in `services/longhorn-system.yaml`.
  - Changed external IP from `192.168.1.111` to `192.168.1.105` in `services/longhorn-system.yaml`.

## 2025-07-17 – `aaf789d` by Andrey Bondarenko
- **Deployment Changes:**
  - Updated volume mount name from `plex-lib-lh` to `plex-lib` in `plex/plex-deployment.yaml`.
  - Adjusted persistent volume claim name from `plex-lib-lh` to `plex-lib`.

- **Persistent Volume Configuration:**
  - Added new `PersistentVolume` definition in `plex/plex-pvc.yaml` with 15Ti capacity and local storage path.
  - Changed `PersistentVolumeClaim` for `plex-lib` to use `ReadWriteOnce` access mode and `local-path` storage class.

- **Breaking Changes:**
  - Renamed volume and PVC from `plex-lib-lh` to `plex-lib`, requiring updates in dependent configurations.

## 2025-07-25 – `c1736ab` by Andrey Bondarenko
- **Deployment Changes:**
  - Added node affinity to `minio-single-deployment.yaml` to restrict scheduling to node `w386.k8s.my.lan`.

- **Persistent Volume Configuration:**
  - Introduced `PersistentVolume` definition in `minio-single-pvc.yaml` with 5Ti storage capacity and local path `/storage/k8s/minio`.
  - Updated `PersistentVolumeClaim` to use `local-path` storage class and changed requested storage from 30Gi to 5Ti.

- **Breaking Changes:**
  - The storage class for the `PersistentVolumeClaim` has been changed from `nfs-client` to `local-path`.

## 2025-07-25 – `b7831c5` by Andrey Bondarenko
- **Resource Configuration Update**:
  - Increased memory requests and limits for Bitwarden deployment from 1150Mi to 1350Mi in `bitwarden/bitwarden-deployment.yaml`.

## 2025-07-25 – `a878706` by Andrey Bondarenko
- **Resource Adjustments**:
  - Increased memory requests and limits for `dawarich` deployment from `542Mi` to `842Mi` in `dawarich/dawarich-deploy.yaml`.
  - Increased memory requests and limits for Prometheus deployment from `239Mi` to `439Mi` in `metrics/kubernetes-prometheus/prometheus-deployment.yaml`.

- **Files Modified**:
  - `dawarich/dawarich-deploy.yaml`
  - `metrics/kubernetes-prometheus/prometheus-deployment.yaml`

No breaking changes identified.

## 2025-07-25 – `2305812` by Andrey Bondarenko
- **Removed**: Deleted `bitwarden/registry-secret.yaml` file, which contained configurations for `ExternalSecret` and `SecretStore`.
- **Impact**: This change may affect the deployment of Bitwarden's private registry access and secret management.

## 2025-07-25 – `77d598f` by Andrey Bondarenko
- **Removed Files:**
  - Deleted `clamav/registry-secret.yaml`: Removed ExternalSecret configuration for private registry.
  - Deleted `clamav/secret-store-registry.yaml`: Removed SecretStore configuration for Vault.

- **Impact:**
  - Both deletions may affect the integration with external secrets management for the ClamAV deployment. Ensure alternative configurations are in place if needed.

## 2025-07-25 – `deffc0f` by Andrey Bondarenko
- **Removed Files:**
  - Deleted `wordpress/registry-secret.yaml`.

- **Updated Configuration:**
  - Modified `wordpress/secret-store.yaml`:
    - Removed detailed Vault configuration (server, path, version, auth).
    - Retained basic `SecretStore` structure.

- **Breaking Change:**
  - Removal of `registry-secret.yaml` may affect existing deployments relying on the private registry configuration.

## 2025-07-25 – `4f24af8` by Andrey Bondarenko
- **Removed:**
  - Deleted `unifi/poller/registry-secret.yaml` file, including definitions for `ExternalSecret` and `SecretStore`.

- **Updated:**
  - Cleaned up `wordpress/secret-store.yaml` by removing an empty line at the beginning.

## 2025-07-25 – `bf906d5` by Andrey Bondarenko
- **Removed Registry Secrets:**
  - Deleted `registry-secret.yaml` files from:
    - `elastic`
    - `mastodon`
    - `minio-single`
    - `plex`

- **Removed External Secrets Configuration:**
  - All configurations for `ExternalSecret` and `SecretStore` related to private registry access have been removed across all namespaces.

- **Breaking Change:**
  - Removal of registry secrets may impact deployments relying on these configurations for accessing private container registries.

## 2025-07-25 – `b82029e` by Andrey Bondarenko
- **Removed Files:**
  - Deleted `registry-secret.yaml` files for multiple namespaces:
    - `argocd`
    - `cert-manager`
    - `collabora`
    - `conduit`
    - `thanos`
  - Deleted `create_secrets.sh` script.

- **Breaking Changes:**
  - Removal of all `ExternalSecret` and `SecretStore` configurations for the specified namespaces, impacting secret management.

- **Implications:**
  - Users must recreate or migrate secrets manually as existing configurations are no longer available.

## 2025-07-25 – `a298e23` by Andrey Bondarenko
### CHANGELOG for Commit a298e23

- **Secret Store Updates**
  - Removed `vault-secret-store-registry` configurations from `dawarich-secret-store.yaml`.

- **Deleted Resources**
  - Removed `registry-secret.yaml` files from:
    - `loki/promtail/`
    - `longhorn/`

- **Breaking Changes**
  - Deletion of `ExternalSecret` resources for `my-private-registry` in both `loki` and `longhorn` namespaces.

## 2025-07-25 – `1a2e610` by Andrey Bondarenko
- **SecretStore Updates:**
  - Renamed `vault-secret-store-registry` to `vault-secret-store` in `mail/secret-store.yaml`.
  - Updated `nextcloud/secret-store.yaml` to use `vault-secret-store-redis` instead of `vault-secret-store-registry`.

- **File Removals:**
  - Removed `minio-single/secret-store.yaml`.
  - Removed `nextcloud/registry-secret.yaml`.

- **Breaking Changes:**
  - Deleted references to `vault-secret-store-registry` in multiple files; ensure dependent resources are updated accordingly.

## 2025-07-25 – `6a793f9` by Andrey Bondarenko
- **Deprecation of Image Pull Secrets**:
  - Removed `imagePullSecrets` from multiple YAML files, including:
    - `DEPRECATED/camera/lighttpd-deployment.yaml`
    - `DEPRECATED/camera/vsftpd.yaml`
    - `DEPRECATED/cron/cronjob-minecraft.yaml`
    - `DEPRECATED/rsyslog/rsyslog-deployment.yaml`
    - `bitwarden/bitwarden-deployment.yaml`
    - `clamav/clamav-deployment.yaml`
    - `conduit/nginx-deployment.yaml`
    - `dawarich/dawarich-deploy.yaml`
  - This change affects deployment configurations across various services.

- **Removal of Deprecated External Secrets**:
  - Deleted the `ExternalSecret` definition for `my-private-registry` in `dawarich/dawarich-external-secrets.yaml`.

- **Updates to ArgoCD Configurations**:
  - Adjusted parameters in `argocd/elasticsearch.yaml`, `argocd/loki.yaml`, and `argocd/postgres.yaml` to remove references to `imagePullSecrets`.

- **General Cleanup**:
  - Cleaned up multiple deployment files by removing unnecessary configurations related to private registry access.

**Note**: Ensure to verify the impact of removing `imagePullSecrets` on deployments that rely on private images.

## 2025-07-25 – `af14970` by Andrey Bondarenko
- **Configuration Update**
  - Increased storage request in `nextcloud/php-pvc.yaml` from 256Gi to 280Gi (300647710720 bytes).

- **File Affected**
  - `nextcloud/php-pvc.yaml`

## 2025-07-25 – `6841020` by Andrey Bondarenko
- **SecretStore Configuration Update**
  - Renamed `vault-secret-store-registry` to `vault-secret-store` in `minecraft/secret-store.yaml`.

- **Removed Vault Provider Details**
  - Deleted provider configuration for Vault, including server URL, path, version, and authentication details.

- **Breaking Change**
  - Existing configurations relying on the previous Vault provider settings will need to be updated to reflect the new structure.

## 2025-07-25 – `f1febca` by Andrey Bondarenko
- **Removed Configuration:**
  - Deleted `SecretStore` definition for `vault-secret-store-registry` from `mysql/secret-store.yaml`.
  - Removed Vault server configuration, including server URL, path, and authentication details.

- **File Affected:**
  - `mysql/secret-store.yaml` - significant reduction in configuration, impacting secret management setup.

## 2025-07-26 – `6698e89` by Andrey Bondarenko
- **Added Configuration:**
  - Introduced `.vscode/settings.json` for YAML schema associations.

- **Schema Mappings:**
  - Mapped `zapp.yaml` and `zcodeformat.yaml` to respective IBM Z Open Editor schemas.
  - Associated Kubernetes deployment schema with specific YAML files in the `dawarich` directory.

## 2025-07-27 – `898da38` by Andrey Bondarenko
- **Deployment Update**
  - Changed Docker image tag from `release` to `latest` in `karakeep/karakeep-deployment.yaml`.

## 2025-07-29 – `dfe1426` by Andrey Bondarenko
- **Configuration Update**
  - Added `fasp` to the `mastodon` configuration in `mastodon/mastodon-values.yaml`.

## 2025-07-29 – `cd96ea5` by Andrey Bondarenko
- **Deployment Configuration (mail/rspamd-deployment.yaml)**:
  - Added `worker-cf` configMap for worker-controller configuration.
  - Introduced `logs` emptyDir for log storage.
  - Updated container image from `harbor.andreybondarenko.com/library/rspamd:latest` to `harbor.andreybondarenko.com/github/rspamd/rspamd-docker:latest`.

- **Security Context Changes**:
  - Changed `allowPrivilegeEscalation` from `false` to `true`.
  - Set `readOnlyRootFilesystem` from `true` to `false`.

- **Volume Mount Adjustments**:
  - Updated mount paths for various configurations to `/etc/rspamd/local.d/`.
  - Added initContainer `fix-perms` to set permissions on `/var/lib/rspamd`.

- **Breaking Changes**:
  - Security context modifications may affect container behavior and security posture.

## 2025-07-29 – `cf4cf23` by Andrey Bondarenko
- **Mail Configuration**
  - Removed unnecessary braces from `redis.conf` in `mail/mail-secret.yaml`.
  - Simplified Redis server configuration by directly specifying server addresses.

## 2025-07-29 – `9f469f7` by Andrey Bondarenko
- **Configuration Updates**
  - Added `worker-controller` settings in `mail/mail-secret.yaml` for secure IP and password configuration.
  - Updated `rspamd-configmap.yaml` to comment out Redis configuration includes and remove unnecessary sections for `history`, `greylist`, `neural`, `statistics`, `dkim_signing`, and `antivirus`.

- **File Changes**
  - `mail/mail-secret.yaml`: Introduced new worker-controller configuration.
  - `mail/rspamd-configmap.yaml`: Streamlined Redis configuration and removed legacy includes.

- **Breaking Changes**
  - Commented out critical Redis configuration includes may affect Redis integration; review required for proper functionality.

## 2025-07-29 – `774e866` by Andrey Bondarenko
- **Added ExternalSecret for Worker Controller**
  - New `ExternalSecret` named `workercontroller` created in `mail/mail-secret.yaml` for managing worker controller credentials.
  - Configures `secure_ip`, `bind_socket`, and `password` using secrets.

- **Updated Rspamd Deployment**
  - Modified `rspamd-deployment.yaml` to reference the new `workercontroller` secret instead of the previous config map.
  - Adjusted key mapping for `workercontroller` in the deployment.

- **Removed Legacy Configuration**
  - Removed old worker-controller configuration from `mail/mail-secret.yaml`.

**Note:** Ensure that the new secret structure is compatible with existing deployments to avoid breaking changes.

## 2025-07-29 – `90858a8` by Andrey Bondarenko
- **Secret Store Update**
  - Changed `vault-token` to `vault-synapse` in `conduit/secret-store.yaml`.

- **New Configuration**
  - Added `conduit/synapse-configmap.yaml` for Synapse configuration with external secrets.
  - Config includes server settings, database configuration, and experimental features.

- **Important Notes**
  - Ensure `vault-synapse` is properly configured to avoid service disruptions.
  - Review new Synapse configuration options for compatibility with existing deployments.

## 2025-07-29 – `4b74173` by Andrey Bondarenko
- **Documentation Updates**
  - Removed TODO items regarding database separation and migration to Grafana Alloy from `README.md`.
