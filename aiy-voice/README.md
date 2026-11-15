# AIY Voice Kit: streaming OpenAI Realtime

Live on the Raspberry Pi Zero W at `192.168.1.179`, with Voice Bonnet V2.
The backend runs in namespace `aiy-voice`, using **GPT-Realtime-2.1**, voice Marin,
24 kHz mono PCM16 over WebSockets. The user confirmed a fast spoken reply on
2026-11-15. This supersedes the earlier local Whisper/Codex/Piper prototype.

Hold the big button while speaking, then release. Green: ready; red: recording;
amber: waiting; blue: speaking. Idle microphone samples are discarded immediately
and never sent. A turn is limited to 30 seconds. Presses during a reply are ignored.
Conversation context lasts for the current connection, up to 50 minutes; reconnects
start a fresh conversation. It receives a curated profile and can search MemPalace; it does not inherit the full Codex or ChatGPT history.

## Deployment and recovery

- GitOps image pin: `harbor.andreybondarenko.com/library/aiy-voice:src-a0828776d63799a7@sha256:917d219a0070d31b59e508eed87aae6170318ba281dd370c691d54d14a4e7ed7`.
- Source archive SHA256: `a0828776d63799a738a13150429517c2c17d49e7a796e691a7d08fc18e7ae23d`.
- Builder Job `image-builder/aiy-voice-build-a0828776d63799a7` completed;
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
  audience `vault`, and policy `aiy-voice-api`. It can read those two paths and the MemPalace credential at `kv/mempalace`. Only the fixed search function is exposed to the model; the underlying MemPalace bearer credential is not a separately scoped read-only server token.
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

Run `/tmp/aiy-voice-venv/bin/python -m unittest discover -s tests -p 'test_aiy*.py' -v`
with aiohttp and PyYAML installed (the integration test needs loopback sockets).
Checks cover authentication, audio forwarded before response completion, durable
usage deduplication, cached-token pricing, idle microphone privacy, batched GPIO
edges and deterministic build contexts. Real model access, TLS routing, device
startup and the physical push-to-talk reply were also verified. A full fresh-card
restore and a reboot with the new voice service remain untested.

## Web search and memory

`profile.txt` contains the user-approved short profile: Russian, informal address,
Brno/Europe-Prague default, concise answers, and technical interests. It contains
no credentials or permissions to operate infrastructure. It is loaded on each new
voice session. `search_memory` calls only `mempalace_search` in the `codex` wing,
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
Lookups add latency; ordinary conversation retains streaming speech-to-speech.

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
