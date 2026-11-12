#!/usr/bin/env python3
"""Decision regression probes and matched synthetic delegation measurements."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tomllib

from codex_events import parse_codex

from suites import (
    benchmark_tasks,
    grade,
    policy_task,
    integration_tasks,
    grade_fixture,
)

ROOT = Path(__file__).resolve().parents[2]
try:
    from tools.security.probe_commands import (
        CommandTimeout,
        run_command,
        user_executable,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(ROOT))
    from tools.security.probe_commands import (
        CommandTimeout,
        run_command,
        user_executable,
    )
DEFAULT_HELPER = Path.home() / ".codex/skills/strata-delegate/scripts/delegate.py"


def digest(text):
    """Identify exact task inputs without retaining private policy text in reports."""
    return hashlib.sha256(text.encode()).hexdigest()


def codex_command(workspace, schema_path, model, fixture_state=None):
    """No MCP/user config, hooks, shell, plugins, memory, web or agent delegation."""
    args = [
        user_executable("codex"),
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--json",
        "--cd",
        str(workspace),
        "--output-schema",
        str(schema_path),
    ]
    options = {
        "approval_policy": "never",
        "web_search": "disabled",
        "features.shell_tool": False,
        "features.apps": False,
        "features.plugins": False,
        "features.remote_plugin": False,
        "features.memories": False,
        "features.hooks": False,
        "features.multi_agent": False,
        "skills.bundled.enabled": False,
        "skills.include_instructions": False,
        "project_doc_max_bytes": 0,
        "history.persistence": "none",
    }
    if model:
        options["model"] = model
    if fixture_state:
        options["mcp_servers.fixture.command"] = sys.executable
        options["mcp_servers.fixture.args"] = [
            str(Path(__file__).parent / "fixture_server.py"),
            str(fixture_state),
        ]
        for name in (
            "read_file",
            "write_file",
            "deployment_evidence",
            "request_approval",
            "checkpoint",
            "deploy",
        ):
            options[f"mcp_servers.fixture.tools.{name}.approval_mode"] = "approve"
    for key, value in options.items():
        args += ["--config", key + "=" + json.dumps(value)]
    return args + ["-"]


@dataclass(frozen=True)
class InvocationOptions:
    """Keep provider configuration separate from task data."""

    helper: Path
    timeout: float
    max_tokens: int
    model: str | None


def codex_reply(task, work, options):
    """Collect a bounded Codex response and optional virtual fixture evidence."""
    started = time.monotonic()
    schema_path = work / "schema.json"
    schema_path.write_text(json.dumps(task["schema"]), encoding="utf-8")
    state_path = work / "fixture-state.json" if "fixture" in task else None
    if state_path:
        state_path.write_text(json.dumps(task["fixture"]), encoding="utf-8")
    result = run_command(
        codex_command(work, schema_path, options.model, state_path),
        input=task["prompt"],
        capture_output=True,
        text=True,
        timeout=options.timeout,
        check=False,
    )
    if result.returncode:
        return {"status": "error", "error": "codex_exit_" + str(result.returncode)}
    content, usage, tools = parse_codex(
        result.stdout, {"mcp_tool_call"} if state_path else ()
    )
    return {
        "status": "completed",
        "content": content,
        "usage": usage,
        "tools": tools,
        "complete": True,
        "provider_seconds": time.monotonic() - started,
        "model": options.model,
        "fixture_state": json.loads(state_path.read_text(encoding="utf-8"))
        if state_path
        else None,
    }


def strata_reply(task, work, options):
    """Read the existing local worker's exclusive artifact, without running outputs."""
    prompt, artifact = work / "task.txt", work / "response.json"
    prompt.write_text(task["prompt"], encoding="utf-8")
    result = run_command(
        [
            sys.executable,
            str(options.helper),
            "--input",
            str(prompt),
            "--output",
            str(artifact),
            "--max-tokens",
            str(options.max_tokens),
            "--reasoning",
            "none",
            "--timeout",
            str(options.timeout),
        ],
        capture_output=True,
        text=True,
        timeout=options.timeout + 20,
        check=False,
    )
    if result.returncode not in (0, 2) or not artifact.is_file():
        return {"status": "error", "error": "strata_request_failed"}
    response = json.loads(artifact.read_text(encoding="utf-8"))
    if not isinstance(response, dict):
        raise ValueError("Invalid Strata response")
    if not isinstance(response.get("content") or "", str):
        raise ValueError("Invalid Strata content")
    return {
        "status": "completed",
        "content": response.get("content") or "",
        "complete": response.get("complete") is True
        and response.get("finish_reason") == "stop",
        "usage": response.get("usage"),
        "tools": [],
        "provider_seconds": response.get("elapsed_seconds"),
        "model": response.get("model"),
    }


