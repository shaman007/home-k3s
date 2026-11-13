#!/bin/sh
# Native MariaDB probe for Firefox Sync; no migrations or credential output.
set -eu
export HOME=/tmp
case "${1:-}" in mysql) ;; *) exit 2 ;; esac
budget=${STARTUP_WAIT_SECONDS:-300}
case "$budget" in ''|*[!0-9]*) exit 2 ;; esac
[ "$budget" -ge 1 ] && [ "$budget" -le 300 ] || exit 2
monotonic() { read -r seconds rest < /proc/uptime; printf '%s' "${seconds%%.*}"; }
started=$(monotonic)
while :; do
  if result=$(timeout -s TERM -k 1 5 mariadb --protocol=TCP --batch --skip-column-names \
    --connect-timeout=4 --host="$MYSQL_HOST" --port="${MYSQL_PORT:-3306}" \
    --user="$MYSQL_USER" --database="$MYSQL_DATABASE" \
    --execute='START TRANSACTION READ ONLY; SELECT 1; ROLLBACK;' 2>/dev/null) && [ "$result" = 1 ]; then
    printf '{"stage":"mysql","result":"ready","elapsed_seconds":%s}\n' "$(( $(monotonic) - started ))"
    exit 0
  fi
  elapsed=$(( $(monotonic) - started ))
  if [ "$elapsed" -ge "$budget" ]; then
    printf '{"stage":"mysql","result":"timeout","elapsed_seconds":%s}\n' "$elapsed"
    exit 1
  fi
  printf '{"stage":"mysql","result":"waiting","elapsed_seconds":%s}\n' "$elapsed"
  remaining=$((budget - elapsed))
  if [ "$remaining" -gt 5 ]; then remaining=5; fi
  sleep "$remaining"
  if [ "$(( $(monotonic) - started ))" -ge "$budget" ]; then
    printf '{"stage":"mysql","result":"timeout","elapsed_seconds":%s}\n' "$(( $(monotonic) - started ))"
    exit 1
  fi
done
