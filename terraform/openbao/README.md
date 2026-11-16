# OpenBao configuration as code

OpenTofu >= 1.11 and hashicorp/vault 5.11.0 manage the KV v2 mount,
Kubernetes auth configuration, least-privilege External Secrets roles and ACLs,
AIY Voice API role, and Keycloak OIDC roles/group mapping. Existing Keycloak
client `openbao` is reused; `keycloak-client.json` records its public contract.

Secret values are deliberately outside Terraform. The OIDC client secret uses
an ephemeral variable and the provider's write-only argument. Increment
`oidc_client_secret_wo_version` when intentionally rotating it. Keep state and
plans outside Git with restrictive permissions. Never put tokens in command
arguments or committed tfvars. The recovery consumer verifies that the OIDC
secret and root token did not enter state.

## Recovery performed on 2026-11-16

The previous Shamir key was rejected. The old StatefulSet `openbao` is retained
at zero replicas, with all three `data-openbao-*` PVCs unchanged and their PV
reclaim policy changed to Retain. Do not delete or reinitialize these volumes.
The replacement StatefulSet is `openbao-20261116`, using independent PVCs and
the original `openbao` service account, required by the Cilium API egress policy.
Compatibility services retain existing consumer URLs. Namespace storage quota
is 60Gi to accommodate both generations.

The encrypted recovery directory is
`~/.local/state/openbao-recovery` (directory 0700, archives 0600). It contains
Kubernetes Secret mirrors, Talos machine configurations, an etcd snapshot,
and `openbao-new-initialization-2026-11-16.json.age`. The latter contains the
**new generation's** unseal material and initial root token. It is encrypted to
`~/.config/talos-backup/age-recipient.txt`; decryption requires the private
identity `~/.config/talos-backup/age-key.txt`. Keep an independent offline copy
of that identity. A copy solely in cluster-hosted Bitwarden cannot solve a
cluster-wide recovery dependency. No plaintext recovery dump is written.

`tools/openbao/consumer.py` runs one bounded phase at a time:

```sh
python3 tools/openbao/consumer.py unseal --pods openbao-20261116-0 openbao-20261116-1 openbao-20261116-2
python3 tools/openbao/consumer.py configure
python3 tools/openbao/consumer.py restore-kv
```

Do not rerun `restore-kv` after normal operation resumes: it deliberately
restores the dated snapshot and could overwrite subsequent rotations.
`initialize` refuses an existing archive or initialized server. It must only
be used for a deliberately prepared empty generation, never retained PVCs.
`configure` uses the surviving Keycloak admin Secret in memory, applies a
non-destructive plan, and stores the OIDC client credential in OpenBao.
Current state lives under `~/.local/state/openbao-recovery/tofu/`.

The snapshot reconstructs 33 KV paths supporting all 55 ExternalSecrets;
four Thanos object-storage values use the canonical working rendered config.
An additional 15 unmapped application Secrets are preserved under
`kv/recovery/kubernetes/<namespace>/<name>` with original base64 data and source
date. These paths deliberately do not claim to match historical KV mappings.
`openbao-rebuilt-2026-11-16.snap.age` is the verified encrypted Raft snapshot
after reconstruction. This is partial reconstruction, not recovery of the old complete OpenBao.
Unmirrored KV values, old leases/tokens, private PKI CA keys, SSH signer keys,
and desktop-only GitHub/mail/Harbor credentials require independent recovery
or explicit replacement. Do not create a replacement CA under an existing
trust relationship without planning consumer trust migration. Current
Let's Encrypt DNS01 uses the restored GoDaddy credential, not the old PKI CA.

## GitOps handover

The live `openbao` Application points to the new generation. The parent
`argocd-applications` and `namespaces` Applications have `skip-reconcile=true`
to prevent the unpublished Git configuration from undoing the new generation
and its storage quota. Publish the reviewed source changes through the user's
normal workflow, verify the remote revision contains them, then remove only
these maintenance pause annotations and verify reconciliation. Do not unpause
against the old source. This repository prohibits `git push` and `kubectl apply`.

Verify all three Raft voters, test unseal after a follower restart, all 35
SecretStores plus the ClusterSecretStore and 55 ExternalSecrets, a real OIDC
login, and a fresh DNS01 certificate. Remove the recorded recovery Alertmanager
silences after verification; renew only while this recovery remains active.

## Verified outcome

- Three Ready replicas and three Raft voters; a follower was restarted and
  successfully unsealed using the verified encrypted initialization archive.
- All 35 SecretStores, one ClusterSecretStore and 55 ExternalSecrets Ready;
  all 55 rendered target Secrets byte-for-byte identical to the pre-rebuild
  encrypted source snapshot after reconciliation.
- Kubernetes-auth can read its allowed GoDaddy path and is denied an unrelated
  Bitwarden path. Ordinary desktop OIDC login works with the desktop policy;
  Home Assistant, MemPalace and OpenAI consumer profiles fetch their restored
  credentials. Desktop GitHub/mail/personal Harbor credentials remain absent.
- All 46 existing Certificates Ready. A fresh Let's Encrypt staging certificate
  was issued through GoDaddy DNS01; temporary test resources were removed.
- Rebuilt Raft snapshot decrypted identically and its internal SHA256SUMS passed.
  New PVCs retain daily Longhorn backup labels; no faulted/degraded volumes.
- Six recovery tests, Kubernetes manifest schema validation, OpenTofu validation
  and a subsequent no-change plan passed. Recovery silences were removed.
- Strict Argo report remains 92/96: two deliberate maintenance pauses, retained
  old OpenBao resources reported OutOfSync, and an existing image-builder orphan
  warning. Publication and GitOps handover remain separate from runtime recovery.

The user considers the former PKI/SSH mounts unused; they were not recreated.
Current ingress certificates and their Let's Encrypt flow do not need them.
The new unseal material is currently in the encrypted initialization archive;
it has not been copied into Bitwarden. Old Bitwarden unseal entries must not be
mistaken for the new generation's key. Rotate exposed old credentials separately.
