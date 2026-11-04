# OpenBao capability-drop rollout

Reviewed 2026-11-04. OpenBao 2.7.2 uses Raft with three voters and Shamir sealing
(no auto-unseal), threshold one. The StatefulSet uses OnDelete. Its desired
container already has no escalation and drop ALL; the three original Pods lack
the latter field. Current/update ControllerRevision comparison showed exactly one
changed path: containers/0/securityContext/capabilities. Images, arguments,
volumes, configuration and data are unchanged.

The user authorized replacing one Pod at a time and unsealing each through their
normal secure procedure. The initial read-only check found openbao-0 leader,
openbao-1/openbao-2 followers, all unsealed and matching committed/applied indexes.
Followers openbao-2 and openbao-1 were replaced first and verified unsealed,
Ready and synchronized before the old leader openbao-0 was replaced last. The
user completed unsealing through their secure procedure. All three Pods now use
openbao-df96cc858, are Ready and unsealed, and have matching Raft committed/applied
indexes. Runtime checks on every Pod show UID 100, zero effective and bounding
capabilities, NoNewPrivs=1 and seccomp mode 2. All five Kyverno policies Pass for
each current Pod, and all 34 SecretStores/ClusterSecretStores are Ready.

The VAULT_UNSEAL value loaded from this host's startup configuration was rejected
with a stored-key decryption/authentication mismatch. Do not assume it matches a
user's current terminal variable. No credential was logged or stored, and failed
attempts were stopped. A fixed local forward can also collide with an existing
forward; for API diagnostics allocate an ephemeral local port and verify it came
from the owned pod-specific forwarding process before sending any credential.
The existing legacy agent_registry mount warning remains documented in the
migration notes and was not changed as part of this rollout.

Target the replacement directly; a shared ingress/service can hit another Pod:

```sh
kubectl exec -it -n openbao openbao-2 -- bao operator unseal \
  -address=https://127.0.0.1:8200 -tls-server-name=openbao.openbao.svc
```

Enter the unseal key only at the CLI's hidden prompt. Do not pass it as a command
argument, put it in chat, save it in this repository, or print tokens. The installed
CA is supplied through the Pod's BAO_CACERT setting. TLS server-name selection
preserves verification rather than bypassing it.

If unseal fails, inspect only the redacted error and sealing progress. Do not
initialize, rekey, change seal configuration, delete a PVC, remove Raft membership
or restart another voter. A root API token is not an unseal key.

After unseal, require Pod Ready, sealed=false, Raft committed/applied indexes
caught up with the leader, membership still three voters, and no fresh errors.
Then replace the other follower, repeat the same unseal/verification gate, and
replace the leader last with quorum available on the two updated voters. Never
advance just because a Pod is Running. Keep OnDelete to preserve operator control.
Finally verify all three Pods use the update revision/drop ALL, current-Pod
Kyverno capability results pass, the authenticated read-only Raft checks succeed,
and OpenBao-backed consumers remain healthy. No exception is planned for OpenBao.
