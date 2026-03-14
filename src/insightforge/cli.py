from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

from .analyzer import build_trace
from .config import load_config
from .diffing import build_diff, render_diff_text, write_diff_html
from .migrations import CURRENT_DB_SCHEMA_VERSION, get_schema_version, migrate_storage
from .policy import evaluate_policies
from .providers import ProviderError, get_provider
from .redaction import apply_redaction
from .renderer import write_html, write_json
from .store import index_trace, load_trace, load_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insightforge",
        description="Wrap AI interactions and emit audit-friendly traces.",
    )
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    wrap = subparsers.add_parser("wrap", help="Run a command and generate JSON + HTML traces.")
    wrap.add_argument("model", help="Model or tool hint, e.g. claude, grok, local-llm")
    wrap.add_argument("prompt", help="The prompt or intent associated with the wrapped run")
    wrap.add_argument(
        "--cmd",
        required=True,
        help="Shell command to execute, quoted as a single string",
    )
    wrap.add_argument(
        "--out",
        default="traces/latest",
        help="Output prefix for generated files, without extension",
    )

    ask = subparsers.add_parser("ask", help="Prompt a supported provider and generate JSON + HTML traces.")
    ask.add_argument("provider", help="Provider name: mock, openai, anthropic")
    ask.add_argument("model", help="Model name understood by the provider")
    ask.add_argument("prompt", help="User prompt to send to the provider")
    ask.add_argument(
        "--system",
        default="",
        help="Optional system prompt or instruction block",
    )
    ask.add_argument(
        "--out",
        default="traces/latest",
        help="Output prefix for generated files, without extension",
    )

    list_cmd = subparsers.add_parser("list", help="List indexed traces from the local registry.")
    list_cmd.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of traces to display",
    )

    diff = subparsers.add_parser("diff", help="Compare two saved traces by path or trace id.")
    diff.add_argument("before", help="Older trace path or trace id")
    diff.add_argument("after", help="Newer trace path or trace id")
    diff.add_argument(
        "--out",
        default="traces/diff-latest.html",
        help="HTML destination for the diff report",
    )

    schema = subparsers.add_parser("schema-version", help="Show the current storage schema version.")
    schema.add_argument(
        "--expected",
        action="store_true",
        help="Also print the expected application schema version",
    )

    subparsers.add_parser("migrate", help="Run storage migrations to the latest schema version.")
    return parser


def _cap_output(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[InsightForge truncated persisted output]"


def _finalize_trace(trace, app_config):
    trace.policy_results, trace.overall_status = evaluate_policies(trace, app_config.policy)
    return apply_redaction(trace, app_config.redaction)


def _write_trace_artifacts(args: argparse.Namespace, trace, app_config) -> None:
    out_prefix = Path(args.out)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = out_prefix.with_suffix(".json")
    html_path = out_prefix.with_suffix(".html")
    write_json(trace, json_path)
    write_html(trace, html_path)
    index_trace(trace, json_path, html_path, app_config.storage)

    print(f"InsightForge trace captured for {trace.model_hint}")
    print(f"Trace ID: {trace.trace_id}")
    print(f"Provider: {trace.provider}")
    print(f"Status: {trace.overall_status}")
    print(f"Confidence score: {trace.confidence_score:.2f}")
    print(f"JSON: {json_path}")
    print(f"HTML: {html_path}")

    for flag in trace.bias_flags + trace.hallucination_flags:
        print(f"[{flag.severity}] {flag.title}: {flag.recommendation}")
    for result in trace.policy_results:
        print(f"[policy:{result.status}] {result.policy_id}: {result.message}")


def run_wrap(args: argparse.Namespace) -> int:
    app_config = load_config()
    command = shlex.split(args.cmd)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    trace = build_trace(
        prompt=args.prompt,
        command=command,
        model_hint=args.model,
        provider="shell",
        stdout=_cap_output(completed.stdout, app_config.policy.max_output_chars),
        stderr=_cap_output(completed.stderr, app_config.policy.max_output_chars),
        exit_code=completed.returncode,
        metadata={"mode": "wrapped shell command"},
    )
    trace = _finalize_trace(trace, app_config)

    _write_trace_artifacts(args, trace, app_config)

    return completed.returncode


def run_ask(args: argparse.Namespace) -> int:
    app_config = load_config()
    try:
        provider = get_provider(args.provider)
        response = provider.generate(model=args.model, prompt=args.prompt, system_prompt=args.system)
        stdout = response.output_text
        stderr = ""
        exit_code = 0
        metadata = response.metadata
        provenance_notes = response.provenance
    except ProviderError as exc:
        stdout = ""
        stderr = str(exc)
        exit_code = 1
        metadata = {"transport": "provider call failed"}
        provenance_notes = []

    trace = build_trace(
        prompt=args.prompt,
        system_prompt=args.system,
        command=[args.provider, args.model],
        model_hint=args.model,
        provider=args.provider,
        stdout=_cap_output(stdout, app_config.policy.max_output_chars),
        stderr=_cap_output(stderr, app_config.policy.max_output_chars),
        exit_code=exit_code,
        metadata=metadata,
        provenance_notes=provenance_notes,
    )
    trace = _finalize_trace(trace, app_config)

    _write_trace_artifacts(args, trace, app_config)
    print(stdout if stdout else stderr)
    return exit_code


def run_list(args: argparse.Namespace) -> int:
    app_config = load_config()
    entries = load_registry(app_config.storage, max(1, args.limit))
    if not entries:
        print("No traces indexed yet.")
        return 0

    for entry in entries:
        print(
            f"{entry['trace_id']} | {entry['captured_at']} | {entry['provider']} | "
            f"{entry['model_hint']} | status={entry['overall_status']} | "
            f"score={entry['confidence_score']:.2f} | {entry['json_path']}"
        )
    return 0


def run_diff(args: argparse.Namespace) -> int:
    app_config = load_config()
    before = load_trace(args.before, app_config.storage)
    after = load_trace(args.after, app_config.storage)
    diff = build_diff(before, after)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_diff_html(diff, out_path)

    print(render_diff_text(diff))
    print(f"HTML: {out_path}")
    return 0


def run_schema_version(args: argparse.Namespace) -> int:
    app_config = load_config()
    current = get_schema_version(app_config.storage)
    print(f"Current schema version: {current}")
    if args.expected:
        print(f"Expected schema version: {CURRENT_DB_SCHEMA_VERSION}")
    return 0


def run_migrate(_: argparse.Namespace) -> int:
    app_config = load_config()
    before, after = migrate_storage(app_config.storage)
    print(f"Migrated storage schema: {before} -> {after}")
    print(f"SQLite: {app_config.storage.sqlite_path}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command_name == "wrap":
        return run_wrap(args)
    if args.command_name == "ask":
        return run_ask(args)
    if args.command_name == "list":
        return run_list(args)
    if args.command_name == "diff":
        return run_diff(args)
    if args.command_name == "schema-version":
        return run_schema_version(args)
    if args.command_name == "migrate":
        return run_migrate(args)

    parser.error("Unknown command")
    return 2
