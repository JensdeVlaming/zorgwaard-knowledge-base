"""Lightweight plain-SQL migration runner."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import sqlparse
from sqlalchemy import text
from sqlalchemy.engine import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / "sql"


def _iter_statements(sql: str) -> Iterable[str]:
    """Split raw SQL into executable statements."""
    for stmt in sqlparse.split(sql):
        stripped = stmt.strip()
        if stripped:
            yield stripped


def run_pending_migrations(engine: Engine) -> None:
    """Apply any migrations that have not been recorded yet."""
    if not MIGRATIONS_DIR.exists():
        return

    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

        applied = {
            row[0]
            for row in conn.execute(text("SELECT filename FROM schema_migrations"))
        }

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            name = path.name
            if name in applied:
                continue

            sql = path.read_text(encoding="utf-8")
            for statement in _iter_statements(sql):
                conn.exec_driver_sql(statement)

            conn.execute(
                text(
                    "INSERT INTO schema_migrations (filename) VALUES (:filename)"
                ),
                {"filename": name},
            )
            print(f"Applied migration: {name}")
