from __future__ import annotations

import re
from dataclasses import replace

from .config import RedactionConfig
from .models import EvidenceCheck, RiskFlag, TraceNode, TraceRecord


def apply_redaction(trace: TraceRecord, config: RedactionConfig) -> TraceRecord:
    if not config.enabled:
        return trace

    def scrub(value: str) -> str:
        masked = value
        for pattern in config.patterns:
            masked = re.sub(pattern, config.mask, masked)
        return masked[:]

    redacted_nodes = [
        TraceNode(
            id=node.id,
            label=node.label,
            kind=node.kind,
            detail=scrub(node.detail),
            score=node.score,
        )
        for node in trace.nodes
    ]
    redacted_evidence = [_redact_evidence(item, scrub) for item in trace.evidence_checks]
    redacted_bias = [_redact_flag(flag, scrub) for flag in trace.bias_flags]
    redacted_hallucination = [_redact_flag(flag, scrub) for flag in trace.hallucination_flags]

    return replace(
        trace,
        prompt=scrub(trace.prompt),
        system_prompt=scrub(trace.system_prompt),
        command=[scrub(part) for part in trace.command],
        stdout=scrub(trace.stdout),
        stderr=scrub(trace.stderr),
        metadata={key: scrub(value) for key, value in trace.metadata.items()},
        provenance=[scrub(item) for item in trace.provenance],
        nodes=redacted_nodes,
        evidence_checks=redacted_evidence,
        bias_flags=redacted_bias,
        hallucination_flags=redacted_hallucination,
    )


def _redact_flag(flag: RiskFlag, scrub) -> RiskFlag:
    return RiskFlag(
        code=flag.code,
        title=scrub(flag.title),
        severity=flag.severity,
        evidence=scrub(flag.evidence),
        recommendation=scrub(flag.recommendation),
    )


def _redact_evidence(item: EvidenceCheck, scrub) -> EvidenceCheck:
    return EvidenceCheck(
        url=scrub(item.url),
        status=item.status,
        category=item.category,
        detail=scrub(item.detail),
        http_status=item.http_status,
        content_type=scrub(item.content_type),
        title=scrub(item.title),
        snippet=scrub(item.snippet),
    )
