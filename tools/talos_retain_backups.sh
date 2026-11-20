#!/bin/bash
# Count-based retention for this cluster's encrypted etcd objects only.
set -euo pipefail
umask 077
export AWS_PAGER="" AWS_EC2_METADATA_DISABLED=true
export AWS_REQUEST_CHECKSUM_CALCULATION=when_required
export AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
endpoint=http://s3.seaweedfs.svc.cluster.local:8333
bucket=talos-etcd
prefix=home-k8s/
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# Text mode concatenates the per-page rows; sort only after all pages succeed.
aws --endpoint-url "$endpoint" s3api list-objects-v2 --bucket "$bucket" --prefix "$prefix" \
  --query 'Contents[?ends_with(Key, `.snap.zst.age`) || ends_with(Key, `.snap.age`)].[LastModified,Key,ETag,Size]' \
  --output text > "$tmp/list"
sort -r "$tmp/list" > "$tmp/sorted"
count=0
latest=0
while IFS=$'\t' read -r modified key etag size extra; do
  [[ -z "$modified" ]] && continue
  [[ -z "${extra:-}" && "$key" =~ ^home-k8s/[a-zA-Z0-9_./:-]+\.snap(\.zst)?\.age$ && "$size" =~ ^[0-9]+$ && "$size" -gt 0 ]]
  [[ -n "$etag" ]]
  epoch=$(date -d "$modified" +%s)
  now=$(date +%s)
  [[ "$epoch" -le "$now" ]]
  (( epoch > latest )) && latest=$epoch
  count=$((count + 1))
done < "$tmp/sorted"
# Do not prune a stale or empty destination while backup delivery is broken.
[[ "$count" -gt 0 && $(( $(date +%s) - latest )) -lt 7200 ]]
echo "Talos backups=$count keep=20 apply=${RETENTION_APPLY:-false}"
tail -n +21 "$tmp/sorted" > "$tmp/expired"
while IFS=$'\t' read -r modified key etag size; do
  [[ -z "$modified" ]] && continue
  if [[ "${RETENTION_APPLY:-false}" == true ]]; then
    # Conditional deletion protects an object changed since this inventory.
    aws --endpoint-url "$endpoint" s3api delete-object --bucket "$bucket" --key "$key" --if-match "$etag" --output json > /dev/null
    echo "Deleted $key"
  else
    echo "Would delete $key"
  fi
done < "$tmp/expired"
