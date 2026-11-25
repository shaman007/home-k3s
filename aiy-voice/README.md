# AIY Voice Kit: streaming OpenAI Realtime

Live on the Raspberry Pi Zero W at `192.168.1.179`, with Voice Bonnet V2.
The backend runs in namespace `aiy-voice`, using **GPT-Realtime-2.1**, voice Marin,
24 kHz mono PCM16 to/from OpenAI. The Pi requests an Opus mono 24 kbit/s CBR
downlink (`opus-24k-v1`); microphone upload remains PCM16. A fast reply was confirmed on
2026-11-15. This supersedes the earlier local Whisper/Codex/Piper prototype.

Hold the big button while speaking, then release. Green: ready; red: recording;
amber: waiting; blue: speaking. Idle microphone samples are discarded immediately
and never sent. A turn is limited to 30 seconds. Presses during a reply are ignored.
Playback starts with three seconds of audio held in Pi RAM. Shorter replies start
as soon as they finish downloading. Before starvation, playback drains cleanly and
refills a larger reserve: one extra second per stall, up to eight seconds. After a
stable reply of at least ten seconds, the reserve decreases by half a second,
down to 1.5 seconds. Adaptation lasts for the connection; reconnects start at three.
Amber indicates buffering; blue indicates playback. Audio is not written to disk;
each turn is limited to five minutes of PCM, including already played audio.
Failed responses stop playback and discard remaining audio. The independent
WebSocket receiver stays active during playback to handle heartbeats and commands.
Opus uses 20 ms frames grouped in WebSocket messages, each prefixed by a two-byte
big-endian packet length. The server encodes in-process with `libopus0`; the Pi
decodes to PCM before the adaptive reserve. Final padding preserves codec lookahead.
A synthetic 30-second stream used 93,062 bytes instead of 1,440,000 PCM bytes
(15.5x smaller); Pi Zero W decoding took 2.39 seconds (about 8% of one core at real
time). Both codec states reset at the next turn. No extra audio is stored.
Old clients retain PCM; new clients accept PCM from old servers, allowing either
side to be rolled back independently. The dotfiles client installer installs
`libopus0` and copies `opus_audio.py`; the server image and CI install the library too.
Connections last up to 50 minutes. Compact conversation context and lasting facts
are saved through MemPalace MCP and restored on reconnect. It receives a curated
profile and can search MemPalace; it does not inherit the full Codex or ChatGPT history.

The live persistent-memory implementation, validation and rollback procedure are
described in [conversation memory](../docs/aiy-conversation-memory.md).

Multiple actions in one voice turn, editable reminders and temporary pauses are
described in [multiple actions](../docs/aiy-multiple-actions.md). The backend, prompt
catalog and Pi modules must remain on compatible versions.

## Deployment and recovery

- GitOps image pin: `harbor.andreybondarenko.com/library/aiy-voice:src-1a721740cb4c2558@sha256:be57ca6cc57f9d4b320635cc14656cffb384bc073331787466eeb949898828a1`.
- Source archive SHA256: `1a721740cb4c25585abad35a4ef913c96097ee2ee71e50d8eecc69be439d30ad`.
- Builder Job `image-builder/aiy-voice-build-1a721740cb4c2558` completed;
  Cosign sign and verification succeeded in the managed builder.
- `prepare_build.py` renders a deterministic source ConfigMap and one-off Job
  using the established privileged Podman/Cosign builder. It does not contact
  external systems. The runtime is a small unprivileged, read-only Python image.
- `kubernetes/resources.yaml` owns the application, certificate, dedicated source
  IP middleware, NetworkPolicy, PVC and External Secrets resources.
  `traefik/network-policy-traefik-allow-egress-aiy-voice.yaml` allows only ingress-to-AIY TCP/8080 and belongs to the existing `traefik-network-policy` Argo application.
