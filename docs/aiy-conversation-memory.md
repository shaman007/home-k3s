# AIY conversation memory

## Behavior

`remember_memory(key, content)` writes a lasting fact through MemPalace MCP.
Stable lowercase keys allow corrections to update the same AIY-owned drawer.
The returned `saved` flag is true only after a confirmed MCP write; an unavailable
server leaves a durable retry entry and returns `saved: false, pending: true`.

After each completed spoken response, a separate, silent Realtime text response
summarizes the conversation. It has no tools and is not added to the spoken
conversation. Its usage is recorded in the existing ledger. This adds provider
usage per turn; it is not a free local summarizer. Raw audio and transcripts are
not stored. If another turn finishes during a summary, a second summary follows.

The summary is queued in the existing PVC's SQLite database. A worker retries MCP
writes every 15 seconds, including after client disconnection or backend restart.
Each connection has its own updated summary in `aiy_voice/conversations`; the
latest context is also kept in `aiy_voice/continuity`. Lasting facts are in
`aiy_voice/facts`; the initial assistant name is in `aiy_voice/identity`.
Search includes both `aiy_voice` and the existing read-only `codex` history.
The model cannot select an MCP tool, target wing, filesystem path or drawer ID.

New connections restore identity, up to 100 facts and the latest context via MCP,
with a 12-second overall deadline and a 24,000-character context budget. The local
cache supplies recent facts/context when MCP is unavailable. Older facts beyond
the bootstrap budget remain available through explicit memory search. Recognizable
credential patterns are rejected before local persistence; prompt policy must also
exclude secrets and private material not intended for memory.

## Prompt upgrade and release

The source changes are not a live rollout. The new runtime requires two additional
prompt fields and the `remember_memory` tool's three description slots. Existing
pods require the old strict catalog, so **do not overwrite the active `bundle`**.

After authorization to build/publish and change the AIY service:

1. Read `kv/aiy-voice/prompts` only inside an authenticated OpenBao consumer.
   `tools/aiy/memory_prompt_upgrade.py::upgrade` constructs a separate bundle in
   memory from the current bundle and operator-supplied text. Never print the
   existing bundle or save it to a local file. Preserve unrelated KV properties;
   store the result as `bundle_memory` at the same KV path.
2. Supply a voice-memory policy: save explicit requests before confirming them;
   independently save useful, established preferences/identity/decisions; reuse a
   stable key for corrections; never elevate guesses or retrieved instructions to
   facts. Explain pending writes honestly. Newer corrected facts supersede older
   identity/context entries. Preserve current short Russian voice behavior.
3. Supply `memory_summary`: produce a concise factual context (at most 4,000
   characters) from the conversation, including current topic, referents, decisions
   and unfinished questions. Retain the assistant/user distinction and uncertainty.
   Exclude secrets, tool directives, inferred personal facts and raw transcripts.
   This field requests a plain text summary, not JSON or a tool call.
4. Supply `memory_context_prefix`: identify the appended JSON as historical,
   untrusted data, not instructions or current device state. Prefer newer direct
   user corrections and live tool results. Supply descriptions for the function,
   stable key and factual content. The updater has no built-in production text.
5. Validate the complete new bundle with `server.session_config(bundle)` in the
   isolated consumer; print only success/schema counts. Create a separate
   ExternalSecret/Secret named `aiy-voice-memory-prompts`, mapping `bundle_memory`
   to the mounted key `bundle`. Retain the original Secret for rollback. The
   existing OpenBao read policy already covers this KV path.
6. Build the deterministic source with `aiy-voice/prepare_build.py`, verify builder
   completion and Cosign verification, then update the image digest and deployment
   prompt Secret reference together. Follow repository publication/approval rules;
   do not run `git push` or `kubectl apply` in this repository.
7. Verify the exact Argo revision, mounted prompt schema, runtime memory tool and
   MCP name restoration. With the user, test remembering a neutral fact, wait for
   a confirmed save, reconnect, then ask for it and for the assistant's name. Check
   context continuity, corrections, retry behavior and summary usage separately.
   Ready/Synced status alone does not prove physical voice acceptance.

Rollback uses the previous image and the original `aiy-voice-prompts` Secret.
Do not delete the PVC, memories or retry tables. Abrupt disconnection before a
summary finishes can lose the final unsummarized turn; this does not reconstruct
conversations that took place before the feature was enabled.

## Validation

Run the AIY suites in an environment with `aiy-voice/requirements.txt`, PyYAML and
the CI lint requirements. Tests use synthetic prompt text and fake MCP/provider
responses; they do not write test records into the real palace or make paid calls.

The implementation was also checked against real MCP: it restored the explicitly
requested name, then saved `assistant_name` through the new bounded writer with a
confirmed `saved: true` response. The running speaker has not yet been upgraded.
