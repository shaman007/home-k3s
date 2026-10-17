# Shared-cluster evaluation — October 16–17, 2026

Measurements are complete. **Keep GPT-OSS as the interactive default and run
Strata only on demand.** Strata generated correct short answers but required
17.5–22.6 minutes at about 0.194 tokens/s. Its resident GPU allocation also
degraded GPT-OSS; stopping Strata restored normal GPT-OSS performance.

| Configuration | Warm short-answer total | Decode tokens/s | GPU layers (GPT-OSS) |
| --- | ---: | ---: | ---: |
| Strata IQ2_XS, 12 GiB host cap | 1050.29 s (one warm sample) | 0.194 estimated | n/a |
| GPT-OSS 0.40.6, Strata resident | 17.63 / 12.68 s | 6.87 / 9.15 native | 1/25 |
| GPT-OSS 0.40.6, Strata stopped | 4.00 / 4.03 s | 28.83 / 28.51 native | 25/25 |

These are small deployment usability tests, not a model-quality ranking.
Native Ollama and client-estimated Strata decode rates use different methods.
Strata is stopped live with data and authentication preserved. The prepared
GitOps change sets zero replicas and pins the tested CUDA image; push and
manual sync are still required to make that default durable remotely.

## Original GPT-OSS baseline

GPT-OSS 20B MXFP4 (`9ba9cc2b4e02`) ran through Ollama 0.40.5 on the shared
RTX 4070 Ti, driver 580.178.04, Ryzen 7 5700G. Ollama reported 25/25 layers
offloaded to GPU. Existing services stayed running. Strata was installing
dependencies and had not loaded its model. Exact responses, token counts and
timings are in [gpt-oss.json](gpt-oss.json).

The script sent three sequential requests per case, 32K context, low reasoning,
temperature zero, and a 512-token output limit. Output-token counts include
reasoning. First-visible-answer latency measures when answer text starts.
Repeated prompts reuse model and prompt caches; their low latency must not be
reported as uncached prompt throughput. The two long prompts also share a
repeated prefix. Input sizes below are actual Ollama tokenizer counts.

| Case | Input tokens | First run total seconds | Median total seconds | Median first visible answer seconds | Median native decode tok/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Short explanation | 79 | 59.83 | 4.28 | 0.71 | 26.98 |
| JSON extraction | 98 | 2.75 | 2.22 | 1.65 | 27.74 |
| Code review | 103 | 17.08 | 16.45 | 2.15 | 27.74 |
| Kubernetes diagnosis | 122 | 18.15 | 17.40 | 1.58 | 27.66 |
| Context recall, approximately 4K | 3,835 | 3.71 | 1.03 | 0.92 | 28.42 |
| Context recall, approximately 16K | 15,099 | 15.98 | 1.19 | 1.08 | 27.83 |

All 18 requests completed without API errors or output truncation. The cold
first request includes model loading; warm short-chat totals were 4.28 and
4.08 seconds. These are deployment measurements, not isolated GPU peak speed.

## Initial response review

- Probe explanation correctly distinguishes removing an unready pod from
  Service endpoints from restarting a container after liveness failure.
- JSON extraction returned the requested values in valid JSON on all repeats.
- Both context cases returned `BLUE-731` on every repeat. The code is placed
  near the end, so this checks basic prompt handling, not difficult recall
  across a long document.
- Storage diagnosis correctly requires a 20Gi quota for two 10Gi claims and
  avoids deleting data. It also volunteers a mutating apply command, even
  though verification commands were requested as read-only. The prompt did
  not include this repository's ban on apply.
- Code review preserves order and handles flat dictionaries using
  `frozenset(x.items())`. It fails for dictionary values containing lists or
  nested dictionaries, because those values are unhashable. Its broad claim
  to support dictionaries therefore needs review. Generated code was inspected,
  not executed.

## Scope and limitations

Strata model discovery required authentication (401 without a key), reported
IQ2_XS loaded at 32768 context, and generated two correct complete responses.
The six matched cases were attempted with bounded latency; transport failures
were preserved and retried separately. Timed-out JSON/code/quota/context/tool
requests do not establish eventual answer correctness or unsupported features.
The upstream benchmark was not run as a duplicate suite; these measurements
use the repository comparison clients. No broad quality superiority or fully
saturated simultaneous-generation performance is claimed.

## Supplemental tool check

`tools/benchmark-llm-tools.py` tests automatic selection of the read-only
`get_namespace_storage` function for namespace `bench-demo`, followed by a
synthetic tool result: 10Gi used, 15Gi hard limit, proposed new claim 10Gi.
No actual cluster tool is executed. Correct synthesis requires a **20Gi total
quota**, an increase of 5Gi. Calling the tool alone does not establish correctness.