- The live resources were created directly for this authorized deployment.
  GitOps source is `argocd/application-aiy-voice.yaml`, discovered by the root
  `argocd-applications` app after publication to `main`. The `applications` project
  explicitly permits only the new AIY namespace. The application renders only
  `kubernetes/resources.yaml`, excluding OpenBao restore sources. Self-heal and
  pruning are enabled; namespace and ledger PVC have `Prune=false,Delete=false`.
  PVC size changes are ignored to preserve manual expansions. Source publication
  and live Argo adoption must be verified separately from a local commit.
- API key: OpenBao KV v2 `kv/openai/voicekit`, property `api_key`.
  Device token: `kv/aiy-voice/device`, property `bearer_token`.
  ESO role `external-secrets-aiy-voice` uses `vault-auth` in this namespace,
  audience `vault`, and policy `external-secrets-aiy-voice`. It can read those two paths and the MemPalace credential at `kv/mempalace`. Only the fixed search function is exposed to the model; the underlying MemPalace bearer credential is not a separately scoped read-only server token.
  Policy and role restore sources are beside the manifests.
- ESO uses the existing verified internal OpenBao endpoint and CA bundle;
  it does not disable certificate verification. Secret values are never in Git.
  Environment-based runtime credentials require a controlled pod replacement
  after a key rotation; ESO refresh alone does not replace environment variables.
- Ledger SQLite is on the 1 GiB Longhorn PVC `aiy-voice-usage`. Preserve this PVC
  during upgrades and recovery. Audio and transcripts are not stored or logged
  by the application. Provider-side data handling follows the API account policy.
- Pi installation/recovery source is in
  `/home/shaman007/git/dotfiles/hosts/aiy/`: `install-voice-client.sh`, systemd unit,
  credential launcher, driver restore and audio configuration.
  The only credential on the Pi is the device token export in its untracked
  `~/.zshrc` (0600); the launcher parses it without executing shell configuration.
  The OpenAI API key stays on the backend.

Internal DNS is `aiy-voice.int.andreybondarenko.com -> 192.168.30.210`.
The existing `traefik` ingress is used because the private LoadBalancer excludes
Wi-Fi sources. AIY's own middleware permits only the Pi `/32`, infrastructure and
WireGuard administrative networks; every voice/usage request also requires its
device bearer token. Shared ingress allowlists were not widened.
UniFi DNS, DHCP reservation for `b8:27:eb:f8:51:94`, and a device-specific HTTPS
firewall policy are tracked locally in `unifi-infra/aiy-voice-*.tf`.
The new policy pins current controller zone UUIDs: historical zone state in that
repository no longer matches the controller. No unrelated zone resources were
recreated or changed.

## Usage and money

The authenticated `GET /v1/usage` endpoint returns provider-reported response IDs,
timestamps, model, status, first-audio latency and token counts, without speech.
Alternatively read the ledger in the pod with SQLite URI `mode=ro`.
Pipe a `{"responses": [...]}` export to `python3 aiy-voice/usage_cost.py`.
The calculator uses the official 2026-11-15 GPT-Realtime-2.1 rates per million:
text input $4, text output $24, audio input $32, audio output $64, cached text/audio
input $0.40. Reasoning tokens are included in text output, not charged twice.
Source: https://developers.openai.com/api/docs/pricing . These calculated amounts
are usage estimates, not an independently retrieved billing receipt.

The onboarding grant issued $46 of API credit, expiring 2026-11-29 18:46:43 UTC.
The first short voice API smoke consumed $0.003788 by actual token counts.
At 2026-11-15 16:11:33 UTC, five completed physical-device replies plus that smoke
totalled **$0.1046432** (about 10.5 US cents), calculated from provider usage.
Device replies reached the client in roughly 1.0 seconds after button release.
`usage-result.json` is a dated snapshot, not a continuously updated bill.
The earlier onboarding Responses haiku did not retain usage, so its exact cost
is not included in this ledger. The project key cannot access organization Costs
(HTTP 403); the exact grant balance and cash billing require Platform billing.
No purchases or credit top-ups were performed. API usage can continue on purchased
balance if available after free credits expire or are exhausted.

