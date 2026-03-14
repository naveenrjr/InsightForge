from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import StorageConfig


CURRENT_DB_SCHEMA_VERSION = 2


def get_schema_version(config: StorageConfig) -> int:
    db_path = Path(config.sqlite_path)
    if not db_path.exists():
        return 0

    with sqlite3.connect(db_path) as connection:
        if not _table_exists(connection, "metadata"):
            return 1 if _table_exists(connection, "traces") else 0
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
    return int(row[0]) if row else 0


def migrate_storage(config: StorageConfig) -> tuple[int, int]:
    db_path = Path(config.sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    before = get_schema_version(config)

    with sqlite3.connect(db_path) as connection:
        _ensure_metadata_table(connection)
        if not _table_exists(connection, "traces"):
            _create_traces_table(connection)
        else:
            _migrate_traces_table(connection)
        _set_schema_version(connection, CURRENT_DB_SCHEMA_VERSION)

    return before, CURRENT_DB_SCHEMA_VERSION


def _ensure_metadata_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )


def _create_traces_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS traces (
            trace_id TEXT PRIMARY KEY,
            captured_at TEXT NOT NULL,
            provider TEXT NOT NULL,
            model_hint TEXT NOT NULL,
            prompt TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            overall_status TEXT NOT NULL,
            json_path TEXT NOT NULL,
            html_path TEXT NOT NULL,
            trace_payload TEXT NOT NULL
        )
        """
    )


def _migrate_traces_table(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(traces)").fetchall()
    }
    if "overall_status" not in columns:
        connection.execute(
            "ALTER TABLE traces ADD COLUMN overall_status TEXT NOT NULL DEFAULT 'unknown'"
        )


def _set_schema_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(
        """
        INSERT INTO metadata (key, value) VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None
