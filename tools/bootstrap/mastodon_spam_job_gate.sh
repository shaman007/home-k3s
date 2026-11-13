#!/bin/sh
# Read-only dependency/schema barrier; migrations remain web-init owned.
set -eu
status=0
timeout -s TERM -k 1 300 /bin/sh -c '
  bundle exec ruby /cron-gate/mastodon_startup.rb dependencies &&
  bundle exec ruby /cron-gate/mastodon_startup.rb schema
' >/dev/null 2>&1 || status=$?
if [ "$status" -ne 0 ]; then
  printf '{"event":"cron_dependencies","result":"unavailable"}\n'
  exit 75
fi
printf '{"event":"cron_dependencies","result":"ready"}\n'
exec bundle exec rails runner /scripts/sync.rb