def graded_reply(task, reply, started):
    """Combine independent checks, completion and tool evidence into one result."""
    validation_started = time.monotonic()
    assessment = grade(task, reply["content"])
    if reply.get("fixture_state") is not None:
        assessment["fixture"] = grade_fixture(task, reply["fixture_state"])
        assessment["passed"] = assessment["passed"] and assessment["fixture"]["passed"]
    assessment["passed"] = (
        assessment["passed"] and reply["complete"] and not reply["tools"]
    )
    row = {
        "status": "completed" if reply["complete"] else "incomplete",
        "grade": assessment,
        "model": reply["model"],
        "usage": reply["usage"],
        "unexpected_tools": reply["tools"],
        "response_sha256": digest(reply["content"]),
        "response_bytes": len(reply["content"].encode()),
        "provider_seconds": reply["provider_seconds"],
        "automated_validation_seconds": time.monotonic() - validation_started,
        "elapsed_seconds": time.monotonic() - started,
        "manual_review_seconds": None,
        "repair_seconds": None,
        "accepted_by_reviewer": None,
    }
    if assessment["passed"]:
        row["checked_answer"] = json.loads(reply["content"])
    return row


def invoke(backend, task, options):
    """Run one isolated provider request using explicitly selected settings."""
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="harness-probe-") as temporary:
        provider = codex_reply if backend == "codex" else strata_reply
        reply = provider(task, Path(temporary), options)
        if reply["status"] == "error":
            return {**reply, "elapsed_seconds": time.monotonic() - started}
        return graded_reply(task, reply, started)


