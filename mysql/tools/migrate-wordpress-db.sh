#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

export DB_NAME="${DB_NAME:-wordpress}"
export SOURCE_HOST="${SOURCE_HOST:-mysql.db.svc.cluster.local}"
export SOURCE_PORT="${SOURCE_PORT:-3306}"
export SOURCE_USER="${SOURCE_USER:-root}"

export TARGET_HOST="${TARGET_HOST:-mysql.wordpress.svc.cluster.local}"
export TARGET_PORT="${TARGET_PORT:-3306}"
export TARGET_USER="${TARGET_USER:-root}"

exec "${SCRIPT_DIR}/migrate-db.sh" "$@"
