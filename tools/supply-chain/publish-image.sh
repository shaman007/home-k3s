#!/usr/bin/env bash
# Publish a reviewed local one-off image and sign the exact registry digest.
set -Eeuo pipefail
image=${1:?Usage: bash publish-image.sh harbor.andreybondarenko.com/library/IMAGE:TAG}
[[ "$image" =~ ^harbor\.andreybondarenko\.com/library/[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*$ ]] || {
  echo 'Expected a tagged image in our Harbor library project' >&2
  exit 1
}
: "${COSIGN_KEY:?Set the signing key reference}"
: "${COSIGN_PUBLIC_KEY:?Set the trusted public key path}"
[[ -r "$COSIGN_PUBLIC_KEY" ]] || exit 1
command -v cosign >/dev/null
command -v podman >/dev/null
digest_file=$(mktemp)
trap 'rm -f "$digest_file"' EXIT
podman push --digestfile "$digest_file" "$image"
digest=$(cat "$digest_file")
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1
repository=${image%:*}
cosign sign --yes --key "$COSIGN_KEY" "$repository@$digest"
cosign verify --key "$COSIGN_PUBLIC_KEY" "$repository@$digest"
printf 'Published, signed and verified %s@%s\n' "$repository" "$digest"