- [OpenAI API, effective 4K context](gpt-oss-tools-openai-4k.json): all three
  selections and quota answers were correct. Selection took 109.20 seconds
  for the cold first request and 1.29/1.27 seconds warm; result synthesis took
  6.62/4.77/4.57 seconds. The context was observed in Ollama's load log, so these
  timings must not be compared directly to a server configured with 32K context.
- [Native Ollama API, explicit 32K context](gpt-oss-tools-32k.json): the first
  request failed with HTTP 500. The server log shows **CUDA out of memory while
  allocating the 768 MiB KV cache**. The later two requests selected the correct
  tool and correctly answered 20Gi. Selection took 55.09 seconds while reloading
  and 1.67 seconds warm; synthesis took 8.46/7.27 seconds.

The GPU snapshot during the 32K run showed 10,802 MiB used of 12,282 MiB, with
6,574 MiB attributed to Ollama. Other GPU users remained active, and cluster
Strata was still only downloading. This demonstrates that time-sliced GPU
allocation does not guarantee enough free VRAM even before adding Strata's
resident GPU cache. Preserve this failure in the comparison; do not report only
successful retries or assume both models can remain loaded concurrently.

## Strata startup and first inference

The 4096 MiB reserve failed engine validation: auto expert-cache allocation
produced zero slots. Reducing the reserve to 3072 MiB allowed startup with
570 resident experts (0.78 GiB), mmap experts, and 32768-token context.
Unauthenticated `/v1/models` returned 401; authenticated model discovery reported
`qwen3.8-flash-next-iq2_xs` loaded. This alone does not prove usable inference.

The first non-streaming request asked for exactly `Strata inference works`, with
temperature 0, low reasoning, and a 64-token cap. The client timed out at 300
seconds. The server recorded cancellation after 312 seconds and 9 generated
tokens, approximately 0.1 tokens/second, with a 19.3% expert-cache hit rate.
During this request the engine had read about 18.2 GiB from storage and was
observed waiting on disk I/O. No cgroup OOM events were recorded. GPU use was
about 9067 MiB with 2809 MiB free. This failed first request must remain part of
the comparison alongside the completed streaming measurements below.

The [first completed matched streaming run](strata.json) answered the probe
question correctly in three sentences. It took **1355.47 seconds** total,
with first reasoning at 263.54 seconds and first visible answer at 910.76
seconds. Usage was 53 prompt tokens and 212 completion tokens; the client
decode estimate was **0.193 tokens/second**. The engine reported a 31.8%
expert-cache hit rate. This is one completed run, not a median or a complete
suite. GPT-OSS's corresponding
measured warm median was 4.28 seconds total and 26.98 native decode tokens/second
(the decode measurement methods differ).

The second (warm) short-chat run also answered correctly in three sentences:
**1050.29 seconds** total, first reasoning at 23.81 seconds, first visible answer
at 633.09 seconds, and **0.194 tokens/second** estimated decode. It reported
48 of 53 input tokens cached and 200 completion tokens. Prompt reuse reduced
startup substantially, but did not materially improve decode throughput.
The third unbounded repeat was intentionally interrupted while still reasoning
after more than 163 seconds. Its partial response was not saved by the original
client; do not count it as a completed run or a server failure.

A separate full suite now uses a **300-second wall-clock deadline per request**,
with three repeats per case. Deadline-limited rows retain partial output and
are marked `incomplete: true`, `finish_reason: client_deadline`; they must not
be scored as complete answers or assigned a completed decode rate without
final token usage. The two original completed runs above remain unchanged.
The deadline implementation was checked against both a stalled stream after
partial output and a stalled connection-opening call; both were interrupted
and the process alarm was cleared. The bounded suite has finished.
The [first bounded row](strata-bounded.json) ended at 300.000 seconds with
`client_deadline`, retained reasoning, and no visible answer. The server
confirmed cancellation at 306 seconds and the next request started. This is
a client-imposed latency failure, not an engine crash.
All three bounded short-chat repeats reached the deadline without a complete
answer. Only the second produced visible answer text before the limit (at
242.33 seconds), and that answer was partial. All three JSON-extraction repeats
also reached the deadline without a complete answer. All three code-review
repeats reached the deadline without a visible implementation. All three quota
diagnosis repeats also reached the deadline without a visible answer. The
context outcomes and transport retries are recorded below. These extraction
timeouts do not establish whether the model would eventually return valid JSON.

The first approximately 4K request was observed as **4152 actual prompt tokens**.
The engine reached 512 processed tokens at 185 seconds; the client deadline
expired without output at 300 seconds. Server cancellation completed at
**365 seconds**, with zero generated tokens. The next repeat therefore includes
queue time while the previous prefill unwound. Deadline results measure client
latency under this serial service behavior, not isolated prefill throughput or
long-context answer quality.
The second 4K request's server cancellation completed at 378 seconds, again
delaying the next request. At that point the live engine's `/proc/PID/io`
`read_bytes` counter had reached 1,337,143,812,096 bytes (about 1.22 TiB) across
the evaluation since its current startup. This is cumulative storage I/O,
not model size or per-request I/O; OOM counters were still zero.

