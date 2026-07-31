# Keycloak realm configuration

`master-realm.snapshot.json` is a normalized, non-secret snapshot of the live
`master` realm. It captures realm security/session/email settings, eleven custom
OIDC clients and protocol mappers, the `admin` realm role, and five groups.
Generated database UUIDs and API access metadata were removed.

The file is deliberately stored below this subdirectory so the Keycloak Argo CD
application does not treat it as a Kubernetes manifest. It is a reviewable
disaster-recovery source, not an automatically reconciled resource: importing
or updating the existing `master` realm is destructive if done blindly.

Client secrets, SMTP credentials, users, passwords, OTP/WebAuthn credentials,
sessions, consents, group membership, and temporary admin clients are excluded.
Restore those from Vault or a database backup. New confidential clients created
from the snapshot receive new secrets, which must then be written to the
corresponding Vault entries used by External Secrets.
