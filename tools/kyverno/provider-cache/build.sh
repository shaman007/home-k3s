#!/usr/bin/env bash
set -euo pipefail
# Requires Go 1.26.9+, curl, tar, patch, and Podman. No credentials are handled here.
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
build_dir=${BUILD_DIR:?Set BUILD_DIR to an empty absolute temporary directory}
image=${IMAGE:-harbor.andreybondarenko.com/library/kyverno-reports-controller:v1.19.2-provider-cache.3}
mkdir -p "$build_dir"
curl -fL https://codeload.github.com/kyverno/kyverno/tar.gz/refs/tags/v1.19.2 -o "$build_dir/source.tgz"
printf '%s  %s\n' 9c09a8cf176357852aaf9b81df0c609099ba72d6591b9e2148984a5b8cfe1dda "$build_dir/source.tgz" | sha256sum -c -
tar -xzf "$build_dir/source.tgz" -C "$build_dir"
cd "$build_dir/kyverno-1.19.2"
patch -p1 < "$script_dir/provider-cache.patch"
go test -race ./pkg/controllers/report/utils -run 'TestVpolProviderCache($|ConcurrentSnapshot|ExpiryBoundary|ExceptionUpdates|InformerOrder|Capacity)' -count=1
CGO_ENABLED=0 go build -buildvcs=false -trimpath -ldflags '-s -w -X github.com/kyverno/kyverno/pkg/version.BuildVersion=v1.19.2-provider-cache.3' -o "$build_dir/reports-controller" ./cmd/reports-controller
cp "$script_dir/Containerfile" "$build_dir/Containerfile"
podman build -f "$build_dir/Containerfile" -t "$image" "$build_dir"
printf 'Built %s; publication and deployment are separate steps.\n' "$image"