## Validation

### Slow delivery to the Pi

On 2026-11-25 a 29-second reply took 42.2 seconds to arrive, starving streamed
playback. Direct SSH transfers were also slow: 512 KiB took 22.5 seconds including
SSH startup. Disabling Wi-Fi power saving did not help and was reverted. Reconnecting
the existing `aiy-wifi` NetworkManager profile restored the receive link rate during
traffic from 1 to 72.2 Mbit/s; the same SSH transfer took 7.4 seconds. After restarting
the voice client, a comparable 29.25-second reply arrived in 8.6 seconds.
This isolates the observed bottleneck to the Pi Wi-Fi connection; the precise
driver/access-point cause and recurrence are not established.

If this recurs, compare `audio_receive_gap_ms` and `reply_ready` in the client
journal, TCP statistics (`ss -tin dst 192.168.30.210`) and Wi-Fi rate during an
active transfer (`/usr/sbin/iw dev wlan0 link`). An idle rate alone is inconclusive.
For authorized recovery, schedule both disconnect and reconnect on the Pi so loss
of SSH cannot prevent reconnection:

```sh
sudo systemd-run --unit=aiy-wifi-reconnect --collect --on-active=2s \
  /bin/sh -c 'nmcli connection down aiy-wifi; nmcli connection up aiy-wifi'
```

Reconnect over SSH, restart `aiy-voice.service` to refresh its TCP connection, and
verify the ready log and a physical spoken reply. This changes no saved Wi-Fi
settings. Adaptive buffering is independent of this Wi-Fi recovery procedure.

### Automated checks

Run `/tmp/aiy-voice-venv/bin/python -m unittest discover -s tests -p 'test_aiy*.py' -v`
with aiohttp and PyYAML installed (the integration test needs loopback sockets).
Checks cover authentication, audio forwarded before response completion, durable
usage deduplication, cached-token pricing, idle microphone privacy, batched GPIO
edges and deterministic build contexts. Real model access, TLS routing, device
startup and the physical push-to-talk reply were also verified. A full fresh-card
restore and a reboot with the new voice service remain untested.

## Web search and memory

Model-facing texts live only in OpenBao KV v2 `kv/aiy-voice/prompts`, field
`bundle` (JSON, schema version 1). This includes the voice profile, time/snapshot
labels, web lookup and reminder-speech instructions, memory notice, and all tool
and parameter descriptions. `aiy-voice-prompts` ExternalSecret projects the bundle
as `/run/aiy-prompts/bundle.json` through a read-only Secret volume (not `subPath`).
No production texts are included in the source archive, image or test fixtures.
Tool names, argument schemas, bounds and allowlists remain in code; bundle edits
can change only existing description slots. Missing/invalid bundles fail startup
and readiness with generic errors, without logging contents or using a fallback.

To update texts, edit only the existing bundle through an authorized OpenBao
consumer or UI; never print or commit it. Keep `version`, text keys, `{now}` in the
web-search template, and the tool/path catalog intact. ESO refreshes every minute;
Kubernetes Secret-volume projection adds its normal propagation delay. Before every push-to-talk turn, the existing provider connection reloads one
coherent bundle and updates both instructions and tool descriptions in place.
No reconnect, client restart or image rebuild is needed, and conversation history
is preserved. Search/speech calls also reload the bundle; existing cached reminder
audio is unchanged. Roll back wording using a retained OpenBao KV version through the
same consumer. Back up/recover this KV path with OpenBao; Git alone cannot restore
its contents. Runtime pod access remains a privileged way to read mounted texts.
Earlier Git history/images may still contain historical texts; this migration
does not rewrite history or delete registry artifacts.

The existing ESO role uses policy `external-secrets-aiy-voice`; its restore ACL
is `kubernetes/openbao-policy.hcl` and the role definition is
`kubernetes/openbao-role.json`. Keep the existing credential paths and add only
`read` for the prompt path. The application itself gets no OpenBao token.

