from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from urllib.error import URLError

from insightforge.analyzer import build_trace
from insightforge.cli import run_init
from insightforge.config import PolicyConfig, RedactionConfig, StorageConfig
from insightforge.migrations import CURRENT_DB_SCHEMA_VERSION, get_schema_version, migrate_storage
from insightforge.models import EvidenceCheck
from insightforge.policy import evaluate_policies
from insightforge.redaction import apply_redaction
from insightforge.store import TraceQuery, index_trace, load_registry, load_trace, search_registry
from insightforge.updater import is_newer_version
from insightforge.verifier import VerificationConfig, extract_claims, extract_urls, verify_output_sources


class ProductionMvpTests(unittest.TestCase):
    def test_redaction_masks_secrets_and_emails(self) -> None:
        trace = build_trace(
            prompt="Use sk-secret-value and email admin@example.com",
            command=["mock"],
            model_hint="demo-model",
            provider="mock",
            stdout="Bearer token123 and admin@example.com",
            stderr="",
            exit_code=0,
            metadata={"api_key": "sk-secret-value"},
        )
        redacted = apply_redaction(trace, RedactionConfig())

        self.assertNotIn("sk-secret-value", redacted.prompt)
        self.assertNotIn("admin@example.com", redacted.stdout)
        self.assertEqual("[REDACTED]", redacted.metadata["api_key"])

    def test_policy_evaluation_fails_low_confidence_and_stderr(self) -> None:
        trace = build_trace(
            prompt="No source answer",
            command=["mock"],
            model_hint="demo-model",
            provider="mock",
            stdout="Maybe this always works",
            stderr="tool failed",
            exit_code=1,
        )
        results, overall_status = evaluate_policies(
            trace,
            PolicyConfig(
                min_confidence=0.8,
                require_sources=True,
                fail_on_stderr=True,
                block_absolute_language=True,
            ),
        )

        self.assertEqual("fail", overall_status)
        self.assertTrue(any(result.policy_id == "min_confidence" and result.status == "fail" for result in results))
        self.assertTrue(any(result.policy_id == "fail_on_stderr" and result.status == "fail" for result in results))

    def test_policy_evaluation_requires_verifiable_source(self) -> None:
        trace = build_trace(
            prompt="Answer with a source",
            command=["mock"],
            model_hint="demo-model",
            provider="mock",
            stdout="Source: https://example.com/report",
            stderr="",
            exit_code=0,
            evidence_checks=[
                EvidenceCheck(
                    url="https://example.com/report",
                    status="reachable",
                    category="http",
                    detail="Source was fetched successfully.",
                    http_status=200,
                )
            ],
        )
        results, overall_status = evaluate_policies(
            trace,
            PolicyConfig(require_sources=True, require_verifiable_sources=True),
        )

        self.assertEqual("pass", overall_status)
        self.assertTrue(
            any(result.policy_id == "require_verifiable_sources" and result.status == "pass" for result in results)
        )

    def test_policy_evaluation_requires_supported_source(self) -> None:
        trace = build_trace(
            prompt="Answer with a supported source",
            command=["mock"],
            model_hint="demo-model",
            provider="mock",
            stdout="SQLite stores data in a local file and can be embedded into applications.",
            stderr="",
            exit_code=0,
            evidence_checks=[
                EvidenceCheck(
                    url="https://example.com/sqlite",
                    status="reachable",
                    category="http",
                    detail="Source was fetched successfully.",
                    http_status=200,
                    title="SQLite Overview",
                    snippet="SQLite is a self-contained embedded database engine stored in a local file.",
                    support_status="supported",
                    support_detail="Source snippet overlaps strongly with a concrete claim from the output.",
                    matched_claim="SQLite stores data in a local file and can be embedded into applications.",
                    support_score=0.71,
                )
            ],
        )
        results, overall_status = evaluate_policies(
            trace,
            PolicyConfig(require_sources=True, require_verifiable_sources=True, require_supported_sources=True),
        )

        self.assertEqual("pass", overall_status)
        self.assertTrue(
            any(result.policy_id == "require_supported_sources" and result.status == "pass" for result in results)
        )

    def test_sqlite_index_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            json_path = cwd / "trace.json"
            html_path = cwd / "trace.html"
            config = StorageConfig(sqlite_path=str(cwd / ".insightforge" / "traces.db"))
            trace = build_trace(
                prompt="Round trip trace",
                command=["mock"],
                model_hint="demo-model",
                provider="mock",
                stdout="output",
                stderr="",
                exit_code=0,
                evidence_checks=[
                    EvidenceCheck(
                        url="https://example.com/report",
                        status="reachable",
                        category="http",
                        detail="Source was fetched successfully.",
                        title="Report",
                        snippet="The report supports the captured statement.",
                        support_status="supported",
                        support_detail="Source snippet overlaps strongly with a concrete claim from the output.",
                        matched_claim="Supported captured statement.",
                        support_score=0.66,
                    )
                ],
            )
            trace.overall_status = "pass"
            json_path.write_text("{}", encoding="utf-8")
            html_path.write_text("<html></html>", encoding="utf-8")

            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(cwd)
                index_trace(trace, json_path, html_path, config)
                entries = load_registry(config)
                loaded = load_trace(trace.trace_id, config)
            finally:
                os.chdir(old_cwd)

            self.assertEqual(1, len(entries))
            self.assertEqual(trace.trace_id, entries[0]["trace_id"])
            self.assertEqual(trace.trace_id, loaded.trace_id)
            self.assertEqual("output", loaded.stdout)
            self.assertEqual("supported", loaded.evidence_checks[0].support_status)
            self.assertEqual(0.66, loaded.evidence_checks[0].support_score)

    def test_search_registry_filters_by_provider_status_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config = StorageConfig(sqlite_path=str(cwd / ".insightforge" / "traces.db"))
            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(cwd)
                first = build_trace(
                    prompt="Investigate NASA Mars claim",
                    command=["openai"],
                    model_hint="gpt-4.1-mini",
                    provider="openai",
                    stdout="NASA claim output",
                    stderr="",
                    exit_code=0,
                )
                second = build_trace(
                    prompt="Review Anthropic safety note",
                    command=["anthropic"],
                    model_hint="claude-sonnet",
                    provider="anthropic",
                    stdout="Safety note output",
                    stderr="",
                    exit_code=0,
                )
                first.overall_status = "fail"
                second.overall_status = "pass"
                (cwd / "one.json").write_text("{}", encoding="utf-8")
                (cwd / "one.html").write_text("<html></html>", encoding="utf-8")
                (cwd / "two.json").write_text("{}", encoding="utf-8")
                (cwd / "two.html").write_text("<html></html>", encoding="utf-8")
                index_trace(first, cwd / "one.json", cwd / "one.html", config)
                index_trace(second, cwd / "two.json", cwd / "two.html", config)

                provider_results = search_registry(config, TraceQuery(provider="openai", limit=10))
                status_results = search_registry(config, TraceQuery(overall_status="pass", limit=10))
                text_results = search_registry(config, TraceQuery(text="NASA", limit=10))
            finally:
                os.chdir(old_cwd)

        self.assertEqual(1, len(provider_results))
        self.assertEqual("openai", provider_results[0]["provider"])
        self.assertEqual(1, len(status_results))
        self.assertEqual("pass", status_results[0]["overall_status"])
        self.assertEqual(1, len(text_results))
        self.assertIn("NASA", text_results[0]["prompt"])

    def test_search_registry_filters_by_date_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config = StorageConfig(sqlite_path=str(cwd / ".insightforge" / "traces.db"))
            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(cwd)
                older = build_trace(
                    prompt="Older trace",
                    command=["mock"],
                    model_hint="demo-model",
                    provider="mock",
                    stdout="older",
                    stderr="",
                    exit_code=0,
                )
                newer = build_trace(
                    prompt="Newer trace",
                    command=["mock"],
                    model_hint="demo-model",
                    provider="mock",
                    stdout="newer",
                    stderr="",
                    exit_code=0,
                )
                older.captured_at = "2026-03-20T10:00:00+00:00"
                newer.captured_at = "2026-03-23T10:00:00+00:00"
                older.trace_id = "older12345678"
                newer.trace_id = "newer12345678"
                older.overall_status = "pass"
                newer.overall_status = "pass"
                (cwd / "older.json").write_text("{}", encoding="utf-8")
                (cwd / "older.html").write_text("<html></html>", encoding="utf-8")
                (cwd / "newer.json").write_text("{}", encoding="utf-8")
                (cwd / "newer.html").write_text("<html></html>", encoding="utf-8")
                index_trace(older, cwd / "older.json", cwd / "older.html", config)
                index_trace(newer, cwd / "newer.json", cwd / "newer.html", config)

                filtered = search_registry(
                    config,
                    TraceQuery(date_from="2026-03-22T00:00:00+00:00", limit=10),
                )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(1, len(filtered))
        self.assertEqual("Newer trace", filtered[0]["prompt"])

    def test_migrate_legacy_database_to_current_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            db_path = cwd / ".insightforge" / "traces.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            import sqlite3

            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE traces (
                        trace_id TEXT PRIMARY KEY,
                        captured_at TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        model_hint TEXT NOT NULL,
                        prompt TEXT NOT NULL,
                        confidence_score REAL NOT NULL,
                        json_path TEXT NOT NULL,
                        html_path TEXT NOT NULL,
                        trace_payload TEXT NOT NULL
                    )
                    """
                )

            config = StorageConfig(sqlite_path=str(db_path))
            self.assertEqual(1, get_schema_version(config))
            before, after = migrate_storage(config)

            self.assertEqual(1, before)
            self.assertEqual(CURRENT_DB_SCHEMA_VERSION, after)
            self.assertEqual(CURRENT_DB_SCHEMA_VERSION, get_schema_version(config))

    def test_version_comparison_detects_newer_release(self) -> None:
        self.assertTrue(is_newer_version("0.2.0", "0.1.9"))
        self.assertFalse(is_newer_version("0.1.0", "0.1.0"))
        self.assertFalse(is_newer_version("0.1.0", "0.2.0"))

    def test_init_writes_default_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                import os

                os.chdir(tmp)
                result = run_init(Namespace(force=False))
                config_path = Path(".insightforge.toml")
                exists = config_path.exists()
                contents = config_path.read_text(encoding="utf-8") if exists else ""
            finally:
                os.chdir(cwd)

        self.assertEqual(0, result)
        self.assertTrue(exists)
        self.assertIn("min_confidence = 0.85", contents)
        self.assertIn("require_verifiable_sources = true", contents)

    def test_extract_urls_normalizes_trailing_punctuation(self) -> None:
        urls = extract_urls("See https://example.com/report, and https://example.com/report.")
        self.assertEqual(["https://example.com/report"], urls)

    def test_extract_claims_skips_urls_and_short_fragments(self) -> None:
        claims = extract_claims(
            "SQLite can run as an embedded database engine inside local applications. "
            "See https://example.com/sqlite for more. "
            "Fast and simple."
        )
        self.assertEqual(
            ["SQLite can run as an embedded database engine inside local applications."],
            claims,
        )

    def test_verify_output_sources_blocks_private_hosts(self) -> None:
        evidence = verify_output_sources(
            "Source: http://127.0.0.1/internal",
            VerificationConfig(),
        )
        self.assertEqual(1, len(evidence))
        self.assertEqual("blocked", evidence[0].status)

    def test_verify_output_sources_reports_reachable_and_unreachable(self) -> None:
        def fetcher(url: str, timeout_seconds: int, max_bytes: int) -> tuple[int, str, str]:
            if "good" in url:
                return 200, "text/html", "<html><title>Trusted Report</title><body>Evidence body</body></html>"
            raise URLError("dns failure")

        evidence = verify_output_sources(
            "Sources: https://good.example/report and https://bad.example/report",
            VerificationConfig(),
            fetcher=fetcher,
        )

        self.assertEqual(2, len(evidence))
        self.assertEqual("reachable", evidence[0].status)
        self.assertEqual("Trusted Report", evidence[0].title)
        self.assertEqual("unreachable", evidence[1].status)

    def test_verify_output_sources_marks_supported_claims(self) -> None:
        def fetcher(url: str, timeout_seconds: int, max_bytes: int) -> tuple[int, str, str]:
            return (
                200,
                "text/html",
                (
                    "<html><title>SQLite Overview</title><body>"
                    "SQLite is an embedded database engine that stores data in a local file."
                    "</body></html>"
                ),
            )

        evidence = verify_output_sources(
            (
                "SQLite stores data in a local file and can be embedded into applications. "
                "Source: https://example.com/sqlite"
            ),
            VerificationConfig(),
            fetcher=fetcher,
        )

        self.assertEqual(1, len(evidence))
        self.assertEqual("supported", evidence[0].support_status)
        self.assertGreaterEqual(evidence[0].support_score, 0.55)
        self.assertIn("SQLite stores data in a local file", evidence[0].matched_claim)

    def test_verify_output_sources_marks_insufficient_evidence(self) -> None:
        def fetcher(url: str, timeout_seconds: int, max_bytes: int) -> tuple[int, str, str]:
            return (
                200,
                "text/html",
                (
                    "<html><title>Weather Report</title><body>"
                    "A storm system is moving across the coast this weekend."
                    "</body></html>"
                ),
            )

        evidence = verify_output_sources(
            (
                "SQLite stores data in a local file and can be embedded into applications. "
                "Source: https://example.com/weather"
            ),
            VerificationConfig(),
            fetcher=fetcher,
        )

        self.assertEqual(1, len(evidence))
        self.assertEqual("insufficient_evidence", evidence[0].support_status)
        self.assertEqual(0.0, evidence[0].support_score)

    def test_build_trace_flags_unsupported_claims(self) -> None:
        supported = build_trace(
            prompt="Answer with support",
            command=["mock"],
            model_hint="demo-model",
            provider="mock",
            stdout="SQLite stores data in a local file and can be embedded into applications.",
            stderr="",
            exit_code=0,
            evidence_checks=[
                EvidenceCheck(
                    url="https://example.com/sqlite",
                    status="reachable",
                    category="http",
                    detail="Source was fetched successfully.",
                    support_status="supported",
                    support_detail="Source snippet overlaps strongly with a concrete claim from the output.",
                    matched_claim="SQLite stores data in a local file and can be embedded into applications.",
                    support_score=0.71,
                )
            ],
        )
        unsupported = build_trace(
            prompt="Answer with support",
            command=["mock"],
            model_hint="demo-model",
            provider="mock",
            stdout="SQLite stores data in a local file and can be embedded into applications.",
            stderr="",
            exit_code=0,
            evidence_checks=[
                EvidenceCheck(
                    url="https://example.com/weather",
                    status="reachable",
                    category="http",
                    detail="Source was fetched successfully.",
                    support_status="insufficient_evidence",
                    support_detail="Source snippet does not clearly support any extracted claim.",
                    matched_claim="SQLite stores data in a local file and can be embedded into applications.",
                    support_score=0.0,
                )
            ],
        )

        self.assertGreater(supported.confidence_score, unsupported.confidence_score)
        self.assertTrue(any(flag.code == "UNSUPPORTED_CLAIM" for flag in unsupported.hallucination_flags))


if __name__ == "__main__":
    unittest.main()
