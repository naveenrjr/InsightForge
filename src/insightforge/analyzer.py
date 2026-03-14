from __future__ import annotations

import re
from collections.abc import Sequence

from .models import RiskFlag, TraceNode, TraceRecord


HEDGE_PATTERNS = (
    r"\bmaybe\b",
    r"\bprobably\b",
    r"\bI think\b",
    r"\blikely\b",
    r"\bappears to\b",
    r"\bseems\b",
)

SOURCE_PATTERNS = (
    r"https?://",
    r"\bsource\b",
    r"\bcitation\b",
    r"\breference\b",
    r"\bdocumentation\b",
    r"\bresearch paper\b",
    r"\bstudy\b",
)

BIAS_PATTERNS = (
    r"\balways\b",
    r"\bnever\b",
    r"\bobviously\b",
    r"\beveryone\b",
    r"\bno one\b",
)


def _count_matches(patterns: Sequence[str], text: str) -> int:
    return sum(len(re.findall(pattern, text, flags=re.IGNORECASE)) for pattern in patterns)


def _build_summary(prompt: str, stdout: str, stderr: str, risk_count: int) -> str:
    if stderr.strip():
        return "The wrapped command produced stderr output; review execution details before trusting the answer."
    if risk_count:
        return "InsightForge detected language patterns that correlate with weak grounding or overconfident claims."
    if not stdout.strip():
        return "The wrapped command returned no stdout, so the trace is mostly execution metadata."
    if prompt.strip():
        return "The response completed without obvious risk markers, but the trace should still be reviewed for source quality."
    return "Execution completed successfully with a low-risk heuristic profile."


def build_trace(
    *,
    prompt: str,
    command: Sequence[str],
    model_hint: str,
    provider: str = "unknown",
    system_prompt: str = "",
    stdout: str,
    stderr: str,
    exit_code: int,
    metadata: dict[str, str] | None = None,
    provenance_notes: Sequence[str] | None = None,
) -> TraceRecord:
    output_blob = "\n".join(part for part in (stdout, stderr) if part)
    hedge_hits = _count_matches(HEDGE_PATTERNS, output_blob)
    source_hits = _count_matches(SOURCE_PATTERNS, output_blob)
    bias_hits = _count_matches(BIAS_PATTERNS, output_blob)
    stderr_penalty = 0.2 if stderr.strip() else 0.0
    empty_penalty = 0.15 if not stdout.strip() else 0.0

    confidence = 0.72
    confidence -= min(0.24, hedge_hits * 0.04)
    confidence -= min(0.20, bias_hits * 0.05)
    confidence -= stderr_penalty + empty_penalty
    confidence += min(0.18, source_hits * 0.06)
    confidence = max(0.05, min(0.99, round(confidence, 2)))

    bias_flags: list[RiskFlag] = []
    hallucination_flags: list[RiskFlag] = []
    provenance: list[str] = list(provenance_notes or [])

    if source_hits:
        provenance.append("Sources or citations were mentioned in the output.")
    elif not provenance:
        provenance.append("No explicit sources or citations were detected.")

    if bias_hits:
        bias_flags.append(
            RiskFlag(
                code="OVERGENERALIZATION",
                title="Overgeneralized claim pattern",
                severity="medium",
                evidence="The output uses absolute language that can hide edge cases or demographic skew.",
                recommendation="Ask the model to qualify claims, state assumptions, and list known exceptions.",
            )
        )

    if hedge_hits and not source_hits:
        hallucination_flags.append(
            RiskFlag(
                code="UNGROUNDED_HEDGING",
                title="Ungrounded uncertainty",
                severity="high",
                evidence="The output contains hedging language without nearby source signals.",
                recommendation="Request citations, intermediate evidence, or a narrower task boundary.",
            )
        )

    if stderr.strip():
        hallucination_flags.append(
            RiskFlag(
                code="EXECUTION_ANOMALY",
                title="Execution anomaly",
                severity="medium",
                evidence="The wrapped command emitted stderr output, which may indicate tool failure or partial completion.",
                recommendation="Inspect stderr and rerun before relying on the result for audits or downstream actions.",
            )
        )

    nodes = [
        TraceNode(id="prompt", label="Prompt", kind="input", detail=prompt or "No prompt recorded."),
        TraceNode(
            id="system",
            label="System Prompt",
            kind="input",
            detail=system_prompt or "No system prompt recorded.",
        ),
        TraceNode(
            id="execution",
            label="Execution",
            kind="process",
            detail=" ".join(command) if command else "No command recorded.",
            score=1.0 if exit_code == 0 else 0.4,
        ),
        TraceNode(
            id="analysis",
            label="Heuristic Analysis",
            kind="analysis",
            detail=f"Hedges={hedge_hits}, source signals={source_hits}, bias markers={bias_hits}",
            score=confidence,
        ),
        TraceNode(
            id="output",
            label="Model Output",
            kind="output",
            detail=(stdout or stderr or "No output captured.")[:1200],
            score=confidence,
        ),
    ]

    risk_count = len(bias_flags) + len(hallucination_flags)
    summary = _build_summary(prompt, stdout, stderr, risk_count)

    return TraceRecord(
        model_hint=model_hint or "unknown",
        provider=provider or "unknown",
        prompt=prompt,
        system_prompt=system_prompt,
        command=list(command),
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        metadata=dict(metadata or {}),
        confidence_score=confidence,
        bias_flags=bias_flags,
        hallucination_flags=hallucination_flags,
        provenance=provenance,
        nodes=nodes,
        summary=summary,
    )