`search_memory` calls only `mempalace_search` in the `codex` wing,
at most four bounded excerpts per lookup. The fixed MCP endpoint uses verified
TLS. Results are historical context, never executable instructions or proof of
current state. No memory write/delete tools are exposed; found memories are not persisted
by AIY or automatically sent to web search. Recognizable secret formats are
redacted defensively; MemPalace itself must remain free of secrets.

`search_web` uses hosted Responses web search with GPT-6 Luna, current local time,
Brno default and live web access. Realtime chooses it for changing facts, then
speaks the grounded result. Normal pages require citations; hosted `weather:`
results can have no URL annotation and are identified as weather-feed provenance
without fabricating a link. Tool results are bounded; each voice turn permits one
lookup round with at most two calls per round and two rounds per voice turn. Failed lookups are reported honestly.
Lookups add latency; spoken replies use adaptive buffering on the Pi.

The usage ledger also records the lookup model, actual search-call count and
cache writes. GPT-6 Luna short-context Standard rates per million tokens: input
$0.10, output $0.50, cached input $0.01, 30m writes $0.125, 12h writes $0.25;
hosted search costs $0.01 per search action. `usage_cost.py` includes both.
Fresh-card restore and reboot with the new service are still untested.

Final validation on 2026-11-15: the deployed final image selected `search_web`
for the synthetic Brno weather question and `search_memory` for a prior-project
question, received results, and generated audio for each. Memory returned four
matches without printing their contents. The device reconnected automatically.
The scoped rollout silence `e1bafc0e-0b8c-4a1b-84bb-33b1c2e2283d` matched only
`namespace=aiy-voice`, was due to expire at 16:30:49 UTC and was removed/verified
expired at 16:26 UTC. No unrelated alerts were silenced.

Usage snapshot at 2026-11-15T16:26:35.832865+00:00: $0.819531300 across 36 recorded provider responses, including voice and search tests. Earlier figures above are dated intermediate snapshots. The onboarding haiku remains excluded; billing balance is unverified.

## Local appliance resources

Button lighting follows `Europe/Prague` time, including daylight saving:
06:00–23:30 uses 18.75% of the original RGB levels; 23:30–00:00 uses the
minimum nonzero level (1) on the dominant color channels; 00:00–06:00 is
completely dark, including recording, playback, errors and reminder effects.
The Pi client refreshes idle lighting every second without a backend request.
Audio and reminder scheduling are unaffected. The existing dotfiles
`hosts/aiy/install-voice-client.sh` installs this policy with `pi_client.py`.

Voice functions: `blink_light`, `set_timer`, `list_timers`, `cancel_timer`,
`device_status`, `set_volume`, and `adjust_volume`. Only the built-in Voice Bonnet button RGB LED is exposed; no
arbitrary GPIO numbers, shell commands, paths, containers or infrastructure
operations can be selected by the model. Blink effects last1–30seconds.
Status includes Pi temperature/uptime and selected backend clock/process metrics.

The Pi acknowledges each command before the assistant reports success.
Acknowledged command results are kept in the PVC ledger's `device_commands`
table. Executable timer state lives on the Pi in
`/var/lib/aiy-voice/timers.sqlite3` (systemd StateDirectory, mode0700), so an
already-set timer survives backend/network loss and client restarts/reboots.
It rings on next service start if the Pi was powered off when due. New timers
require a live voice/backend connection. At most16 active timers, durations
1second–7days; completed timers are retained locally. Command IDs are idempotent.

A due timer flashes yellow and emits three locally generated beeps without
OpenAI calls. Speech and alarms serialize through the same ALSA output. Preserve
the Pi state directory and PVC when restoring/upgrading. No new root or generic
GPIO permissions are granted; the existing narrow LED/audio permissions suffice.
The dotfiles installer now copies `local_resources.py` beside `pi_client.py`.

