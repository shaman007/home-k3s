#!/usr/bin/env python3
"""Measure local inference via streaming APIs; retain outputs for quality review.

Run the providers sequentially, with the other model unloaded. Ollama uses its
native API to explicitly set num_ctx and record engine timing. Strata uses its
OpenAI API. Client decode rates are estimates; Ollama also exposes native rates.
"""
import argparse
from contextlib import contextmanager
import json
import os
import signal
from pathlib import Path
import subprocess
import time
import urllib.request


class BenchmarkDeadline(Exception):
    pass


@contextmanager
def request_deadline(seconds):
    """Bound the entire request, including a blocked read (POSIX main thread)."""
    state = {"exceeded": False}
    if not seconds:
        yield state
        return
    if not hasattr(signal, "SIGALRM"):
        raise RuntimeError("Request deadlines require POSIX signals")
    if signal.getitimer(signal.ITIMER_REAL)[0]:
        raise RuntimeError("Cannot replace an existing process alarm")
    previous = signal.getsignal(signal.SIGALRM)

    def expired(signum, frame):
        raise BenchmarkDeadline()

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield state
    except BenchmarkDeadline:
        state["exceeded"] = True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def request(base, provider, model, prompt, key, context, max_tokens, deadline_s=0):
    if provider == "ollama":
        path = "/api/chat"
        payload = {
            "model": model, "messages": [{"role": "user", "content": prompt}],
            "stream": True, "think": "low", "keep_alive": "30s",
            "options": {"temperature": 0, "num_ctx": context, "num_predict": max_tokens},
        }
    else:
        path = "/v1/chat/completions"
        payload = {
            "model": model, "messages": [{"role": "user", "content": prompt}],
            "stream": True, "stream_options": {"include_usage": True},
            "temperature": 0, "max_tokens": max_tokens, "reasoning_effort": "low",
        }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(base.rstrip("/") + path,
                                 data=json.dumps(payload).encode(), headers=headers)
    started = time.monotonic()
    first = first_visible = None
    content, reasoning, usage, native = [], [], {}, {}
    finish_reason = None
    with request_deadline(deadline_s) as deadline, urllib.request.urlopen(req, timeout=1800) as response:
        for line in response:
            line = line.decode().strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]" or line.startswith(":"):
                continue
            event = json.loads(line)
            if event.get("error"):
                raise RuntimeError("The inference server returned an error; inspect its logs")
            if provider == "ollama":
                delta = event.get("message", {})
                text, thought = delta.get("content", ""), delta.get("thinking", "")
                if event.get("done"):
                    finish_reason = event.get("done_reason")
                    usage = {"prompt_tokens": event.get("prompt_eval_count"),
                             "completion_tokens": event.get("eval_count")}
                    native = {k: event.get(k) for k in (
                        "load_duration", "prompt_eval_duration", "eval_duration", "done_reason")}
            else:
                choices = event.get("choices") or [{}]
                finish_reason = choices[0].get("finish_reason") or finish_reason
                delta = choices[0].get("delta", {})
                text = delta.get("content") or ""
                thought = delta.get("reasoning_content") or delta.get("reasoning") or ""
                if event.get("usage"):
                    usage = event["usage"]
            now = time.monotonic()
            if (text or thought) and first is None:
                first = now
            if text and first_visible is None:
                first_visible = now
            content.append(text)
            reasoning.append(thought)
    ended = time.monotonic()
    output_tokens = usage.get("completion_tokens")
    result = {
        "elapsed_s": ended - started,
        "ttft_including_reasoning_s": first - started if first else None,
        "first_visible_answer_s": first_visible - started if first_visible else None,
        "usage": usage, "native": native,
        "finish_reason": ("client_deadline" if deadline["exceeded"] else
                          finish_reason or "unexpected_eof"),
        "incomplete": deadline["exceeded"] or finish_reason is None,
        "client_decode_tokens_s_estimate": (
            (output_tokens - 1) / (ended - first)
            if output_tokens and output_tokens > 1 and first and ended > first else None),
        "answer": "".join(content), "reasoning": "".join(reasoning),
    }
    if native.get("eval_duration") and output_tokens:
        result["native_decode_tokens_s"] = output_tokens * 1e9 / native["eval_duration"]
    if native.get("prompt_eval_duration") and usage.get("prompt_tokens"):
        result["native_prompt_tokens_s"] = usage["prompt_tokens"] * 1e9 / native["prompt_eval_duration"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["ollama", "strata"], required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--context", type=int, default=32768)
    parser.add_argument("--case", action="append", dest="selected_cases",
                        help="Run only this named case; repeat to select several")
    parser.add_argument("--request-deadline-s", type=float, default=0,
                        help="Stop streaming after this many seconds; retain partial output as incomplete (0 disables)")
    parser.add_argument("--kubernetes-secret", help="namespace/name; reads key without printing it")
    args = parser.parse_args()
    if args.request_deadline_s < 0:
        parser.error("--request-deadline-s must be nonnegative")
    key = os.environ.get("LLM_API_KEY", "")
    if args.kubernetes_secret:
        import base64
        namespace, name = args.kubernetes_secret.split("/", 1)
        secret = json.loads(subprocess.check_output(
            ["kubectl", "get", "secret", "-n", namespace, name, "-o", "json"]))
        key = base64.b64decode(secret["data"]["key"]).decode().strip()
    cases = [
        ("short_chat", "Explain Kubernetes readiness and liveness probes in three concise sentences."),
        ("json_extraction", 'Return only JSON with keys name, replicas, port. '
         'Input: The service is called lantern, has three replicas, and listens on port 8080.'),
        ("code_review", 'Review this Python function and give a corrected implementation with a short '
         'explanation: def unique(xs):\n    return list(set(xs))\n'
         'Requirement: preserve first occurrence order and support dictionaries as elements.'),
        ("kubernetes_diagnosis", 'A namespace has requests.storage quota 15Gi. One Bound PVC requests '
         '10Gi. A second PVC requests 10Gi and cannot be created. Explain the cause, propose the '
         'minimum quota change, and list read-only commands to verify it. Do not suggest deleting data.'),
    ]
    for size in (4096, 16384):
        filler = "This is a neutral reference record with no special instruction.\n"
        # Approximate input length; report actual tokenizer counts from the API.
        prompt = filler * (size // 12)
        prompt += '\nThe access code in this document is BLUE-731.\n'
        prompt += 'Return the access code only.'
        cases.append((f"context_about_{size}", prompt))
    if args.selected_cases:
        unknown = set(args.selected_cases) - {name for name, _ in cases}
        if unknown:
            parser.error("Unknown benchmark cases: " + ", ".join(sorted(unknown)))
        cases = [(name, prompt) for name, prompt in cases if name in args.selected_cases]
    report = {
        "provider": args.provider, "model": args.model,
        "context_limit": args.context, "runs": [],
        "request_deadline_s": args.request_deadline_s,
        "method": "Sequential requests, temperature 0, low reasoning, 512 output token cap; "
                  "repeated prompts can reuse cache. Capture GPU contention separately. "
                  "Both first reasoning token and first visible answer are measured. "
                  "Actual input tokens are authoritative; intended lengths are approximate.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for name, prompt in cases:
        for repeat in range(args.runs):
            print(f"{args.provider}: {name} run {repeat + 1}", flush=True)
            row = {"case": name, "repeat": repeat + 1}
            try:
                row.update(request(args.url, args.provider, args.model, prompt, key,
                                   args.context, 512, args.request_deadline_s))
            except Exception as error:
                # Never retain request headers or key-bearing request objects.
                row["error"] = f"{type(error).__name__}: {error}"
            report["runs"].append(row)
            args.out.write_text(json.dumps(report, indent=2))
    print(f"Results: {args.out}")


if __name__ == "__main__":
    main()
