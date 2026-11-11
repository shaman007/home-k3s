"""Benchmark clients must retain provider semantics without forwarding credentials."""

import importlib.util
import io
import json
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from contextlib import redirect_stderr
import urllib.error
import urllib.request

from http_fixture import fixture_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def load(name, path):
    """Load a benchmark module without running its command-line entry point."""
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


streaming = load("streaming_benchmark", "tools/benchmark_local_llm.py")
tool_calls = load("tool_benchmark", "tools/benchmark_llm_tools.py")
http = sys.modules["benchmark_http"]


class BenchmarkHttpTests(unittest.TestCase):
    """Exercise both provider protocols, deadlines, validation and real redirect dispatch."""

    def test_invalid_urls_never_reach_transport(self):
        """Reject unsafe schemes, URL credentials and ambiguous URL suffixes."""
        for base in [
            "file:///etc/passwd",
            "ftp://fixture.invalid",
            "http://fixture.invalid:0",
            "https://fixture.invalid:bad",
            "https://user:private@fixture.invalid",
            "https://fixture.invalid?private=true",
            "https://fixture.invalid#private",
        ]:
            with self.subTest(base=base), patch.object(urllib.request, "build_opener") as build:
                with self.assertRaises(ValueError):
                    tool_calls.post(
                        tool_calls.RequestOptions(base, "fixture", "openai", 1024), [], ""
                    )
                build.assert_not_called()

    def test_invalid_cli_url_fails_before_secret_lookup(self):
        """Validate both CLI endpoints before reading Kubernetes credentials or writing reports."""
        for module, provider in [(streaming, "strata"), (tool_calls, "openai")]:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "report.json"
                argv = [
                    "benchmark",
                    "--url",
                    "file:///private",
                    "--provider",
                    provider,
                    "--model",
                    "fixture",
                    "--out",
                    str(output),
                    "--kubernetes-secret",
                    "fixture/key",
                ]
                with (
                    patch("sys.argv", argv),
                    patch.object(module.subprocess, "check_output") as secret,
                    redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    module.main()
                secret.assert_not_called()
                self.assertFalse(output.exists())

    def test_redirects_cannot_forward_bearer_credentials(self):
        """Reject reads and writes through urllib's real redirect dispatcher."""
        marker = secrets.token_urlsafe(18)
        for base in ["https://fixture.invalid", "http://127.0.0.1:18000"]:
            for status in (301, 302, 303, 307, 308):
                for provider in ("openai", "ollama"):
                    path = "/api/chat" if provider == "ollama" else "/v1/chat/completions"
                    url = base + path
                    visits, buffers = [], []
                    with (
                        self.subTest(base=base, status=status, provider=provider),
                        patch.object(
                            urllib.request,
                            "build_opener",
                            side_effect=fixture_opener(url, status, visits, buffers),
                        ),
                    ):
                        with self.assertRaisesRegex(RuntimeError, f"HTTP {status}") as error:
                            tool_calls.post(
                                tool_calls.RequestOptions(base, "fixture", provider, 1024),
                                [],
                                marker,
                            )
                        self.assertEqual(visits, [url])
                        self.assertNotIn(marker, str(error.exception))
                        self.assertTrue(all(body.closed for body in buffers))

    def test_nonstreaming_protocol_and_timeout_are_preserved(self):
        """Keep both tool-selection payloads and explicit timeouts unchanged."""
        marker = secrets.token_urlsafe(18)
        for provider in ("openai", "ollama"):
            opener = MagicMock()
            body = io.BytesIO(b'{"message":{"content":"fixture"}}')
            opener.open.return_value = body
            with patch.object(urllib.request, "build_opener", return_value=opener):
                response, elapsed = tool_calls.post(
                    tool_calls.RequestOptions(
                        "https://fixture.invalid/proxy/", "fixture-model", provider, 2048, 7
                    ),
                    [],
                    marker,
                )
            request = opener.open.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload["model"], "fixture-model")
            self.assertEqual(payload["tools"], [tool_calls.TOOL])
            self.assertEqual(request.get_header("Authorization"), "Bearer " + marker)
            self.assertEqual(opener.open.call_args.kwargs, {"timeout": 7})
            self.assertTrue(request.full_url.startswith("https://fixture.invalid/proxy/"))
            self.assertEqual(response["message"]["content"], "fixture")
            self.assertGreaterEqual(elapsed, 0)
            if provider == "ollama":
                self.assertFalse(payload["stream"])
                self.assertEqual(payload["options"]["num_ctx"], 2048)
            self.assertTrue(body.closed)

    def test_streaming_protocols_keep_completion_and_usage(self):
        """Retain Ollama native timings and OpenAI completion/usage records."""
        events = {
            "ollama": [
                {
                    "message": {"content": "answer", "thinking": "thought"},
                    "done": True,
                    "done_reason": "stop",
                    "eval_count": 2,
                    "prompt_eval_count": 3,
                    "eval_duration": 1000000000,
                }
            ],
            "strata": [
                {
                    "choices": [
                        {
                            "delta": {"content": "answer", "reasoning_content": "thought"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"completion_tokens": 2, "prompt_tokens": 3},
                }
            ],
        }
        for provider, records in events.items():
            data = "\n".join(
                ("data: " if provider == "strata" else "") + json.dumps(v) for v in records
            ).encode()
            body = io.BytesIO(data)
            opener = MagicMock()
            opener.open.return_value = body
            with patch.object(urllib.request, "build_opener", return_value=opener):
                result = streaming.request(
                    streaming.RequestOptions(
                        "http://localhost:8080", provider, "fixture", 1024, 64
                    ),
                    "synthetic",
                    "",
                )
            self.assertEqual(result["answer"], "answer")
            self.assertEqual(result["reasoning"], "thought")
            self.assertEqual(result["usage"]["completion_tokens"], 2)
            self.assertFalse(result["incomplete"])
            self.assertEqual(result["finish_reason"], "stop")
            self.assertTrue(body.closed)

    def test_deadline_still_marks_partial_stream_incomplete(self):
        """Preserve the benchmark's deadline signal through the transport context."""
        response = MagicMock()
        response.__enter__.return_value = response
        response.__iter__.side_effect = streaming.BenchmarkDeadline()
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(urllib.request, "build_opener", return_value=opener):
            result = streaming.request(
                streaming.RequestOptions("http://localhost:8080", "strata", "fixture", 1024, 64, 5),
                "synthetic",
                "",
            )
        self.assertTrue(result["incomplete"])
        self.assertEqual(result["finish_reason"], "client_deadline")
        response.__exit__.assert_called_once()

    def test_error_details_and_response_bodies_are_not_retained(self):
        """Close HTTP failures and suppress private URL, body and transport diagnostics."""
        marker = secrets.token_urlsafe(18)
        body = io.BytesIO(marker.encode())
        for failure in [
            urllib.error.HTTPError("https://fixture.invalid/" + marker, 500, marker, {}, body),
            urllib.error.URLError(marker),
            ValueError(marker),
        ]:
            opener = MagicMock()
            opener.open.side_effect = failure
            with (
                self.subTest(kind=type(failure).__name__),
                patch.object(urllib.request, "build_opener", return_value=opener),
            ):
                with self.assertRaises(RuntimeError) as caught:
                    tool_calls.post(
                        tool_calls.RequestOptions(
                            "https://fixture.invalid", "fixture", "openai", 1024
                        ),
                        [],
                        marker,
                    )
                self.assertNotIn(marker, str(caught.exception))
        self.assertTrue(body.closed)


class ToolTrialTests(unittest.TestCase):
    """Preserve automatic tool selection and stage-specific failure evidence."""

    def test_valid_call_synthesizes_with_provider_specific_result(self):
        """Both providers receive the fixed quota fixture and their expected tool identifier."""
        for provider in ("openai", "ollama"):
            with self.subTest(provider=provider):
                options = tool_calls.RequestOptions(
                    "http://localhost:8080", "fixture", provider, 1024
                )
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "fixture",
                            "function": {
                                "name": "get_namespace_storage",
                                "arguments": '{"namespace":"bench-demo"}',
                            },
                        }
                    ],
                }
                first = (
                    {"message": message}
                    if provider == "ollama"
                    else {"choices": [{"message": message}]}
                )
                final = {"content": "Quota must be at least 20Gi"}
                second = (
                    {"message": final}
                    if provider == "ollama"
                    else {"choices": [{"message": final}]}
                )
                with patch.object(
                    tool_calls, "post", side_effect=[(first, 1), (second, 2)]
                ) as post:
                    row = tool_calls.run_trial(options, "", 0)
                self.assertTrue(row["valid_tool_call"])
                self.assertEqual(row["answer"], final["content"])
                result = post.call_args.args[1][-1]
                self.assertEqual(json.loads(result["content"]), tool_calls.FIXTURE)
                field = "tool_name" if provider == "ollama" else "tool_call_id"
                self.assertEqual(
                    result[field], "get_namespace_storage" if provider == "ollama" else "fixture"
                )

    def test_invalid_namespace_does_not_synthesize(self):
        """A tool call targeting another namespace cannot receive the fixture result."""
        options = tool_calls.RequestOptions("http://localhost:8080", "fixture", "ollama", 1024)
        response = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_namespace_storage",
                            "arguments": {"namespace": "another"},
                        }
                    }
                ]
            }
        }
        with patch.object(tool_calls, "post", return_value=(response, 1)) as post:
            row = tool_calls.run_trial(options, "", 0)
        self.assertFalse(row["valid_tool_call"])
        self.assertNotIn("answer", row)
        post.assert_called_once()

    def test_selection_failure_retains_failure_stage(self):
        """A failed selection is recorded without attempting synthesis."""
        options = tool_calls.RequestOptions("http://localhost:8080", "fixture", "openai", 1024)
        with patch.object(
            tool_calls, "post", side_effect=RuntimeError("synthetic failure")
        ) as post:
            row = tool_calls.run_trial(options, "", 0)
        self.assertEqual(row["failure_stage"], "selection")
        self.assertIn("RuntimeError", row["error"])
        post.assert_called_once()


