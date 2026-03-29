"""Database connection and query helpers for FastAPI backend."""

from __future__ import annotations
import os
from pathlib import Path
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load .env from the project root (parent of backend/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Check your .env file.")
    return url


def query_df(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SQL query and return a list of dicts (one per row)."""
    conn = psycopg2.connect(_get_database_url())
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params if params else None)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    """Execute a SQL query and return a single dict or None."""
    conn = psycopg2.connect(_get_database_url())
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params if params else None)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
