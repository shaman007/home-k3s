# Strata evaluation on the shared RTX 4070 Ti

Pinned Strata revision: `296b59d2f73c8f04a805df29c2fa97655adace78`.
Model: original Qwen3.8-Flash-Next IQ2_XS, context 32,768, images disabled.

The GPU node has about 62 GiB allocatable RAM and currently reserves about
48 GiB for existing pods. This deployment requests and caps RAM at 12 GiB,
caps CPU at four cores, uses best-effort priority, and explicitly selects
`--low-ram mmap`. The generic `on` setting is insufficient: setup sees host
RAM and may select a resident expert cache exceeding the container limit.
File cache is charged to the container; cold reads and cache eviction may
substantially reduce inference speed. This is an evaluation of the deployment
under a restricted resource budget, not full-RAM peak performance. Successful
inference alongside GPT-OSS and effects on other services remain unverified.

`--vram-reserve-mib 3072` leaves a margin for the other GPU consumers. A 4096 MiB
reserve failed engine validation because no expert-cache slots remained; the
3072 MiB setting starts successfully and has generated complete responses;
coexistence validation is still pending. Kubernetes
GPU time slicing does not isolate VRAM or guarantee throughput. GPT-OSS may need
CPU offload while Strata is loaded. Compare models sequentially, stopping Strata
for the GPT-OSS baseline, then test coexistence separately before recommending
leaving both models loaded. Existing services must not be scaled down implicitly.

The 160 GiB Longhorn PVC holds source, environment, downloaded files and model
packs. The current StorageClass has two replicas: 320 GiB of logical replica
capacity. Downloads are approximately 70 GB, plus dependencies and prepared
data. The namespace quota allows exactly this claim. Deleting the PVC deletes
the model data under the current StorageClass reclaim policy. There is no
configured backup of this reproducible model cache.

## Deployment

Live resource creation requires approval under the repository instructions.
Create namespace `strata`, then a Secret `strata-api-key` with a random `key`
entry without printing or writing its value to repository files. Create the
rendered Kustomize bundle. Do not use `kubectl apply` (forbidden here).
The Argo Application uses manual sync during evaluation; do not create it
against unpublished files. No commit, push or Argo sync is part of preparation.

The CUDA development image supplies the toolkit needed to compile the Linux
engine when no prebuilt release asset exists. Bootstrap installs Python and
the C++ compiler; source and built artifacts persist with the model cache.
The container bootstraps dependencies and downloads the pinned source and model
on its first start. It reuses `/data` on subsequent starts. No liveness probe
interrupts the potentially long first download. Runtime authentication config
is ephemeral; the Kubernetes Secret is the source of the key. Never copy that
runtime config into reports. Validate the actual loaded model and a generated
answer, not just the readiness endpoint.

Internal OpenAI API: `http://strata.strata.svc.cluster.local:8080/v1`.
Ingress is limited to Strata and Open WebUI namespaces, with API authentication.
No public Ingress is created. For local access, use
`kubectl port-forward -n strata service/strata 18080:8080` and an API client
that reads the key securely. Open WebUI connection is a separate configuration
change and must preserve existing providers.

## Benchmark and usability review

Run upstream `tools/strata_bench.py --url http://127.0.0.1:8080 --runs 3`
inside the deployment with its key supplied through `STRATA_KEY`, not command
arguments. Save reports under `/data/results` and export sanitized reports.
Review report fields for secrets before exporting.

The repository comparison tool uses Ollama's native API so its 32K context is
explicit rather than relying on server defaults. For Strata it uses the OpenAI
streaming API. Forward Ollama to localhost:11434 and Strata to localhost:18080;
run each provider separately:

```sh
python3 tools/benchmark-local-llm.py --provider ollama \
  --url http://127.0.0.1:11434 --model gpt-oss:20b \
  --out /tmp/llm-comparison/gpt-oss.json
python3 tools/benchmark-local-llm.py --provider strata \
  --url http://127.0.0.1:18080 --model strata \
  --kubernetes-secret strata/strata-api-key \
  --request-deadline-s 300 \
  --out /tmp/llm-comparison/strata-bounded.json
```

Compare first visible answer latency, full response latency, actual prompt and
output tokens, decode rate, peak RAM/VRAM, and effects on existing services.
Report cold first runs separately from repeated prompts. Check extraction JSON,
order-preserving code with dictionary inputs, safe storage-quota diagnosis, and
long-context recall. Retain responses for manual review. These small tasks are
usability checks, not a broad model-quality benchmark or proof of tool-calling
reliability. The [2026-10-16 baseline report](results/2026-10-16/README.md)
contains measured GPT-OSS results and two completed Strata short-chat responses.
Strata took 22.6 minutes cold and 17.5 minutes warm, with about 0.194 tokens/s
decode; these results do not support replacing GPT-OSS for interactive use.
The remaining comparison cases and coexistence checks are still in progress.
The bounded suite retains partial responses with `incomplete: true` and
`finish_reason: client_deadline`; do not score them as complete answers.
This optional deadline requires POSIX signals and runs in the main thread.

For a synthetic tool round trip, use `tools/benchmark-llm-tools.py` with the same
URL, model and secret options. Add `--provider ollama --context 32768` for the
Ollama baseline; the default OpenAI-compatible mode uses the context configured
on the server. This test supplies fixture data and never executes a real cluster
tool. Review the final quota answer as well as the tool arguments. Retain API
failures and cold-load timings alongside successful warm runs.
Use `--request-timeout-s 300` to bound socket inactivity on each non-streaming
tool-selection or synthesis request; reports identify the stage of any failure.
