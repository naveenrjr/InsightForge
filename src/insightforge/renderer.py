from __future__ import annotations

import html
import json
from pathlib import Path

from .models import TraceRecord


def write_json(trace: TraceRecord, destination: Path) -> None:
    destination.write_text(json.dumps(trace.to_dict(), indent=2), encoding="utf-8")


def _render_flags(trace: TraceRecord) -> str:
    items = trace.bias_flags + trace.hallucination_flags
    if not items:
        return "<p class='empty'>No heuristic flags were raised.</p>"

    rendered = []
    for flag in items:
        rendered.append(
            (
                "<article class='flag'>"
                f"<h3>{html.escape(flag.title)}</h3>"
                f"<p><strong>Severity:</strong> {html.escape(flag.severity)}</p>"
                f"<p>{html.escape(flag.evidence)}</p>"
                f"<p><strong>Recommendation:</strong> {html.escape(flag.recommendation)}</p>"
                "</article>"
            )
        )
    return "".join(rendered)


def _render_nodes(trace: TraceRecord) -> str:
    rendered = []
    for node in trace.nodes:
        score = "n/a" if node.score is None else f"{node.score:.2f}"
        rendered.append(
            (
                "<article class='node'>"
                f"<div class='node-kind'>{html.escape(node.kind)}</div>"
                f"<h3>{html.escape(node.label)}</h3>"
                f"<p>{html.escape(node.detail)}</p>"
                f"<div class='node-score'>score: {score}</div>"
                "</article>"
            )
        )
    return "".join(rendered)


def _render_list_items(items: list[str]) -> str:
    if not items:
        return "<p class='empty'>None recorded.</p>"
    return "".join(f"<article class='node'><p>{html.escape(item)}</p></article>" for item in items)


def _render_metadata(trace: TraceRecord) -> str:
    if not trace.metadata:
        return "<p class='empty'>No provider metadata recorded.</p>"
    return "".join(
        f"<article class='node'><h3>{html.escape(key)}</h3><p>{html.escape(value)}</p></article>"
        for key, value in trace.metadata.items()
    )


def _render_policy_results(trace: TraceRecord) -> str:
    if not trace.policy_results:
        return "<p class='empty'>No policy results recorded.</p>"
    return "".join(
        (
            "<article class='node'>"
            f"<div class='node-kind'>{html.escape(result.status)}</div>"
            f"<h3>{html.escape(result.policy_id)}</h3>"
            f"<p>{html.escape(result.message)}</p>"
            "</article>"
        )
        for result in trace.policy_results
    )


def _render_evidence(trace: TraceRecord) -> str:
    if not trace.evidence_checks:
        return "<p class='empty'>No cited URLs were detected for verification.</p>"
    return "".join(
        (
            "<article class='node'>"
            f"<div class='node-kind'>{html.escape(item.status)}</div>"
            f"<h3>{html.escape(item.url)}</h3>"
            f"<p>{html.escape(item.detail)}</p>"
            f"<p><strong>Category:</strong> {html.escape(item.category)}</p>"
            f"<p><strong>HTTP:</strong> {html.escape(str(item.http_status) if item.http_status is not None else 'n/a')}</p>"
            f"<p><strong>Content-Type:</strong> {html.escape(item.content_type or 'n/a')}</p>"
            f"<p><strong>Title:</strong> {html.escape(item.title or 'n/a')}</p>"
            f"<p><strong>Snippet:</strong> {html.escape(item.snippet or 'n/a')}</p>"
            f"<p><strong>Support:</strong> {html.escape(item.support_status or 'n/a')}</p>"
            f"<p><strong>Matched claim:</strong> {html.escape(item.matched_claim or 'n/a')}</p>"
            f"<p><strong>Support score:</strong> {item.support_score:.2f}</p>"
            f"<p><strong>Support detail:</strong> {html.escape(item.support_detail or 'n/a')}</p>"
            "</article>"
        )
        for item in trace.evidence_checks
    )


def write_html(trace: TraceRecord, destination: Path) -> None:
    payload = html.escape(json.dumps(trace.to_dict(), indent=2))
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InsightForge Trace</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --panel: #fffaf2;
      --ink: #1d1d1b;
      --muted: #625a4d;
      --accent: #c6532d;
      --accent-soft: #f1d3c7;
      --line: #d4c8b7;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Avenir Next", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(198,83,45,0.18), transparent 28%),
        linear-gradient(180deg, #efe3d5 0%, var(--bg) 42%, #f8f3ec 100%);
    }}
    .shell {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 64px;
    }}
    .hero, .panel {{
      background: rgba(255, 250, 242, 0.82);
      backdrop-filter: blur(8px);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: 0 24px 80px rgba(58, 42, 26, 0.08);
    }}
    .hero {{
      padding: 28px;
      margin-bottom: 20px;
    }}
    .eyebrow {{
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 12px;
      font-weight: 700;
    }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 20px;
    }}
    .metric, .node, .flag {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }}
    .metric strong {{
      display: block;
      font-size: 28px;
      margin-top: 8px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.25fr 1fr;
      gap: 20px;
    }}
    .panel {{
      padding: 22px;
    }}
    .stack {{
      display: grid;
      gap: 14px;
    }}
    .node-kind, .node-score {{
      color: var(--muted);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    pre {{
      overflow: auto;
      padding: 16px;
      border-radius: 16px;
      background: #1d1d1b;
      color: #f7f0e8;
      font-size: 13px;
    }}
    .empty {{
      color: var(--muted);
    }}
    @media (max-width: 860px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">InsightForge Trace</div>
      <h1>{html.escape(trace.model_hint)} decision map</h1>
      <p>{html.escape(trace.summary)}</p>
      <div class="metrics">
        <div class="metric">
          Provider
          <strong>{html.escape(trace.provider)}</strong>
        </div>
        <div class="metric">
          Status
          <strong>{html.escape(trace.overall_status)}</strong>
        </div>
        <div class="metric">
          Model
          <strong>{html.escape(trace.model_hint)}</strong>
        </div>
        <div class="metric">
          Confidence
          <strong>{trace.confidence_score:.2f}</strong>
        </div>
        <div class="metric">
          Exit code
          <strong>{trace.exit_code}</strong>
        </div>
        <div class="metric">
          Captured
          <strong>{html.escape(trace.captured_at[:19])}</strong>
        </div>
      </div>
    </section>
    <section class="grid">
      <div class="panel">
        <h2>Insight Map</h2>
        <div class="stack">{_render_nodes(trace)}</div>
      </div>
      <div class="panel">
        <h2>Risk Flags</h2>
        <div class="stack">{_render_flags(trace)}</div>
      </div>
    </section>
    <section class="grid" style="margin-top:20px;">
      <div class="panel">
        <h2>Policy Verdicts</h2>
        <div class="stack">{_render_policy_results(trace)}</div>
      </div>
      <div class="panel">
        <h2>Evidence Check</h2>
        <div class="stack">{_render_evidence(trace)}</div>
      </div>
    </section>
    <section class="grid" style="margin-top:20px;">
      <div class="panel">
        <h2>Provenance</h2>
        <div class="stack">{_render_list_items(trace.provenance)}</div>
      </div>
      <div class="panel">
        <h2>Metadata</h2>
        <div class="stack">{_render_metadata(trace)}</div>
      </div>
    </section>
    <section class="panel" style="margin-top:20px;">
      <h2>Raw Trace</h2>
      <pre>{payload}</pre>
    </section>
  </main>
</body>
</html>
"""
    destination.write_text(document, encoding="utf-8")
