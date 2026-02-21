#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  migrate-db.sh [--dump-only | --restore-only]

Environment variables:
  DB_NAME            Required. Database name (letters, numbers, underscore only).
  SOURCE_HOST        Source MySQL host. Default: mysql.db.svc.cluster.local
  SOURCE_PORT        Source MySQL port. Default: 3306
  SOURCE_USER        Source MySQL user. Default: root
  SOURCE_PASSWORD    Required for dump/migrate mode.

  TARGET_HOST        Required for restore/migrate mode.
  TARGET_PORT        Target MySQL port. Default: 3306
  TARGET_USER        Target MySQL user. Default: root
  TARGET_PASSWORD    Required for restore/migrate mode.

  DUMP_FILE          Dump file path.
                     Default: ./<DB_NAME>-YYYYmmdd-HHMMSS.sql
  MYSQL_CHARSET      Default: utf8mb4
  MYSQL_COLLATION    Default: utf8mb4_unicode_ci
  SOURCE_SSL_MODE    Default: DISABLED
  TARGET_SSL_MODE    Default: DISABLED

Examples:
  SOURCE_PASSWORD=oldpass TARGET_HOST=mysql.wordpress.svc.cluster.local \
  TARGET_PASSWORD=newpass DB_NAME=wordpress ./migrate-db.sh

  SOURCE_PASSWORD=oldpass DB_NAME=nextcloud ./migrate-db.sh --dump-only

  TARGET_HOST=mysql.nextcloud.svc.cluster.local TARGET_PASSWORD=newpass \
  DB_NAME=nextcloud DUMP_FILE=./nextcloud.sql ./migrate-db.sh --restore-only
EOF
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

MODE="migrate"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dump-only)
      MODE="dump"
      shift
      ;;
    --restore-only)
      MODE="restore"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

require_command mysqldump
require_command mysql
require_command date

DB_NAME="${DB_NAME:-}"
if [[ -z "$DB_NAME" ]]; then
  echo "DB_NAME is required." >&2
  exit 1
fi
if [[ ! "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "Invalid DB_NAME '$DB_NAME'. Use letters, numbers, and underscore only." >&2
  exit 1
fi

SOURCE_HOST="${SOURCE_HOST:-mysql.db.svc.cluster.local}"
SOURCE_PORT="${SOURCE_PORT:-3306}"
SOURCE_USER="${SOURCE_USER:-root}"
TARGET_PORT="${TARGET_PORT:-3306}"
TARGET_USER="${TARGET_USER:-root}"
MYSQL_CHARSET="${MYSQL_CHARSET:-utf8mb4}"
MYSQL_COLLATION="${MYSQL_COLLATION:-utf8mb4_unicode_ci}"
SOURCE_SSL_MODE="${SOURCE_SSL_MODE:-DISABLED}"
TARGET_SSL_MODE="${TARGET_SSL_MODE:-DISABLED}"
DUMP_FILE="${DUMP_FILE:-./${DB_NAME}-$(date +%Y%m%d-%H%M%S).sql}"

dump_db() {
  : "${SOURCE_PASSWORD:?SOURCE_PASSWORD is required for dump mode}"

  local dump_cmd=(
    mysqldump
    --host="$SOURCE_HOST"
    --port="$SOURCE_PORT"
    --user="$SOURCE_USER"
    --protocol=TCP
    --ssl-mode="$SOURCE_SSL_MODE"
    --single-transaction
    --quick
    --routines
    --events
    --triggers
    --hex-blob
    --set-gtid-purged=OFF
    --default-character-set="$MYSQL_CHARSET"
  )

  # Compatible with older/newer client binaries.
  if mysqldump --help 2>/dev/null | grep -q -- '--column-statistics'; then
    dump_cmd+=(--column-statistics=0)
  fi

  dump_cmd+=("$DB_NAME")

  echo "Dumping '$DB_NAME' from ${SOURCE_HOST}:${SOURCE_PORT} to ${DUMP_FILE}"
  MYSQL_PWD="$SOURCE_PASSWORD" "${dump_cmd[@]}" > "$DUMP_FILE"
}

restore_db() {
  : "${TARGET_HOST:?TARGET_HOST is required for restore mode}"
  : "${TARGET_PASSWORD:?TARGET_PASSWORD is required for restore mode}"

  if [[ ! -f "$DUMP_FILE" ]]; then
    echo "Dump file not found: $DUMP_FILE" >&2
    exit 1
  fi

  echo "Ensuring target database '$DB_NAME' exists on ${TARGET_HOST}:${TARGET_PORT}"
  MYSQL_PWD="$TARGET_PASSWORD" mysql \
    --host="$TARGET_HOST" \
    --port="$TARGET_PORT" \
    --user="$TARGET_USER" \
    --protocol=TCP \
    --ssl-mode="$TARGET_SSL_MODE" \
    -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET $MYSQL_CHARSET COLLATE $MYSQL_COLLATION;"

  echo "Restoring '$DB_NAME' from ${DUMP_FILE} into ${TARGET_HOST}:${TARGET_PORT}"
  MYSQL_PWD="$TARGET_PASSWORD" mysql \
    --host="$TARGET_HOST" \
    --port="$TARGET_PORT" \
    --user="$TARGET_USER" \
    --protocol=TCP \
    --ssl-mode="$TARGET_SSL_MODE" \
    --database="$DB_NAME" \
    < "$DUMP_FILE"
}

case "$MODE" in
  dump)
    dump_db
    ;;
  restore)
    restore_db
    ;;
  migrate)
    dump_db
    restore_db
    ;;
  *)
    echo "Unexpected mode: $MODE" >&2
    exit 1
    ;;
esac

echo "Done."
