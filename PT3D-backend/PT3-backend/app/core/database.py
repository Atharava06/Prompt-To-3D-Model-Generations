from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import settings

_lock = threading.RLock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def using_postgres() -> bool:
    url = settings.database_url or ""
    return url.startswith(("postgres://", "postgresql://"))


def _translate_query(query: str) -> str:
    if not using_postgres():
        return query
    # The app uses qmark parameters and does not place '?' inside SQL literals.
    return query.replace("?", "%s")


@contextmanager
def _connect() -> Iterator[Any]:
    if using_postgres():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL is set to Postgres, but psycopg is not installed. "
                "Install backend requirements first."
            ) from exc

        conn = psycopg.connect(settings.database_url, row_factory=dict_row)
        try:
            yield conn
        finally:
            conn.close()
        return

    db_path: Path = settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _schema_sql() -> list[str]:
    return [
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            image_path TEXT NOT NULL,
            glb_path TEXT NOT NULL,
            quality_preset TEXT NOT NULL DEFAULT 'balanced',
            image_object_key TEXT,
            glb_object_key TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS training_examples (
            example_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            quality_preset TEXT NOT NULL,
            failure_label TEXT NOT NULL,
            admin_notes TEXT,
            image_path TEXT NOT NULL,
            glb_path TEXT NOT NULL,
            image_object_key TEXT,
            glb_object_key TEXT,
            include_in_sdxl_lora INTEGER NOT NULL DEFAULT 0,
            include_in_hunyuan INTEGER NOT NULL DEFAULT 0,
            review_status TEXT NOT NULL DEFAULT 'candidate',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_training_examples_job ON training_examples(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_training_examples_label ON training_examples(failure_label)",
    ]


def init_db() -> None:
    with _lock:
        with _connect() as conn:
            try:
                for statement in _schema_sql():
                    conn.execute(statement)
                _ensure_column(conn, "jobs", "quality_preset", "TEXT NOT NULL DEFAULT 'balanced'")
                _ensure_column(conn, "jobs", "image_object_key", "TEXT")
                _ensure_column(conn, "jobs", "glb_object_key", "TEXT")
                _ensure_column(conn, "training_examples", "include_in_sdxl_lora", "INTEGER NOT NULL DEFAULT 0")
                _ensure_column(conn, "training_examples", "include_in_hunyuan", "INTEGER NOT NULL DEFAULT 0")
                _ensure_column(conn, "training_examples", "review_status", "TEXT NOT NULL DEFAULT 'candidate'")
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _ensure_column(conn: Any, table: str, column: str, column_type: str) -> None:
    if using_postgres():
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}")
        return

    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> Any | None:
    with _lock:
        with _connect() as conn:
            cursor = conn.execute(_translate_query(query), params)
            return cursor.fetchone()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[Any]:
    with _lock:
        with _connect() as conn:
            cursor = conn.execute(_translate_query(query), params)
            return list(cursor.fetchall())


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with _lock:
        with _connect() as conn:
            try:
                cursor = conn.execute(_translate_query(query), params)
                conn.commit()
                return cursor.rowcount
            except Exception:
                conn.rollback()
                raise
