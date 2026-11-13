#!/bin/sh
# Skip before starting private Dovecot or touching mail when Rspamd is unavailable.
set -eu
[ "$#" -gt 0 ] || exit 2
budget=${STARTUP_WAIT_SECONDS:-300}
case "$budget" in ''|*[!0-9]*) exit 2 ;; esac
[ "$budget" -ge 1 ] && [ "$budget" -le 300 ] || exit 2
monotonic() { read -r seconds rest < /proc/uptime; printf '%s' "${seconds%%.*}"; }
started=$(monotonic)
while :; do
  elapsed=$(( $(monotonic) - started ))
  remaining=$((budget - elapsed))
  if [ "$remaining" -le 0 ]; then break; fi
  timeout_seconds=5
  if [ "$remaining" -lt 5 ]; then timeout_seconds=$remaining; fi
  status=$(timeout -s TERM -k 1 "$timeout_seconds" curl --noproxy '*' --proto '=http' \
    --silent --connect-timeout 2 --max-time 4 --output /dev/null --write-out '%{http_code}' \
    http://rspamd.mail.svc.cluster.local:11334/ping 2>/dev/null) || status=''
  elapsed=$(( $(monotonic) - started ))
  if [ "$status" = 200 ] && [ "$elapsed" -le "$budget" ]; then
    printf '{"event":"cron_dependencies","result":"ready","duration_seconds":%s}\n' "$elapsed"
    exec "$@"
  fi
  if [ "$elapsed" -ge "$budget" ]; then break; fi
  remaining=$((budget - elapsed))
  if [ "$remaining" -gt 5 ]; then remaining=5; fi
  sleep "$remaining"
done
printf '{"event":"cron_dependencies","result":"skipped"}\n'
exit 0
