# Shared-cluster evaluation — 2026-10-16

Status: GPT-OSS baseline complete; Strata setup still in progress. This is not
yet a comparison or a recommendation to replace GPT-OSS.

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

## Remaining work

Verify Strata model load, authenticated API, actual resource use and existing
service health; run the same comparison prompts and upstream Strata benchmark;
then assess latency, response correctness and coexistence with GPT-OSS.
