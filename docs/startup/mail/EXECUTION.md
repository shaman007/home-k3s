# Automatic mail rollout — 32517070

The user published the whole package, then explicitly chose automatic Argo
rollout without a manual mail pause or stopping Postfix. No manual patches,
scaling, rule changes or alert silences were performed during observation.
Longhorn, DNS and external routes were not changed.

## Observed order

Times below use Europe/Prague.

| Container | Started | Result |
| --- | --- | --- |
| valkey | 2026-11-13 23:15:25 CET | Ready |
| rspamd | 2026-11-13 23:15:30 CET | Ready |
| postfix-mail | 2026-11-13 23:15:59 CET | Ready |

Rspamd init completed at 23:15:28 CET; Postfix init completed at 23:15:58 CET.
Both emitted mail_dependencies/ready and exited 0. New Valkey, Rspamd and Postfix
Pods had zero repeat restarts. Dovecot and Unbound kept their original Pods.
Argo mail reached 32517070 Synced/Healthy without conditions; all relevant
Service endpoints were ready.

## Runtime checks

* Mounted Rspamd configuration passed `rspamadm configtest -s`: syntax OK.
* Native configdump confirms CLAMAV_UNAVAILABLE soft reject on CLAM_VIRUS_FAIL,
  honoring reject/soft reject. Postfix postconf confirms milter_default_action
  tempfail and the existing Rspamd, Dovecot SASL and LMTP endpoints.
* Postfix queue count 0. Valkey finished loading, AOF enabled, last AOF write/
  rewrite and RDB statuses OK; observed DBSIZE 43366 (no pre-rollout key-count
  inventory was taken, so this is not an exact data checksum comparison).
* Public SMTP 25/submission 587 STARTTLS and IMAPS 993 negotiated TLS 1.3, certificate
  verification and hostname andreybondarenko.com passed over the existing IPv6
  route. No AUTH, MAIL, message submission or mailbox read was performed.
* No current namespace-mail alerts were returned by Alertmanager. No alert rules
  or silences were modified.

## Startup warnings and local follow-up

Two readiness warnings occurred once at process start: queue-exporter 9154 had
not bound yet, and Rspamd local HTTP ping was not ready. Both recovered without
restarts; no recurring readiness failure was observed.

The Rspamd warning exposed a real diagnostic bug: Perl do-BLOCK/while is not a
loop for last, so a failed --check could emit a fatal last-outside-loop error
instead of clean exit 1. It still failed closed; subsequent healthy checks
succeeded. The local follow-up uses a real while loop and adds a regression for
failed --check and expired --wait. New immutable script ConfigMap references
require a normal Rspamd/Postfix rollout after publication; Valkey/Dovecot and
mail policies do not change. That fix is not yet published/applied.

Native read-only isolated execution of the fixed negative branch through stdin
returns 1 cleanly without modifying the running Pod's script or provider state.
Actual live provider outage, SMTP 4xx failure injection and authenticated end-to-
end message delivery were not tested under the observe-only authorization.

CI for 32517070: Pre-commit, CodeQL and Codacy Security Scan passed; validate-inputs
including repository unit tests passed. Remaining CEL/render validation jobs
were still running when checked; their completion was not awaited.

The approved local follow-up references `mail-startup-a7a2479604c9`, retaining
`mail-startup-e07d94c90561` for existing Pods. It passed all 745 repository tests
(21 skipped), native negative-branch execution, canonical source checks, runtime
contracts, and render/schema/resource checks (178 valid, 10 CRDs skipped, 0 errors;
12 containers checked). It is committed separately for publication, not applied
by a manual patch.

## Functional verification — 5a06a5da, 2026-11-13

Argo `mail` is Synced/Healthy at 5a06a5da with auto-sync/prune/self-heal.
All running mail containers have zero restarts. The corrected readiness script
is deployed; no manual cluster patch or service stop was needed.

A uniquely tagged synthetic inbound message was sent with `swaks` over verified
public SMTP STARTTLS. The first attempt received the configured greylisting
451; the same message was retried after five minutes and accepted as AE58628.
Postfix logged successful LMTP delivery, Dovecot saved it, and a doveadm search
for only its unique Message-ID confirmed it in the final local user's mailbox.
No existing messages were read or deleted. The test message remains in the
mailbox. One additional synthetic fixture message also reached the same own
catch-all during development because the fixture retained production myorigin;
the harness now rewrites myorigin and blocks all nonlocal delivery explicitly.

Run the opt-in isolated test with:

```sh
python3 tools/security/test_mail_runtime.py
```

Requires Podman, OpenSSL, swaks, Python/PyYAML and access to the declared images.
It uses fresh fixture storage, a synthetic password/TLS key, local backend
addresses and a tiny harmless EICAR-only database, never production Secrets or
mail storage. Only loopback IMAP/submission ports are published. It starts and
removes its own containers/volumes; it does not stop production dependencies.
Internet access remains available for normal DNS/Rspamd maps.

Verified against the declared images and Git filter configuration:

| Scenario | Observed result |
| --- | --- |
| Healthy, authenticated SMTP | 250 queued; same Message-ID found through authenticated TLS IMAP |
| EICAR attachment | 554 antivirus rejection; absent from fixture mailbox |
| ClamAV stopped, fresh attachment | 451 temporary rejection; absent from mailbox |
| ClamAV restarted | 250 and IMAP delivery |
| Rspamd stopped | 454 temporary rejection; absent from mailbox |
| Rspamd restarted | 250 and IMAP delivery |

Scope: failure injection was local, not a production network/readiness outage.
Production SMTP AUTH was not tested with a real user's password; fixture AUTH
uses the production Dovecot/Postfix configuration with disposable credentials.
Short text without a scan-eligible MIME part may not invoke ClamAV at all;
ClamAV unavailability is therefore not itself a rejection trigger for every
message. No policy relaxation was made. The scanner-down test uses a unique
attachment to exercise a real scan rather than a cached/omitted scan.
