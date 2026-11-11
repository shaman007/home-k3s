#!/usr/bin/env python3
"""Measure local inference via streaming APIs; retain outputs for quality review.

Run the providers sequentially, with the other model unloaded. Ollama uses its
native API to explicitly set num_ctx and record engine timing. Strata uses its
OpenAI API. Client decode rates are estimates; Ollama also exposes native rates.
"""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import signal
from pathlib import Path
import time
import urllib.request

from benchmark_http import open_response, validate_base_url, validate_cli_url
from benchmark_credentials import load_api_key


class BenchmarkDeadline(Exception):
    """Signal that a benchmark request exceeded its whole-request deadline."""


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


@dataclass(frozen=True)
class RequestOptions:
    """Pin endpoint, provider and inference limits for a streaming request."""

    base: str
    provider: str
    model: str
    context: int
    max_tokens: int
    deadline_s: float = 0


@dataclass
class StreamTiming:
    """Track start, first reasoning/content and first visible-answer timestamps."""

    started: float
    first: float | None = None
    first_visible: float | None = None


@dataclass
class StreamState:
    """Retain incremental output and provider metrics even when a deadline interrupts reading."""

    timing: StreamTiming
    content: list = field(default_factory=list)
    reasoning: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    native: dict = field(default_factory=dict)
    finish_reason: str | None = None

    def consume(self, provider, event):
        """Update completion, usage, text and timing from one provider event."""
        if event.get("error"):
            raise RuntimeError("The inference server returned an error; inspect its logs")
        if provider == "ollama":
            delta = event.get("message", {})
            text, thought = (delta.get("content", ""), delta.get("thinking", ""))
            if event.get("done"):
                self.finish_reason = event.get("done_reason")
                self.usage = {
                    "prompt_tokens": event.get("prompt_eval_count"),
                    "completion_tokens": event.get("eval_count"),
                }
                self.native = {
                    k: event.get(k)
                    for k in (
                        "load_duration",
                        "prompt_eval_duration",
                        "eval_duration",
                        "done_reason",
                    )
                }
        else:
            choices = event.get("choices") or [{}]
            self.finish_reason = choices[0].get("finish_reason") or self.finish_reason
            delta = choices[0].get("delta", {})
            text = delta.get("content") or ""
            thought = delta.get("reasoning_content") or delta.get("reasoning") or ""
            if event.get("usage"):
                self.usage = event["usage"]
        now = time.monotonic()
        if (text or thought) and self.timing.first is None:
            self.timing.first = now
        if text and self.timing.first_visible is None:
            self.timing.first_visible = now
        self.content.append(text)
        self.reasoning.append(thought)

    def result(self, ended, deadline):
        """Build the original result schema and rates with explicit incomplete status."""
        output_tokens = self.usage.get("completion_tokens")
        result = {
            "elapsed_s": ended - self.timing.started,
            "ttft_including_reasoning_s": self.timing.first - self.timing.started
            if self.timing.first
            else None,
            "first_visible_answer_s": self.timing.first_visible - self.timing.started
            if self.timing.first_visible
            else None,
            "usage": self.usage,
            "native": self.native,
            "finish_reason": "client_deadline"
            if deadline["exceeded"]
            else self.finish_reason or "unexpected_eof",
            "incomplete": deadline["exceeded"] or self.finish_reason is None,
            "client_decode_tokens_s_estimate": (output_tokens - 1) / (ended - self.timing.first)
            if output_tokens
            and output_tokens > 1
            and self.timing.first
            and (ended > self.timing.first)
            else None,
            "answer": "".join(self.content),
            "reasoning": "".join(self.reasoning),
        }
        if self.native.get("eval_duration") and output_tokens:
            result["native_decode_tokens_s"] = (
                output_tokens * 1000000000.0 / self.native["eval_duration"]
            )
        if self.native.get("prompt_eval_duration") and self.usage.get("prompt_tokens"):
            result["native_prompt_tokens_s"] = (
                self.usage["prompt_tokens"] * 1000000000.0 / self.native["prompt_eval_duration"]
            )
        return result


