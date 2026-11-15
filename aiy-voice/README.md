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

- Runtime image: `harbor.andreybondarenko.com/library/aiy-voice:src-0eebad117a7bf983@sha256:725440234ce96a90d171cc83462c44a858a3fbb4f4fa8c29de6d4f6bd99ccfac`.
- Source archive SHA256: `0eebad117a7bf98389d896c22fb90f15ddd2e98a89e3497fc4e04e0648a0bd29`.
- Builder Job `image-builder/aiy-voice-build-0eebad117a7bf983` completed;
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
current state. No write/delete tools are exposed; found memories are not persisted
by AIY or automatically sent to web search. Recognizable secret formats are
redacted defensively; MemPalace itself must remain free of secrets.

`search_web` uses hosted Responses web search with GPT-6 Luna, current local time,
Brno default and live web access. Realtime chooses it for changing facts, then
speaks the grounded result. Normal pages require citations; hosted `weather:`
results can have no URL annotation and are identified as weather-feed provenance
without fabricating a link. Tool results are bounded; each voice turn permits one
lookup round with at most two calls. Failed lookups are reported honestly.
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
