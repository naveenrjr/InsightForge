from __future__ import annotations

from .config import PolicyConfig
from .models import PolicyResult, TraceRecord


def evaluate_policies(trace: TraceRecord, config: PolicyConfig) -> tuple[list[PolicyResult], str]:
    results: list[PolicyResult] = []

    if trace.confidence_score >= config.min_confidence:
        results.append(
            PolicyResult(
                policy_id="min_confidence",
                status="pass",
                severity="medium",
                message=f"Confidence {trace.confidence_score:.2f} meets threshold {config.min_confidence:.2f}.",
            )
        )
    else:
        results.append(
            PolicyResult(
                policy_id="min_confidence",
                status="fail",
                severity="high",
                message=f"Confidence {trace.confidence_score:.2f} is below threshold {config.min_confidence:.2f}.",
            )
        )

    if config.require_sources:
        has_source = any("source" in item.lower() or "citation" in item.lower() for item in trace.provenance)
        results.append(
            PolicyResult(
                policy_id="require_sources",
                status="pass" if has_source else "fail",
                severity="high",
                message="Trace contains source provenance." if has_source else "Trace lacks required source provenance.",
            )
        )

    if config.fail_on_stderr:
        clean = not trace.stderr.strip()
        results.append(
            PolicyResult(
                policy_id="fail_on_stderr",
                status="pass" if clean else "fail",
                severity="high",
                message="Trace stderr is empty." if clean else "Trace contains stderr output.",
            )
        )

    if config.block_absolute_language:
        overconfident = any(flag.code == "OVERGENERALIZATION" for flag in trace.bias_flags)
        results.append(
            PolicyResult(
                policy_id="block_absolute_language",
                status="fail" if overconfident else "pass",
                severity="medium",
                message=(
                    "Absolute language detected in the output."
                    if overconfident
                    else "No blocked absolute language detected."
                ),
            )
        )

    overall_status = "pass" if all(result.status == "pass" for result in results) else "fail"
    return results, overall_status