On resuming October 17, the original bounded client had exited after its local
port-forward lost connection. Its final artifact contains **14 deadline-limited
rows**, one empty/truncated stream for the third 4K repeat, and three 16K
connection-refused errors. The empty stream has no terminal finish reason,
usage, or answer; the original client incorrectly wrote `incomplete: false`.
Treat it as a transport failure, not a completed generation. The client now
marks a missing terminal finish reason `unexpected_eof` and incomplete; targeted
checks cover both empty streams and normal terminal responses. Raw original
results are preserved. Separate connected context retries followed restoration
of the port-forward. Do not interpret the
three connection-refused rows as model inference or context-quality failures.
The separate [connected 4K retry](strata-4k-retry.json) reached its 300-second
deadline without output. Its server-side cancellation completed at 447 seconds.
All context retries used the original CUDA 13.0.0 container. A merged CUDA
13.4.3 image update was not synced or runtime-validated; the prepared manifest
pins the measured 13.0.0 image by its verified digest instead.
All three [connected 16K retries](strata-16k-retry.json) reached 300 seconds
without output. The server observed 16440 prompt tokens. Cancellation of the
first two took 377 and 403 seconds of engine time respectively, adding queue
time to later requests. These are latency-limit failures, not evidence that
the model cannot represent the configured context or answer the recall task.

## GPT-OSS with Strata resident (October 17)

[Three short-chat requests](gpt-oss-coexist.json) completed correctly with
Strata still loaded. Ollama was now **0.40.6**, versus 0.40.5 for the original
baseline; the model ID remained `9ba9cc2b4e02` and context was explicitly 32768.
The first request overlapped Strata's final cancelled prefill draining; warm
requests ran with Strata resident and idle. This is not a saturated simultaneous
generation-throughput test.

| Repeat | Total seconds | First visible seconds | Native decode tokens/s |
| --- | ---: | ---: | ---: |
| Cold | 258.06 | 227.26 | 2.91 |
| Warm 1 | 17.63 | 4.00 | 6.87 |
| Warm 2 | 12.68 | 2.35 | 9.15 |

Ollama logged only **1/25 layers offloaded to GPU**, with 768 MiB non-SWA and
18 MiB SWA KV buffers on CPU; the original baseline logged 25/25 GPU layers.
Total GPU use reached 10790 MiB with 1085 MiB free. Ollama's cgroup recorded
memory-limit reclaim events but zero OOM events or kills. The same-version
control below measures recovery after unloading Strata. Ollama unloaded naturally after its
30-second keep-alive, verified with `ollama ps`, before the Strata tool test.

The October 17 node allocation snapshot shows 59516 MiB of requested RAM
(93% of allocatable), including Strata's 12288 MiB request. Allocatable RAM is
64950100 KiB, leaving only about 3.82 GiB of unreserved scheduling capacity.
A substantially larger guaranteed host cache would therefore crowd existing
reservations; the low observed CPU usage alone does not establish room for it.

## Strata tool test and recovery control (October 17)

All three [synthetic tool attempts](strata-tools.json) timed out during selection
after about 300 seconds, before a tool call was returned. No real cluster tool
was executed. Synthesis was not reached; this establishes a latency failure,
not absence of tool support or incorrect tool arguments.

After the tool tests, Strata was scaled to zero. Its pod disappeared, the 160 GiB
PVC remained Bound, and the API Secret remained present. Total GPU usage fell
to 2835 MiB with 9040 MiB free. All three requests in the
[Ollama 0.40.6 recovery control](gpt-oss-control-0406.json) completed correctly:

| Repeat | Total seconds | First visible seconds | Native decode tokens/s |
| --- | ---: | ---: | ---: |
| Cold | 60.81 | 57.28 | 22.17 |
| Warm 1 | 4.00 | 0.68 | 28.83 |
| Warm 2 | 4.03 | 0.69 | 28.51 |

Ollama restored 25/25 GPU layers and GPU KV buffers (768 MiB plus 18 MiB).
No other workload was scaled. Node memory requests fell from 59516 MiB (93%)
to 47228 MiB (74%), releasing Strata's entire 12 GiB reservation.

During the second bounded request, total GPU usage rose to **10592 MiB** with
**1283 MiB free**. Strata's process reported 6328 MiB; Ollama reported no loaded
model. Cgroup OOM counters remained zero. The startup reserve is therefore not
an ongoing VRAM isolation guarantee: later allocations by other workloads can
consume the remaining margin. The measured coexistence and recovery tests
above confirm that leaving Strata resident materially affects GPT-OSS here.