GitOps adoption of the base release8ef156b7 was confirmed Synced/Healthy for
`aiy-voice` and `traefik-network-policy`. The next release also sets SecretStore
refreshInterval900 as required by CI runtime contracts.

## Voice volume

`set_volume(level)` sets0–100percent; `adjust_volume(delta)` applies relative
percentage points. “Сделай тише” defaults to-10, “громче” to+10. `device_status`
returns the actual mixer percentage. Only the Voice Bonnet Speaker control can
be changed. Actual ALSA steps can round percentages (requested40 ->41%).
The requested level persists in the Pi SQLite preferences table and is restored
on each service start; it affects both speech and local alarms. The initial
user-requested reduction changed raw25/39 (64%) to16/39 (41%). No privilege
expansion or model-selected mixer/command names are involved.

The voice-volume release is source archive
`32193503a39a4f6e34b6d9982956851cf3759b1999cbfb4811d76466ec3cfe61`,
image digest `sha256:86ad5ffe786e625014b21b7ae7d8b391825c9cb1fc6aa54c079d1673c0494dda`.
Its managed builder Job ended successfully and verified the Cosign signature.
The first attempt hit an init-only Cosign128Mi memory limit before building;
the verified retry uses256Mi for that one-off init, without changing shared
CronJob settings. The Pi client and quiet volume are already installed;
GitOps publication of the image-pin commit activates voice volume tools.
CI now installs AIY dependencies alongside existing validation dependencies;
its explicit ingress-class tests retain all private-route constraints and
check AIY's exact device/admin source allowlist as a single scoped exception.

## Home Assistant over MCP

`home_assistant.py` calls the existing verified HTTPS endpoint
`https://ha.andreybondarenko.com/api/mcp/assist` with the official MCP SDK.
Only the19 inspected Assist tools in `homeassistant_tools.json` are exposed to
Realtime as `ha_*` functions. These operate on entities already exposed to Assist;
no administrative configuration, generic service-call or arbitrary MCP tool API
is exposed. The server must acknowledge an action before the assistant reports
success. Tool results are data, never instructions. Local speaker volume and
timers remain distinct from HA media-player volume and HA timers.

The existing HOME_ASSISTANT_TOKEN was stored in OpenBao
`kv/aiy-voice/homeassistant`, property `token`. ESO reads this dedicated path and
projects only the environment reference into the backend; it never reaches the
Pi or model context. The underlying existing token may be privileged; the bridge
uses only the fixed Assist URL and tool allowlist. No HA configuration or exposure
settings were changed. Scope reference:
https://www.home-assistant.io/integrations/mcp_server/ .

The CPU limit was removed to comply with the repository resource policy; CPU
request50m and memory limit256Mi remain. Before publication, the full render of
96Argo applications passed the296-container resource check,47-template restricted
context check and complete structural schema validation.807 unit tests passed
on the CI Python version (16 expected skips). The HA endpoint discovery and a
read-only light-state query succeeded with the existing credential. No physical
home-device actions were executed as part of that integration test.

## Daily reminders with completion for today

`create_daily_reminder`, `list_daily_reminders`, `acknowledge_reminder` and
`disable_daily_reminder` manage independent daily tasks on the Pi. No example
schedules are installed automatically. Each task has a start time, exclusive end
time (normally22:00), repeat interval (normally30minutes), and explicit completion
phrase. Dates and day boundaries use Europe/Prague, including DST. Unless an
explicit first date is supplied, creation after the start time begins tomorrow.

Completion is a persisted `(reminder_id, local_date)` fact, independent of whether
the first alert has sounded. An early affirmative statement closes that task for
today; tomorrow it reopens. Other tasks remain pending. A repeated confirmation
is idempotent. Ambiguous phrases require clarification, including when one of
several matching tasks is already complete. Semantic equivalents can be passed
with the identified task ID and the entire verbatim user statement; local guards
reject questions, negations, future plans and non-today statements. These guards
supplement the voice model's task identification; they are not a full language
understanding engine. A button press alone never acknowledges a task. Permanent
cancellation is a separate explicit operation.

