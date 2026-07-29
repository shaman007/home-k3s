Here is everyting that is not in use and I don't really care about. It's here for historical reasons, I may fix somt things that's obvious, but I don't test!

This includes the retired Wazuh stack and its related helper manifests.

The root-level `secrets.sh` helper was retired into this directory. It used unsafe
directory parsing and deleted an existing encrypted output before confirming that
the replacement was created successfully. The archived script is intentionally
disabled; use Vault and External Secrets for active secret management.
