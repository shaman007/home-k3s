#!/bin/bash

# DEPRECATED: this historical helper is intentionally disabled.
# Active cluster secrets are managed through Vault and External Secrets.
echo "secrets.sh is deprecated; use Vault and External Secrets instead." >&2
exit 1

# Historical implementation retained for reference:
#
# dirs=( $(ls -la|grep drw|grep -v "\."| awk '{ print $9 }') )
#
# for dirs in "${dirs[@]}"
# do
#     echo $dirs
#     cd $dirs
#     rm ./secret.yaml.asc -f
#     gpg -a -r 'Andrey Bondarenko <me@andreybondarenko.com>' --encrypt secret.yaml
#     cd ..
# done