Short speech is generated once with the existing Realtime voice, checked against
the requested text and cached as PCM in the Pi state database (maximum15seconds
per task, maximum16 enabled tasks). Generation usage enters the existing cost
ledger. Repeats play locally without new API requests, even when disconnected;
creating or confirming reminders requires the voice/backend connection. Preserve
the state directory during upgrades. Offline or powered-off periods produce no
backlog burst: at most the current slot plays after recovery within the active
window. At22:00 pending tasks wait until the next day's start.

Reminders wait while a conversation is active. Pressing the button interrupts
local reminder playback before microphone capture; interruption silences that
slot but does not mark the task complete. The installer must copy `reminders.py`
alongside `local_resources.py` and `pi_client.py`. Existing timers, volume settings
and acknowledgements share the preserved SQLite database without destructive
migration. New task behavior is covered by simulated-clock, restart, multiple-task,
early-confirmation, quiet-hours, DST and playback tests; deployment/physical voice
acceptance must be verified separately for each release.

The reminder release archive is
`713d3e318e62dc1dc038f028f49268e4762839de3542699e9989bac5f368a196`;
the immutable image pin and managed-build verification are in `build-result.json`.
The live API accepted all32 tools and generated a validated1.85second neutral
phrase; its separately recorded test usage cost about$0.00294. This test used no
real schedule. All12 reminder tests also passed on the Pi. Before installing
the new client, its previous Python files and a consistent SQLite backup were
saved under `/var/lib/aiy-voice/backup-713d3e318e62dc1d` (private directory).
To roll back the client, restore those two Python files and restart its service;
the additive reminder tables can remain. Do not replace the current SQLite database
with the backup after new user actions, because doing so loses later state.
Backend activation still requires publication of the GitOps image-pin commit
and a verified Argo rollout; a completed build or Pi update alone does not enable
the new voice tools.

### Live acceptance correction: fresh state on every press

Physical testing confirmed two one-minute repeat slots without acknowledgement.
It also exposed a false verbal confirmation: the voice session still remembered
an empty list after a test task was added on the Pi, and no acknowledgement tool
was called. The test task was disabled; verbal reassurance alone was not treated
as successful completion.

The client now includes the current enabled reminder metadata and today's flags
in every `start` event. The backend validates and whitelists at most16 tasks,
excludes cached audio/extra fields, and refreshes session instructions before
committing the user's audio. Fresh state explicitly replaces stale conversation
facts, including an old empty list. Task names remain data, not instructions.
The model must call `acknowledge_reminder` for an unambiguous affirmative completion
and report success only after its result. Ambiguous tasks still need clarification.

Regressions cover state changes between presses, bounded metadata, and propagation
through the actual gateway protocol.821 unit tests passed (16 expected skips).
Two live API checks produced the correct acknowledgement call for «сделал»,
including with stale «no reminders» conversation history; combined test usage was
about$0.034472. The signed corrected image is recorded in `build-result.json`.
The physical early-acknowledgement/silence test must be repeated after GitOps
publication of this correction; the earlier failed test is not acceptance proof.

The corrected early-voice test saved an actual acknowledgement at22:59:42 on
2026-11-15 before the23:02 start. No playback was delivered at23:02 or23:03,
and the neutral schedule was automatically disabled. A further careful physical
repeat was requested; do not confuse instrumental evidence with a new listening
confirmation. No user schedules were created.

## Feminine self-reference

The voice profile uses feminine Russian self-reference (for example «отметила»),
while preserving the user's original gender and verbatim completion quote such
as «сделал». A live Realtime check confirmed the exact acknowledgement arguments
and a feminine reply after a synthetic successful tool result. The voice and
reminder scheduler are unchanged; publication of the new image pin activates the
wording change through GitOps.

## Weekdays and stable random displacement

