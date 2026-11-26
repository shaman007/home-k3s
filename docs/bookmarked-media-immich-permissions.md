# Bookmarked media: Immich queue permissions

The upload key belongs to the non-admin Private account. Keep its existing
permissions and owner unchanged. Immich 3.4.2 PUT /api/jobs/faceDetection requires
both an admin owner and job.create. Adding job.create to the upload key alone
cannot fix its 403.

Create a separate admin-owned key named bookmarked-media-face-detection with
only job.create. Immich does not provide a permission limited to face detection:
this scope can submit other job commands, but grants no asset reads/uploads or
configuration access. Do not grant all, job.read, or API-key management rights.
Store the value only in OpenBao kv/immich as face_detection_api_key, preserving
api_key and db_password. Never paste it into Git, logs, or chat.

The existing ExternalSecret maps this field to IMMICH_JOB_API_KEY. Only the
immich-upload container receives it; the downloader retains only its upload key.
The face-detection request uses the separate key and force:false, preserving
missing-only processing. Upload and description calls keep IMMICH_API_KEY.
Publish manifests only after the OpenBao field exists. Argo CD and External
Secrets reconcile the change; already-created Jobs retain their original spec.

Verify that /api/api-keys/me reports exactly ["job.create"] for the new key,
that asset listing and queue reading remain forbidden, and that the existing
PUT with command:start, force:false succeeds. Observe the real face-detection
queue through admin UI or the existing monitoring, without broadening key rights.
