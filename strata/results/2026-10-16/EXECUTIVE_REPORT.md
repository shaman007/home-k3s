# Executive report: Strata on the shared Kubernetes GPU

Evaluation: October 16–17, 2026

**Recommendation: retain GPT-OSS as the default and keep Strata available only on demand.**

Strata successfully ran Qwen3.8-Flash-Next IQ2_XS on the RTX 4070 Ti and generated
correct short answers. However, performance under the shared cluster's resource
budget was unsuitable for interactive use. Keeping Strata loaded also materially
slowed the existing GPT-OSS service.

| Measured configuration | Warm short-answer completion | Decode rate |
| --- | ---: | ---: |
| Strata, 12 GiB host-memory limit | 17.5 minutes, one completed warm sample | ~0.19 tokens/s, estimated |
| GPT-OSS with Strata resident | 12.7–17.6 seconds | 6.9–9.2 tokens/s, native |
| GPT-OSS after Strata stopped | ~4 seconds | 28.5–28.8 tokens/s, native |

The two completed Strata answers took 17.5 and 22.6 minutes. The warm answer
started displaying after 10.6 minutes. Matched tests covering chat, JSON
extraction, code review, quota diagnosis, and approximately 4K/16K context did
not complete within a five-minute request limit. Three synthetic tool-selection
attempts also timed out before returning a call.

The principal operational constraint was memory and storage pressure. Strata
used roughly 6 GiB of GPU memory and reserved 12 GiB of host RAM. Its small
expert cache caused heavy disk reads; the engine recorded more than 1 TiB of
cumulative storage reads during evaluation. Node RAM reservations reached 93%,
leaving about 3.8 GiB unreserved, so a substantially larger guaranteed cache
would compete with existing workloads.

With Strata resident, GPT-OSS offloaded only 1 of 25 layers to the GPU and kept
its context cache on CPU. After Strata stopped, the same Ollama 0.40.6 runtime
returned to 25 of 25 GPU layers and normal warm response speed. This recovery
control supports the conclusion that shared GPU capacity was a material cause
of the degradation. Other GPU-service pods remained Ready without restarts;
their full application performance was not benchmarked.

**Operational outcome:** Strata is deployed for on-demand evaluation, defaults
to zero replicas, and retains its model data and API authentication. The tested
CUDA image is pinned by digest. The final pushed revision was verified Synced
and Healthy in Argo, and all CI workflows passed.

**Decision limits:** this evaluation supports a deployment decision, not a
general model-quality ranking. Strata's timed-out tasks leave eventual answer
quality and tool support unverified. Token-rate measurement methods differ,
and the models generated different amounts of reasoning. Connection failures
were preserved separately and affected context tests were retried. No hardware
purchase is justified by these measurements alone; further work should use a
separate resource budget and explicitly test memory/cache and storage changes.

Detailed methods, raw results, failures, and caveats:
[technical evaluation](README.md).