class StreamingPartialResultTests(unittest.TestCase):
    """Keep partial output and incomplete status when provider streams stop early."""

    def test_deadline_retains_partial_answer_and_closes_response(self):
        """An interrupted read preserves prior text without claiming completion."""
        event = {"choices": [{"delta": {"content": "partial", "reasoning_content": "thought"}}]}

        def events():
            yield ("data: " + json.dumps(event)).encode()
            raise streaming.BenchmarkDeadline()

        response = MagicMock()
        response.__enter__.return_value = response
        response.__iter__.side_effect = events
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(urllib.request, "build_opener", return_value=opener):
            result = streaming.request(
                streaming.RequestOptions("http://localhost:8080", "strata", "fixture", 1024, 64, 5),
                "synthetic",
                "",
            )
        self.assertEqual(result["answer"], "partial")
        self.assertEqual(result["reasoning"], "thought")
        self.assertEqual(result["finish_reason"], "client_deadline")
        self.assertTrue(result["incomplete"])
        response.__exit__.assert_called_once()

    def test_eof_without_completion_marker_remains_incomplete(self):
        """Visible text alone cannot turn an abruptly ended stream into a completed result."""
        event = {"choices": [{"delta": {"content": "partial"}}]}
        body = io.BytesIO(
            ("data: " + json.dumps(event) + "\n\n: keepalive\ndata: [DONE]\n").encode()
        )
        opener = MagicMock()
        opener.open.return_value = body
        with patch.object(urllib.request, "build_opener", return_value=opener):
            result = streaming.request(
                streaming.RequestOptions("http://localhost:8080", "strata", "fixture", 1024, 64),
                "synthetic",
                "",
            )
        self.assertEqual(result["answer"], "partial")
        self.assertEqual(result["finish_reason"], "unexpected_eof")
        self.assertTrue(result["incomplete"])
        self.assertTrue(body.closed)
