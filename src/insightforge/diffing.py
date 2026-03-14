from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path

from .models import TraceRecord


@dataclass(slots=True)
class TraceDiff:
    before: TraceRecord
    after: TraceRecord
    summary_lines: list[str]
    score_delta: float
    added_flags: list[str]
    removed_flags: list[str]


def build_diff(before: TraceRecord, after: TraceRecord) -> TraceDiff:
    before_flags = {_flag_key(flag) for flag in before.bias_flags + before.hallucination_flags}
    after_flags = {_flag_key(flag) for flag in after.bias_flags + after.hallucination_flags}
    score_delta = round(after.confidence_score - before.confidence_score, 2)

    summary_lines = [
        f"Provider: {before.provider} -> {after.provider}",
        f"Model: {before.model_hint} -> {after.model_hint}",
        f"Status: {before.overall_status} -> {after.overall_status}",
        f"Confidence: {before.confidence_score:.2f} -> {after.confidence_score:.2f} ({score_delta:+.2f})",
        f"Exit code: {before.exit_code} -> {after.exit_code}",
        "Prompt changed." if before.prompt != after.prompt else "Prompt unchanged.",
        "Output changed." if before.stdout != after.stdout else "Output unchanged.",
    ]

    return TraceDiff(
        before=before,
        after=after,
        summary_lines=summary_lines,
        score_delta=score_delta,
        added_flags=sorted(after_flags - before_flags),
        removed_flags=sorted(before_flags - after_flags),
    )


def write_diff_html(diff: TraceDiff, destination: Path) -> None:
    before_json = html.escape(json.dumps(diff.before.to_dict(), indent=2))
    after_json = html.escape(json.dumps(diff.after.to_dict(), indent=2))
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InsightForge Diff</title>
  <style>
    :root {{
      --bg: #f3f1ea;
      --panel: #fffdf8;
      --ink: #1d1d1b;
      --muted: #666050;
      --good: #2f6f4f;
      --bad: #aa3d2a;
      --line: #d7d0c2;
    }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Avenir Next", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #ebe4d8 0%, var(--bg) 100%);
    }}
    main {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 28px 18px 64px;
    }}
    .panel {{
      background: rgba(255,253,248,0.92);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 20px;
      box-shadow: 0 20px 70px rgba(52, 42, 28, 0.08);
      margin-bottom: 18px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
    }}
    .chip {{
      border-radius: 999px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      background: var(--panel);
    }}
    .good {{ color: var(--good); }}
    .bad {{ color: var(--bad); }}
    pre {{
      overflow: auto;
      padding: 14px;
      border-radius: 16px;
      background: #1d1d1b;
      color: #f7f0e8;
      font-size: 13px;
    }}
    @media (max-width: 860px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>Trace diff</h1>
      {''.join(f"<p>{html.escape(line)}</p>" for line in diff.summary_lines)}
      <div class="chips">
        {''.join(f"<span class='chip bad'>Added flag: {html.escape(flag)}</span>" for flag in diff.added_flags) or "<span class='chip'>No new flags</span>"}
        {''.join(f"<span class='chip good'>Removed flag: {html.escape(flag)}</span>" for flag in diff.removed_flags) or "<span class='chip'>No removed flags</span>"}
      </div>
    </section>
    <section class="grid">
      <section class="panel">
        <h2>Before</h2>
        <pre>{before_json}</pre>
      </section>
      <section class="panel">
        <h2>After</h2>
        <pre>{after_json}</pre>
      </section>
    </section>
  </main>
</body>
</html>
"""
    destination.write_text(document, encoding="utf-8")


def render_diff_text(diff: TraceDiff) -> str:
    lines = ["InsightForge diff"]
    lines.extend(diff.summary_lines)
    if diff.added_flags:
        lines.append("Added flags: " + ", ".join(diff.added_flags))
    if diff.removed_flags:
        lines.append("Removed flags: " + ", ".join(diff.removed_flags))
    return "\n".join(lines)


def _flag_key(flag) -> str:
    return f"{flag.code}:{flag.severity}:{flag.title}"
