from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Iterable

import psycopg


TABLES = ("users", "sessions", "jobs")
PRIMARY_KEYS = {
    "users": "user_id",
    "sessions": "token_hash",
    "jobs": "job_id",
}


def qmarks(count: int) -> str:
    return ", ".join(["%s"] * count)


def migrate_table(sqlite_conn: sqlite3.Connection, pg_conn, table: str) -> int:
    rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0

    columns = rows[0].keys()
    column_sql = ", ".join(columns)
    primary_key = PRIMARY_KEYS[table]
    update_sql = ", ".join(
        f"{column}=EXCLUDED.{column}" for column in columns if column != primary_key
    )
    sql = (
        f"INSERT INTO {table} ({column_sql}) VALUES ({qmarks(len(columns))}) "
        f"ON CONFLICT ({primary_key}) DO UPDATE SET {update_sql}"
    )

    with pg_conn.cursor() as cursor:
        cursor.executemany(sql, [tuple(row[column] for column in columns) for row in rows])
    return len(rows)


def create_schema(pg_conn) -> None:
    schema = [
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
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at DESC)",
    ]
    with pg_conn.cursor() as cursor:
        for statement in schema:
            cursor.execute(statement)
        cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS quality_preset TEXT NOT NULL DEFAULT 'balanced'")
        cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS image_object_key TEXT")
        cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS glb_object_key TEXT")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy local SQLite app data into Supabase Postgres.")
    parser.add_argument(
        "--sqlite-path",
        default=str(Path(__file__).resolve().parents[1] / "data" / "app.db"),
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Supabase Postgres connection string. Defaults to DATABASE_URL.",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required.")

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row
    try:
        with psycopg.connect(args.database_url) as pg_conn:
            create_schema(pg_conn)
            for table in TABLES:
                count = migrate_table(sqlite_conn, pg_conn, table)
                print(f"{table}: {count}")
            pg_conn.commit()
    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    main()
