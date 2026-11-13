#!/bin/sh
# Same-image main wrapper. A missing dependency must never release cron.php.
set -eu
budget=${STARTUP_WAIT_SECONDS:-300}
case "$budget" in ''|*[!0-9]*) exit 2 ;; esac
[ "$budget" -ge 1 ] && [ "$budget" -le 300 ] || exit 2
monotonic() { read -r seconds rest < /proc/uptime; printf '%s' "${seconds%%.*}"; }
started=$(monotonic)
while :; do
  ready=true
  for mode in nextcloud-sql nextcloud-valkey web; do
    elapsed=$(( $(monotonic) - started ))
    remaining=$((budget - elapsed))
    if [ "$remaining" -le 0 ]; then ready=false; break; fi
    timeout_seconds=5
    if [ "$remaining" -lt 5 ]; then timeout_seconds=$remaining; fi
    if [ "$mode" = web ]; then
      timeout -s TERM -k 1 "$timeout_seconds" php /cron-gate/nextcloud_job_ready.php >/dev/null 2>&1 || ready=false
    else
      timeout -s TERM -k 1 "$timeout_seconds" php /cron-gate/probe_data.php "$mode" >/dev/null 2>&1 || ready=false
    fi
  done
  elapsed=$(( $(monotonic) - started ))
  if [ "$ready" = true ] && [ "$elapsed" -le "$budget" ]; then
    printf '{"event":"cron_dependencies","result":"ready","duration_seconds":%s}\n' "$elapsed"
    exec php /nextcloud/cron.php
  fi
  if [ "$elapsed" -ge "$budget" ]; then
    printf '{"event":"cron_dependencies","result":"skipped","duration_seconds":%s}\n' "$elapsed"
    exit 0
  fi
  remaining=$((budget - elapsed))
  if [ "$remaining" -gt 5 ]; then remaining=5; fi
  sleep "$remaining"
done
