#!/bin/sh
# Protocol readiness only; no credentials, migrations, or mail-policy changes.
set -eu
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
  result=$(timeout -s TERM -k 1 "$timeout_seconds" valkey-cli --raw -h valkey.mail.svc.cluster.local -p 6379 PING 2>/dev/null) || result=''
  elapsed=$(( $(monotonic) - started ))
  if [ "$result" = PONG ] && [ "$elapsed" -le "$budget" ]; then
    printf '{"event":"mail_dependencies","stage":"valkey","result":"ready","duration_seconds":%s}\n' "$elapsed"
    exit 0
  fi
  if [ "$elapsed" -ge "$budget" ]; then break; fi
  remaining=$((budget - elapsed))
  if [ "$remaining" -gt 5 ]; then remaining=5; fi
  sleep "$remaining"
done
printf '{"event":"mail_dependencies","stage":"valkey","result":"unavailable"}\n'
exit 1
