from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha1


TRACE_SCHEMA_VERSION = "0.2"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_trace_id(captured_at: str, provider: str, model_hint: str, prompt: str) -> str:
    seed = f"{captured_at}|{provider}|{model_hint}|{prompt}".encode("utf-8")
    return sha1(seed).hexdigest()[:12]


@dataclass(slots=True)
class TraceNode:
    id: str
    label: str
    kind: str
    detail: str
    score: float | None = None


@dataclass(slots=True)
class RiskFlag:
    code: str
    title: str
    severity: str
    evidence: str
    recommendation: str


@dataclass(slots=True)
class PolicyResult:
    policy_id: str
    status: str
    severity: str
    message: str


@dataclass(slots=True)
class TraceRecord:
    version: str = TRACE_SCHEMA_VERSION
    captured_at: str = field(default_factory=utc_now_iso)
    trace_id: str = ""
    model_hint: str = "unknown"
    provider: str = "unknown"
    prompt: str = ""
    system_prompt: str = ""
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    confidence_score: float = 0.0
    bias_flags: list[RiskFlag] = field(default_factory=list)
    hallucination_flags: list[RiskFlag] = field(default_factory=list)
    policy_results: list[PolicyResult] = field(default_factory=list)
    overall_status: str = "unknown"
    provenance: list[str] = field(default_factory=list)
    nodes: list[TraceNode] = field(default_factory=list)
    summary: str = ""

    def __post_init__(self) -> None:
        if not self.trace_id:
            self.trace_id = build_trace_id(self.captured_at, self.provider, self.model_hint, self.prompt)

    def to_dict(self) -> dict:
        return asdict(self)
