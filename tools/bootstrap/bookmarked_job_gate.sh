#!/bin/sh
# Runs after existing package installation, before export, downloads or uploads.
set -eu
# Explicit tokenFile config: kubectl must not fall back to localhost:8080.
export KUBECONFIG=/cron-gate/kubeconfig
budget=${STARTUP_WAIT_SECONDS:-300}
case "$budget" in ''|*[!0-9]*) exit 78 ;; esac
[ "$budget" -ge 1 ] && [ "$budget" -le 300 ] || exit 78
[ "${IMMICH_INSTANCE_URL:-}" = https://immich.andreybondarenko.com/api ] || exit 78
case "${IMMICH_API_KEY:-}" in ''|*[!a-zA-Z0-9+/.=_-]*) exit 78 ;; esac
now() { read -r seconds rest < /proc/uptime; printf '%s' "${seconds%%.*}"; }
deadline=$(( $(now) + budget ))
run() {
  left=$((deadline - $(now)))
  [ "$left" -gt 0 ] || return 1
  if [ "$left" -gt 8 ]; then left=8; fi
  timeout -s TERM -k 1 "$left" "$@"
}
while [ "$(now)" -lt "$deadline" ]; do
  pod=$(run kubectl get pods -n mastodon --request-timeout=5s \
    -l app.kubernetes.io/component=web,app.kubernetes.io/instance=mastodon -o json 2>/dev/null \
    | jq -r '[.items[]|select(any(.status.conditions[]?; .type=="Ready" and .status=="True"))][0].metadata.name // empty') || pod=''
  mastodon_ready=false
  if [ -n "$pod" ]; then
    if run kubectl exec -i -n mastodon "$pod" -c mastodon-web --request-timeout=6s -- \
      timeout -s TERM -k 1 4 bundle exec ruby - dependencies < /cron-gate/mastodon_startup.rb >/dev/null 2>&1 &&
       run kubectl exec -i -n mastodon "$pod" -c mastodon-web --request-timeout=6s -- \
      timeout -s TERM -k 1 4 bundle exec ruby - schema < /cron-gate/mastodon_startup.rb >/dev/null 2>&1; then
      mastodon_ready=true
    fi
  fi
  status=$(printf 'header = "x-api-key: %s"\nurl = "%s/users/me"\n' "$IMMICH_API_KEY" "$IMMICH_INSTANCE_URL" \
    | run curl --config - --noproxy '*' --proto '=https' --silent --max-time 5 \
      --output /dev/null --write-out '%{http_code}' 2>/dev/null) || status=''
  case "$status" in
    401|403) printf '{"event":"cron_dependencies","result":"denied"}\n'; exit 77 ;;
    404) printf '{"event":"cron_dependencies","result":"invalid-config"}\n'; exit 78 ;;
  esac
  if [ "$mastodon_ready" = true ] && [ "$status" = 200 ] && [ "$(now)" -le "$deadline" ]; then
    printf '{"event":"cron_dependencies","result":"ready"}\n'
    exec /scripts/fetch-bookmarked-media.sh
  fi
  left=$((deadline - $(now)))
  [ "$left" -gt 0 ] || break
  if [ "$left" -gt 5 ]; then left=5; fi
  sleep "$left"
done
mkdir -p /work/import
: > /work/.dependencies-skipped
printf '{"event":"cron_dependencies","result":"skipped"}\n'
exit 0
