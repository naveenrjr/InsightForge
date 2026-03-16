from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import StorageConfig
from .migrations import migrate_storage
from .models import EvidenceCheck, PolicyResult, RiskFlag, TraceNode, TraceRecord


REGISTRY_DIR = Path(".insightforge")
REGISTRY_PATH = REGISTRY_DIR / "registry.json"


def ensure_storage(config: StorageConfig) -> Path:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    db_path = Path(config.sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    migrate_storage(config)
    return db_path


def index_trace(trace: TraceRecord, json_path: Path, html_path: Path, config: StorageConfig) -> None:
    db_path = ensure_storage(config)
    payload = json.dumps(trace.to_dict())
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO traces (
                trace_id, captured_at, provider, model_hint, prompt, confidence_score,
                overall_status, json_path, html_path, trace_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
                captured_at=excluded.captured_at,
                provider=excluded.provider,
                model_hint=excluded.model_hint,
                prompt=excluded.prompt,
                confidence_score=excluded.confidence_score,
                overall_status=excluded.overall_status,
                json_path=excluded.json_path,
                html_path=excluded.html_path,
                trace_payload=excluded.trace_payload
            """,
            (
                trace.trace_id,
                trace.captured_at,
                trace.provider,
                trace.model_hint,
                trace.prompt,
                trace.confidence_score,
                trace.overall_status,
                str(json_path),
                str(html_path),
                payload,
            ),
        )
    _write_legacy_registry(config)


def load_registry(config: StorageConfig, limit: int | None = None) -> list[dict]:
    db_path = ensure_storage(config)
    query = """
        SELECT trace_id, captured_at, provider, model_hint, prompt, confidence_score, overall_status, json_path, html_path
        FROM traces
        ORDER BY captured_at DESC
    """
    params: tuple[object, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [
        {
            "trace_id": row[0],
            "captured_at": row[1],
            "provider": row[2],
            "model_hint": row[3],
            "prompt": row[4],
            "confidence_score": row[5],
            "overall_status": row[6],
            "json_path": row[7],
            "html_path": row[8],
        }
        for row in rows
    ]


def load_trace(source: str, config: StorageConfig) -> TraceRecord:
    candidate = Path(source)
    if candidate.exists():
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        return _trace_from_payload(payload)

    db_path = ensure_storage(config)
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT trace_payload FROM traces WHERE trace_id = ?",
            (source,),
        ).fetchone()
    if row is None:
        raise FileNotFoundError(f"Could not resolve trace '{source}' as a file path or indexed trace id.")
    return _trace_from_payload(json.loads(row[0]))


def _trace_from_payload(payload: dict) -> TraceRecord:
    return TraceRecord(
        version=payload.get("version", "0.1"),
        captured_at=payload.get("captured_at", ""),
        trace_id=payload.get("trace_id", ""),
        model_hint=payload.get("model_hint", "unknown"),
        provider=payload.get("provider", "unknown"),
        prompt=payload.get("prompt", ""),
        system_prompt=payload.get("system_prompt", ""),
        command=list(payload.get("command", [])),
        exit_code=payload.get("exit_code"),
        stdout=payload.get("stdout", ""),
        stderr=payload.get("stderr", ""),
        metadata=dict(payload.get("metadata", {})),
        confidence_score=float(payload.get("confidence_score", 0.0)),
        bias_flags=[RiskFlag(**flag) for flag in payload.get("bias_flags", [])],
        hallucination_flags=[RiskFlag(**flag) for flag in payload.get("hallucination_flags", [])],
        evidence_checks=[EvidenceCheck(**item) for item in payload.get("evidence_checks", [])],
        policy_results=[PolicyResult(**result) for result in payload.get("policy_results", [])],
        overall_status=payload.get("overall_status", "unknown"),
        provenance=list(payload.get("provenance", [])),
        nodes=[TraceNode(**node) for node in payload.get("nodes", [])],
        summary=payload.get("summary", ""),
    )


def _write_legacy_registry(config: StorageConfig) -> None:
    entries = load_registry(config)
    REGISTRY_PATH.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
