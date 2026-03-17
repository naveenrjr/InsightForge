from __future__ import annotations

import re
from collections.abc import Sequence

from .models import EvidenceCheck, RiskFlag, TraceNode, TraceRecord


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


def _evidence_metrics(evidence_checks: Sequence[EvidenceCheck]) -> tuple[int, int]:
    reachable = sum(1 for item in evidence_checks if item.status == "reachable")
    problematic = sum(1 for item in evidence_checks if item.status in {"unreachable", "timeout", "invalid", "blocked"})
    return reachable, problematic


def _support_metrics(evidence_checks: Sequence[EvidenceCheck]) -> tuple[int, int]:
    supported = sum(1 for item in evidence_checks if item.support_status == "supported")
    unsupported = sum(1 for item in evidence_checks if item.support_status == "insufficient_evidence")
    return supported, unsupported


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
    evidence_checks: Sequence[EvidenceCheck] | None = None,
) -> TraceRecord:
    output_blob = "\n".join(part for part in (stdout, stderr) if part)
    hedge_hits = _count_matches(HEDGE_PATTERNS, output_blob)
    source_hits = _count_matches(SOURCE_PATTERNS, output_blob)
    bias_hits = _count_matches(BIAS_PATTERNS, output_blob)
    stderr_penalty = 0.2 if stderr.strip() else 0.0
    empty_penalty = 0.15 if not stdout.strip() else 0.0
    reachable_sources, problematic_sources = _evidence_metrics(evidence_checks or [])
    supported_sources, unsupported_sources = _support_metrics(evidence_checks or [])

    confidence = 0.72
    confidence -= min(0.24, hedge_hits * 0.04)
    confidence -= min(0.20, bias_hits * 0.05)
    confidence -= stderr_penalty + empty_penalty
    confidence += min(0.18, source_hits * 0.06)
    confidence += min(0.12, reachable_sources * 0.06)
    confidence += min(0.12, supported_sources * 0.08)
    confidence -= min(0.18, problematic_sources * 0.06)
    confidence -= min(0.16, unsupported_sources * 0.08)
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

    if problematic_sources:
        hallucination_flags.append(
            RiskFlag(
                code="UNVERIFIABLE_SOURCE",
                title="Unverifiable cited source",
                severity="high",
                evidence="One or more cited URLs could not be verified successfully.",
                recommendation="Use reachable, publicly available citations or disable verification only for trusted private environments.",
            )
        )

    if unsupported_sources:
        hallucination_flags.append(
            RiskFlag(
                code="UNSUPPORTED_CLAIM",
                title="Source does not clearly support the claim",
                severity="high",
                evidence="A cited source was reachable, but the extracted snippet did not align with the model's claim.",
                recommendation="Use citations that directly support the claim or narrow the answer to what the evidence actually states.",
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
            detail=(
                f"Hedges={hedge_hits}, source signals={source_hits}, bias markers={bias_hits}, "
                f"reachable sources={reachable_sources}, supported sources={supported_sources}, "
                f"problematic sources={problematic_sources}"
            ),
            score=confidence,
        ),
        TraceNode(
            id="evidence",
            label="Evidence Verification",
            kind="analysis",
            detail=(
                "No cited URLs detected."
                if not evidence_checks
                else (
                    f"Verified {len(evidence_checks)} cited URLs: {reachable_sources} reachable, "
                    f"{supported_sources} claim-supporting, {problematic_sources} problematic."
                )
            ),
            score=(
                1.0
                if evidence_checks and not problematic_sources and not unsupported_sources
                else (0.4 if problematic_sources or unsupported_sources else None)
            ),
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
        evidence_checks=list(evidence_checks or []),
        provenance=provenance,
        nodes=nodes,
        summary=summary,
    )