def request(options, prompt, key):
    """Stream an inference response while retaining deadlines and partial completion evidence."""
    if options.provider == "ollama":
        path = "/api/chat"
        payload = {
            "model": options.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "think": "low",
            "keep_alive": "30s",
            "options": {
                "temperature": 0,
                "num_ctx": options.context,
                "num_predict": options.max_tokens,
            },
        }
    else:
        path = "/v1/chat/completions"
        payload = {
            "model": options.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": 0,
            "max_tokens": options.max_tokens,
            "reasoning_effort": "low",
        }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(
        validate_base_url(options.base) + path, data=json.dumps(payload).encode(), headers=headers
    )
    state = StreamState(StreamTiming(time.monotonic()))
    with (
        request_deadline(options.deadline_s) as deadline,
        open_response(req, timeout=1800) as response,
    ):
        for line in response:
            line = line.decode().strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]" or line.startswith(":"):
                continue
            state.consume(options.provider, json.loads(line))
    return state.result(time.monotonic(), deadline)


def main():
    """Measure local inference via streaming APIs; retain outputs for quality review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["ollama", "strata"], required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--context", type=int, default=32768)
    parser.add_argument(
        "--case",
        action="append",
        dest="selected_cases",
        help="Run only this named case; repeat to select several",
    )
    parser.add_argument(
        "--request-deadline-s",
        type=float,
        default=0,
        help=(
            "Stop streaming after this many seconds; retain partial "
            "output as incomplete (0 disables)"
        ),
    )
    parser.add_argument("--kubernetes-secret", help="namespace/name; reads key without printing it")
    args = parser.parse_args()
    if args.request_deadline_s < 0:
        parser.error("--request-deadline-s must be nonnegative")
    args.url = validate_cli_url(parser, args.url)
    key = load_api_key(args.kubernetes_secret)
    cases = [
        (
            "short_chat",
            "Explain Kubernetes readiness and liveness probes in three concise sentences.",
        ),
        (
            "json_extraction",
            "Return only JSON with keys name, replicas, port. "
            "Input: The service is called lantern, has three replicas, and listens on port 8080.",
        ),
        (
            "code_review",
            "Review this Python function and give a corrected implementation with a short "
            "explanation: def unique(xs):\n    return list(set(xs))\n"
            "Requirement: preserve first occurrence order and support dictionaries as elements.",
        ),
        (
            "kubernetes_diagnosis",
            (
                "A namespace has requests.storage quota 15Gi. One Bound PVC "
                "requests 10Gi. A second PVC requests 10Gi and cannot be "
                "created. Explain the cause, propose the minimum quota "
                "change, and list read-only commands to verify it. Do not "
                "suggest deleting data."
            ),
        ),
    ]
    for size in (4096, 16384):
        filler = "This is a neutral reference record with no special instruction.\n"
        # Approximate input length; report actual tokenizer counts from the API.
        prompt = filler * (size // 12)
        prompt += "\nThe access code in this document is BLUE-731.\n"
        prompt += "Return the access code only."
        cases.append((f"context_about_{size}", prompt))
    if args.selected_cases:
        unknown = set(args.selected_cases) - {name for name, _ in cases}
        if unknown:
            parser.error("Unknown benchmark cases: " + ", ".join(sorted(unknown)))
        cases = [(name, prompt) for name, prompt in cases if name in args.selected_cases]
    report = {
        "provider": args.provider,
        "model": args.model,
        "context_limit": args.context,
        "runs": [],
        "request_deadline_s": args.request_deadline_s,
        "method": "Sequential requests, temperature 0, low reasoning, 512 output token cap; "
        "repeated prompts can reuse cache. Capture GPU contention separately. "
        "Both first reasoning token and first visible answer are measured. "
        "Actual input tokens are authoritative; intended lengths are approximate.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    options = RequestOptions(
        args.url, args.provider, args.model, args.context, 512, args.request_deadline_s
    )
    for name, prompt in cases:
        for repeat in range(args.runs):
            print(f"{args.provider}: {name} run {repeat + 1}", flush=True)
            row = {"case": name, "repeat": repeat + 1}
            try:
                row.update(request(options, prompt, key))
            except Exception as error:
                # Exception text can contain private response data or request credentials.
                row["error"] = type(error).__name__
            report["runs"].append(row)
            args.out.write_text(json.dumps(report, indent=2))
    print(f"Results: {args.out}")


if __name__ == "__main__":
    main()
