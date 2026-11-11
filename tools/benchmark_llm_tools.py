#!/usr/bin/env python3
"""Test a synthetic read-only tool round trip through an OpenAI-compatible API.

No tool is executed against Kubernetes. The supplied quota result is a fixed
fixture. Preserve both responses to review tool choice, arguments and synthesis.
"""

import argparse
from dataclasses import dataclass
import base64
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from benchmark_http import open_response, validate_base_url


TOOL = {
    "type": "function",
    "function": {
        "name": "get_namespace_storage",
        "description": "Read a namespace's storage ResourceQuota usage and hard limit.",
        "parameters": {
            "type": "object",
            "properties": {"namespace": {"type": "string"}},
            "required": ["namespace"],
            "additionalProperties": False,
        },
    },
}
PROMPT = (
    "Use the available read-only tool to check namespace bench-demo. I want to "
    "add a PVC requesting 10Gi. Tell me whether its storage quota permits that "
    "and the minimum total quota needed if it does not. Do not change anything."
)
FIXTURE = {
    "namespace": "bench-demo",
    "requests_storage_used_gib": 10,
    "requests_storage_hard_gib": 15,
}


@dataclass(frozen=True)
class RequestOptions:
    """Keep inference endpoint, model and protocol limits together across both stages."""

    url: str
    model: str
    provider: str
    context: int
    timeout_s: float = 1800


def post(options, messages, key):
    """Send a synthetic tool-call request and return the response and elapsed time."""
    payload = {
        "model": options.model,
        "messages": messages,
        "tools": [TOOL],
        "temperature": 0,
        "reasoning_effort": "low",
        "max_tokens": 1024,
    }
    path = "/v1/chat/completions"
    if options.provider == "ollama":
        path = "/api/chat"
        payload = {
            "model": options.model,
            "messages": messages,
            "tools": [TOOL],
            "stream": False,
            "think": "low",
            "keep_alive": "30s",
            "options": {"temperature": 0, "num_ctx": options.context, "num_predict": 1024},
        }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(
        validate_base_url(options.url) + path, data=json.dumps(payload).encode(), headers=headers
    )
    started = time.monotonic()
    with open_response(req, timeout=options.timeout_s) as response:
        result = json.load(response)
    if result.get("error"):
        raise RuntimeError("Inference API returned an error; inspect server logs")
    return (result, time.monotonic() - started)


def valid_tool_call(calls):
    """Accept exactly the synthetic storage tool and its expected namespace argument."""
    valid = len(calls) == 1 and calls[0]["function"]["name"] == "get_namespace_storage"
    if valid:
        arguments = calls[0]["function"]["arguments"]
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        valid = arguments == {"namespace": "bench-demo"}
    return valid


def run_trial(options, key, repeat):
    """Record selection and synthesis outcomes separately for one synthetic trial."""
    row = {"repeat": repeat + 1}
    stage = "selection"
    started = time.monotonic()
    try:
        messages = [{"role": "user", "content": PROMPT}]
        response, elapsed = post(options, messages, key)
        row.update({"selection_response": response, "selection_seconds": elapsed})
        message = (
            response["message"]
            if options.provider == "ollama"
            else response["choices"][0]["message"]
        )
        calls = message.get("tool_calls") or []
        valid = valid_tool_call(calls)
        row["valid_tool_call"] = valid
        if valid:
            messages.append(
                {k: v for k, v in message.items() if k in ("role", "content", "tool_calls")}
            )
            tool_result = {"role": "tool", "content": json.dumps(FIXTURE)}
            if options.provider == "ollama":
                tool_result["tool_name"] = "get_namespace_storage"
            else:
                tool_result["tool_call_id"] = calls[0]["id"]
            messages.append(tool_result)
            stage = "synthesis"
            response, elapsed = post(options, messages, key)
            row.update({"synthesis_response": response, "synthesis_seconds": elapsed})
            final = (
                response["message"]
                if options.provider == "ollama"
                else response["choices"][0]["message"]
            )
            row["answer"] = final.get("content")
    except Exception as error:
        row["error"] = f"{type(error).__name__}: {error}"
        row["failure_stage"] = stage
    row["elapsed_s"] = time.monotonic() - started
    return row


def main():
    """Test a synthetic read-only tool round trip through an OpenAI-compatible API."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", choices=["openai", "ollama"], default="openai")
    parser.add_argument(
        "--context",
        type=int,
        default=32768,
        help="Ollama context; for OpenAI configure and verify the server separately",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--request-timeout-s",
        type=float,
        default=1800,
        help="Socket inactivity timeout for each non-streaming API call",
    )
    parser.add_argument("--kubernetes-secret", help="namespace/name; key is never printed")
    args = parser.parse_args()
    if args.request_timeout_s <= 0:
        parser.error("--request-timeout-s must be positive")
    try:
        args.url = validate_base_url(args.url)
    except ValueError:
        parser.error("Use an HTTP or HTTPS service URL without credentials or suffixes")
    key = os.environ.get("LLM_API_KEY", "")
    if args.kubernetes_secret:
        namespace, name = args.kubernetes_secret.split("/", 1)
        secret = json.loads(
            subprocess.check_output(
                ["kubectl", "get", "secret", "-n", namespace, name, "-o", "json"]
            )
        )
        key = base64.b64decode(secret["data"]["key"]).decode().strip()
    report = {
        "model": args.model,
        "provider": args.provider,
        "context_limit": args.context if args.provider == "ollama" else None,
        "prompt": PROMPT,
        "fixture": FIXTURE,
        "request_timeout_s": args.request_timeout_s,
        "method": "Synthetic tool selection and result synthesis; no real tool executed. "
        "Temperature zero, low reasoning, 1024 output token cap. "
        "Tool choice is automatic, not forced. Repeats may reuse cache.",
        "runs": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    options = RequestOptions(
        args.url, args.model, args.provider, args.context, args.request_timeout_s
    )
    for repeat in range(args.runs):
        row = run_trial(options, key, repeat)
        report["runs"].append(row)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(
            (
                f"Run {repeat + 1}: valid tool call={row.get('valid_tool_call', False)} error="
                f"{row.get('error', 'none')}"
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