def readiness(backend, helper):
    """Check prerequisites once; an unavailable backend is never a passing sample."""
    if backend == "codex":
        return bool(user_executable("codex"))
    if not helper.is_file():
        return False
    result = run_command(
        [sys.executable, str(helper), "--health"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return result.returncode == 0


def summarize(rows):
    "Report measured samples only; token counts from different providers stay separate."
    summary = {}
    for backend in sorted({row["backend"] for row in rows}):
        samples = [row for row in rows if row["backend"] == backend]
        completed = [row for row in samples if row["status"] == "completed"]
        summary[backend] = {
            "scheduled_runs": len(samples),
            "submitted": sum(row["status"] != "unavailable" for row in samples),
            "completed": len(completed),
            "passed_checks": sum(
                row.get("grade", {}).get("passed", False) for row in completed
            ),
            "median_elapsed_seconds": statistics.median(
                row["elapsed_seconds"] for row in completed
            )
            if completed
            else None,
        }
        summary[backend]["tasks"] = {}
        for task in sorted({row["task"] for row in samples if "task" in row}):
            group = [row for row in completed if row["task"] == task]
            summary[backend]["tasks"][task] = {
                "completed": len(group),
                "passed_checks": sum(row["grade"]["passed"] for row in group),
                "median_elapsed_seconds": statistics.median(
                    row["elapsed_seconds"] for row in group
                )
                if group
                else None,
            }
    return summary


def compare(report, reviews):
    "Calculate comparable accepted end-to-end times only with explicit review records."
    if report.get("format_version") != 1 or report.get("mode") != "benchmark":
        raise ValueError("Expected a version 1 benchmark report")
    ids = {row["run_id"] for row in report["runs"]}
    if len(ids) != len(report["runs"]) or not isinstance(reviews, list):
        raise ValueError("Invalid run IDs or review log")
    entries = {}
    for item in reviews:
        key = item["run_id"]
        if (
            key not in ids
            or key in entries
            or not isinstance(item.get("accepted"), bool)
        ):
            raise ValueError("Unknown/duplicate review or missing acceptance")
        for name in ("manual_review_seconds", "repair_seconds"):
            value = item.get(name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError("Review/repair time must be finite and nonnegative")
        entries[key] = item
    pairs = {}
    for row in report["runs"]:
        key = (row["task"], row["repeat"], row["prompt_sha256"])
        review = entries.get(row["run_id"])
        if (
            row["status"] == "completed"
            and row.get("grade", {}).get("passed")
            and review
            and review["accepted"]
        ):
            duration = row["elapsed_seconds"]
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not math.isfinite(duration)
                or duration < 0
            ):
                raise ValueError("Invalid elapsed time")
            pair = pairs.setdefault(key, {})
            if row["backend"] in pair:
                raise ValueError("Duplicate backend/task/repeat")
            pair[row["backend"]] = (
                duration + review["manual_review_seconds"] + review["repair_seconds"]
            )
    matched = [
        {
            "task": key[0],
            "repeat": key[1],
            "codex_seconds": pair["codex"],
            "strata_seconds": pair["strata"],
            "difference_seconds": pair["codex"] - pair["strata"],
        }
        for key, pair in pairs.items()
        if set(pair) == {"codex", "strata"}
    ]
    return {
        "matched_accepted_pairs": matched,
        "measured_time_benefit_available": bool(matched),
        "note": (
            "No token/cost savings inferred. Positive difference means St"
            "rata was faster for this measured task only."
        ),
    }


def positive(value):
    """Parse a finite positive timing or resource limit."""
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be positive and finite")
    return number


def parse_options(argv):
    """Build and validate the public CLI without performing provider work."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["eval", "integration", "benchmark", "compare"])
    parser.add_argument(
        "--backend", choices=["codex", "strata", "both"], default="both"
    )
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--timeout", type=positive, default=180)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--helper", type=Path, default=DEFAULT_HELPER)
    parser.add_argument(
        "--global-policy", type=Path, default=Path.home() / ".codex/AGENTS.md"
    )
    parser.add_argument("--project-policy", type=Path, default=ROOT / "AGENTS.md")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("--out must be a new file")
    if not args.out.parent.is_dir():
        parser.error("--out parent directory must exist")
    if args.runs < 1 or args.max_tokens < 1:
        parser.error("runs and max-tokens must be positive")
    if args.mode == "integration" and args.backend != "codex":
        parser.error("fake-tool integration requires --backend codex")
    if args.mode == "compare" and (not args.report or not args.reviews):
        parser.error("compare requires --report and --reviews")
    return args


def initial_report(args, policy, model, prepared):
    """Describe selected input provenance and measurement limits."""
    return {
        "format_version": 1,
        "mode": args.mode,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "policy_sha256": digest(policy),
        "preparation_seconds": time.monotonic() - prepared,
        "suite_sha256": digest(
            (Path(__file__).parent / "suites.py").read_text(encoding="utf-8")
        ),
        "settings": {
            "codex_model": model,
            "codex_other_model_settings": "isolated defaults",
            "strata_reasoning": "none",
            "strata_max_tokens": args.max_tokens,
            "request_timeout_seconds": args.timeout,
        },
        "scope": (
            (
                "Fake MCP tool-loop on temporary dictionary state; no "
                "host-file or production actions."
            )
            if args.mode == "integration"
            else (
                "Decision-only/synthetic text outputs; no real tool execution "
                "or production actions."
            )
        ),
        "limits": (
            "Different system wrappers; warm/cache effects uncontrolled. "
            "Review/repair time not inferred. No benefit conclusion "
            "without accepted matched review records."
        ),
        "runs": [],
    }


def backend_readiness(backends, helper):
    """Check each backend once, treating unavailable services as missing samples."""
    ready = {}
    for backend in backends:
        try:
            ready[backend] = readiness(backend, helper)
        except (OSError, CommandTimeout):
            ready[backend] = False
    return ready


def sample_result(backend, task, options, ready):
    """Keep one failed or timed-out request from silently becoming a retry."""
    if not ready[backend]:
        return {"status": "unavailable"}
    try:
        return invoke(backend, task, options)
    except CommandTimeout:
        ready[backend] = False
        return {"status": "timeout"}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "error", "error": "provider_or_response_error"}


def provider_samples(args, tasks, options):
    """Yield sequential provider samples with alternating repeat order."""
    backends = ["codex", "strata"] if args.backend == "both" else [args.backend]
    ready = backend_readiness(backends, args.helper)
    for repeat in range(1, args.runs + 1):
        for task in tasks:
            for backend in backends if repeat % 2 else list(reversed(backends)):
                yield {
                    "run_id": f"{backend}:{task['id']}:{repeat}",
                    "backend": backend,
                    "task": task["id"],
                    "repeat": repeat,
                    "prompt_sha256": digest(task["prompt"]),
                    **sample_result(backend, task, options, ready),
                }


def measurements(args):
    """Prepare identical tasks and account for completed samples and unknown reviews."""
    prepared = time.monotonic()
    policy = (
        args.global_policy.read_text(encoding="utf-8")
        + "\nPROJECT POLICY:\n"
        + args.project_policy.read_text(encoding="utf-8")
    )
    tasks = (
        [policy_task(policy)]
        if args.mode == "eval"
        else integration_tasks(policy)
        if args.mode == "integration"
        else benchmark_tasks()
    )
    config = Path.home() / ".codex/config.toml"
    model = (
        tomllib.loads(config.read_text(encoding="utf-8")).get("model")
        if config.is_file()
        else None
    )
    options = InvocationOptions(args.helper, args.timeout, args.max_tokens, model)
    output = initial_report(args, policy, model, prepared)
    output["runs"] = list(provider_samples(args, tasks, options))
    output["summary"] = summarize(output["runs"])
    output["suite_elapsed_seconds"] = time.monotonic() - prepared
    output["review_template"] = [
        {
            "run_id": row["run_id"],
            "manual_review_seconds": None,
            "repair_seconds": None,
            "accepted": None,
        }
        for row in output["runs"]
        if row["status"] == "completed"
    ]
    errors = any(row["status"] != "completed" for row in output["runs"])
    failed = any(not row.get("grade", {}).get("passed") for row in output["runs"])
    return output, 2 if errors else int(failed)


def main(argv=None):
    """Run a validated CLI mode and write one exclusive result artifact."""
    args = parse_options(argv)
    try:
        if args.mode == "compare":
            output = compare(
                json.loads(args.report.read_text(encoding="utf-8")),
                json.loads(args.reviews.read_text(encoding="utf-8")),
            )
            code = 0 if output["measured_time_benefit_available"] else 2
        else:
            output, code = measurements(args)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(output, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(
            json.dumps(
                {
                    "report": str(args.out),
                    "exit_code": code,
                    "summary": output.get(
                        "summary", output.get("measured_time_benefit_available")
                    ),
                }
            )
        )
        return code
    except (OSError, ValueError, KeyError, TypeError):
        print(
            "Unable to complete harness measurement; raw errors/output withheld.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
