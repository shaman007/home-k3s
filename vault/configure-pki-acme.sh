#!/usr/bin/env sh
set -eu
printf '%s\n' 'Retired: private ingress and backend certificate issuance must not be recreated. Use cert-manager and Let’s Encrypt DNS-01.' >&2
exit 1