The existing `create_daily_reminder` tool also accepts `weekdays` (Monday=0,
Sunday=6) and `jitter_minutes` (0–10). A non-empty weekday set is required;
all seven days means daily. Nominal slots remain on the start/repeat grid.
Each slot, including the first, receives its own plus/minus displacement; with
30minute repeats and10minute jitter, successive actual gaps can be10–50minutes.
The first slot may precede the nominal start by10minutes. No slot starts at or
after the exclusive end time. Repeat must exceed twice jitter to preserve order.

The additive Pi `reminder_recurrence` table stores weekday masks, jitter and a
random per-task seed. SHA256 of seed/date/slot deterministically selects each
offset; polling, reconnects and restarts do not redraw it. The bounded in-memory
slot cache avoids repeated hashing on the Pi Zero. Existing rows without a policy
remain exact daily reminders. Recovery still emits only the latest overdue slot,
not a backlog. Weekly completion applies only to the scheduled local weekday/date;
the next occurrence is computed across quiet days and DST. Completion before the
first displaced slot suppresses that day's whole task. Ambiguity requires task
clarification; a fixed spoken password is not required. Full verbatim evidence and
negative/future guards remain in force, with affirmative passive/adjective forms
supported for free-form task identification.

Runtime schedules, their speech and completion facts stay in the appliance's
private SQLite state, never in Git. Back up that state before upgrades. Do not
downgrade to an older engine while weekly/jitter policies remain enabled: an old
engine ignores this additional policy table. Restore matching code and preserve
the current database; disable affected tasks before any deliberate downgrade.
828 CI-version unit tests (16 expected skips) and19 isolated Pi reminder tests
passed, including weekdays, early weekly completion, jitter deadlines, stability,
legacy state and recovery. Live API checks accepted the extended schema and
identified free-form completions; unclear wording can still require clarification.

## Persistent notes and changing reminder intervals

`save_note` stores an explicitly requested user note in the Pi's existing
`/var/lib/aiy-voice/timers.sqlite3`, in the additive `voice_notes` table.
`list_notes` retrieves it after reconnects, backend container replacements and
appliance restarts. This is explicit note storage, not automatic conversation
history. The device acknowledges only after committing; preserve and back up
this database during recovery. Notes and device command results are private
runtime data; never put credentials in notes. Backend device-command audit rows
on the existing PVC also contain successful `list_notes` results.

`update_reminder_interval` changes an existing task's repeat interval without
recreating the task, cached speech, weekday/jitter policy or completion records.
Elapsed slots on the new grid are skipped so changing frequency does not play an
extra catch-up signal. The default requested repeat interval is now60minutes;
existing tasks require an explicit update. The existing ±10minute jitter remains,
so an hourly nominal grid can produce actual gaps of40–80minutes.

Both backend tool definitions and Pi `local_resources.py` / `reminders.py` must
be updated together before these tools can work. The existing dotfiles installer
already copies both Pi modules; no new packages or service configuration are
required. On2026-11-16 the Pi modules were installed and all four enabled reminders were
changed in place to60minutes; all six existing completion records were preserved,
and SQLite integrity was verified. A coherent code/database backup is at
`/var/lib/aiy-voice/backup-hourly-notes-20261116`. The Pi passed a save/reopen/read
note test in an isolated temporary database; no user note was created.
All52 AIY tests pass, including stale-playback protection during interval changes.
Backend release `3d148120` is installed: Argo CD verified Synced/Healthy at the
exact revision, runtime readiness returned200, all three new tools and the hourly
default are present, and the physical Pi reconnected. The signed image digest and
source label were independently checked with skopeo. A neutral test note in the
actual Pi database survived a client service restart and was then removed without
changing user notes. New commands still need a physical voice acceptance test.
The Python base stays at the deployed 3.12.16: the earlier unactivated 3.15 base
cannot build pinned aiohttp without gcc.
Home Assistant's Shopping list is independent and is preserved.
