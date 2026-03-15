from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from insightforge.analyzer import build_trace
from insightforge.cli import run_init
from insightforge.config import AppConfig, PolicyConfig, RedactionConfig, StorageConfig
from insightforge.migrations import CURRENT_DB_SCHEMA_VERSION, get_schema_version, migrate_storage
from insightforge.policy import evaluate_policies
from insightforge.redaction import apply_redaction
from insightforge.store import index_trace, load_registry, load_trace
from insightforge.updater import is_newer_version


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


if __name__ == "__main__":
    unittest.main()
