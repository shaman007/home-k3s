# Daily logs check

`metrics/cron-job-logs-check.yaml` runs at 05:00 Europe/Prague. The script in
`metrics/config-map-logs-check-scripts.yaml` reads Loki, builds deterministic
candidate evidence, asks local Ollama for analyst notes, stores the report in
`monitoring/logs-check-report`, and sends email. Argo CD owns the deployment
through `argocd/application-logs-check.yaml`.

The daily window is 24 local wall-clock hours, ending at the current whole hour.
Around daylight saving transitions its elapsed duration may differ. Each category
is queried in non-overlapping one-hour slices with at most 200 lines per slice.
A reached cap or failed query explicitly makes collection incomplete. Counts are
sampled log lines, not total occurrences, incidents, failed jobs, or proof of impact.
No matching lines is not proof that a service is healthy.

Repeated patterns are grouped across pods using namespace, container, and a
normalized message. Sidekiq serialized job arguments are removed before reports,
storage, or model prompts; the job class and final exception remain. The analyst
prompt includes at most 50 distinct patterns per category,
with an explicit warning if more were found. Newly observed sampled patterns
are listed before recurring ones, with at most 50 comparison details in email.
Pattern history is capped at 2,000
patterns; capped history cannot support novelty comparison. Known routine Argo
refreshes, normal unauthenticated MySQL connection closes,
validated SecretStore events, and the specific Longhorn Endpoints deprecation
notice are excluded from analysis. Unfamiliar warnings remain visible and enter
the analyst prompt. Scoped filters remain visible through suppression counts.
Longhorn purge warnings, CoreDNS timeouts, Mastodon mailer failures, and ClamAV
exporter timeouts remain candidates for investigation rather than blanket ignores.

Newly observed/recurring pattern labels require an adjacent previous report with
the same window length and uncapped pattern history. Comparisons describe sampled
evidence; newly observed does not prove a newly occurring fault. Legacy one-hour
reports are not
comparable baselines. A previously observed pattern missing from a sample is not
labelled resolved. This detects pattern novelty, not statistical rate anomalies;
volume changes require complete counts and a longer historical baseline.

Ollama notes are advisory. The deterministic fallback reports current evidence
without inventing API failures or assuming that a model error means its service
is unreachable. Prompts forbid treating log contents as instructions, inferring
user impact from names, or recommending changes without supporting evidence.

Validate locally with:

```sh
python3 -m unittest discover -s tests -p 'test_logs_check*.py' -v
```

Repository validation and read-only replays do not deploy the changes or prove
CronJob resource usage, full model output, report storage, or email delivery for
the new daily window. Verify those after an authorized GitOps deployment.
