"""Database connection and query helpers — Supabase (PostgreSQL) backend."""

import os
import psycopg2
import psycopg2.extras
import pandas as pd

def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    return url


class _Cursor:
    """Proxy for psycopg2 cursor — converts RealDictRow to tuples for index access."""

    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return tuple(row.values()) if isinstance(row, dict) else tuple(row)

    def fetchall(self):
        return [
            tuple(r.values()) if isinstance(r, dict) else tuple(r)
            for r in self._cur.fetchall()
        ]


class Connection:
    """
    Thin wrapper around psycopg2 connection that mirrors the sqlite3 interface
    used throughout this app (conn.execute, conn.executemany, conn.commit, conn.close).
    """

    def __init__(self, database_url: str):
        self._conn = psycopg2.connect(database_url)
        self._conn.autocommit = False

    def execute(self, sql: str, params=()):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(sql, params or None)
        except Exception:
            self._conn.rollback()
            raise
        return _Cursor(cur)

    def executemany(self, sql: str, rows):
        cur = self._conn.cursor()
        try:
            cur.executemany(sql, rows)
        except Exception:
            self._conn.rollback()
            raise

    def commit(self):
        self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def rollback(self):
        self._conn.rollback()


def get_connection() -> Connection:
    return Connection(_get_database_url())


def create_tables():
    """Create all tables and indexes if they don't exist."""
    conn = get_connection()
    stmts = [
        """CREATE TABLE IF NOT EXISTS lca_records (
            case_number TEXT PRIMARY KEY,
            case_status TEXT,
            received_date TEXT,
            decision_date TEXT,
            visa_class TEXT,
            employer_name TEXT,
            trade_name_dba TEXT,
            employer_city TEXT,
            employer_state TEXT,
            naics_code TEXT,
            job_title TEXT,
            soc_code TEXT,
            soc_title TEXT,
            full_time_position TEXT,
            begin_date TEXT,
            end_date TEXT,
            total_worker_positions INTEGER,
            worksite_city TEXT,
            worksite_county TEXT,
            worksite_state TEXT,
            wage_from REAL,
            wage_to REAL,
            wage_unit TEXT,
            prevailing_wage REAL,
            pw_unit TEXT,
            pw_wage_level TEXT,
            h1b_dependent TEXT,
            willful_violator TEXT,
            annual_wage_from REAL,
            annual_wage_to REAL,
            fiscal_year INTEGER,
            source_file TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_employer_name ON lca_records(employer_name)",
        "CREATE INDEX IF NOT EXISTS idx_worksite_state ON lca_records(worksite_state)",
        "CREATE INDEX IF NOT EXISTS idx_soc_code ON lca_records(soc_code)",
        "CREATE INDEX IF NOT EXISTS idx_fiscal_year ON lca_records(fiscal_year)",
        "CREATE INDEX IF NOT EXISTS idx_case_status ON lca_records(case_status)",
        "CREATE INDEX IF NOT EXISTS idx_job_title ON lca_records(job_title)",
        """CREATE TABLE IF NOT EXISTS career_urls (
            employer_name TEXT PRIMARY KEY,
            career_url TEXT,
            looked_up_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS saved_companies (
            employer_name TEXT PRIMARY KEY,
            status TEXT DEFAULT 'Interested',
            role TEXT DEFAULT '',
            saved_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS company_tags (
            employer_name TEXT PRIMARY KEY,
            chinese_affiliated INTEGER DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS company_cn_scores (
            employer_name TEXT PRIMARY KEY,
            cn_score INTEGER DEFAULT 0,
            cn_label TEXT DEFAULT ''
        )""",
        """CREATE TABLE IF NOT EXISTS job_applications (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            company TEXT NOT NULL,
            job_title TEXT NOT NULL DEFAULT '',
            job_urls TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL DEFAULT 'Interested',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )""",
    ]
    for stmt in stmts:
        conn.execute(stmt)
    conn.commit()
    conn.close()


def insert_records(records: list[dict]):
    """Bulk upsert LCA records into lca_records using execute_values."""
    if not records:
        return
    cols = [
        "case_number", "case_status", "received_date", "decision_date",
        "visa_class", "employer_name", "trade_name_dba", "employer_city",
        "employer_state", "naics_code", "job_title", "soc_code", "soc_title",
        "full_time_position", "begin_date", "end_date", "total_worker_positions",
        "worksite_city", "worksite_county", "worksite_state",
        "wage_from", "wage_to", "wage_unit", "prevailing_wage", "pw_unit",
        "pw_wage_level", "h1b_dependent", "willful_violator",
        "annual_wage_from", "annual_wage_to", "fiscal_year", "source_file",
    ]
    col_names = ", ".join(cols)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "case_number")
    sql = f"""
        INSERT INTO lca_records ({col_names}) VALUES %s
        ON CONFLICT (case_number) DO UPDATE SET {update_set}
    """
    rows = [tuple(r.get(c) for c in cols) for r in records]
    pg = psycopg2.connect(_get_database_url())
    cur = pg.cursor()
    psycopg2.extras.execute_values(cur, sql, rows, page_size=1000)
    pg.commit()
    pg.close()


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    raw = psycopg2.connect(_get_database_url())
    try:
        df = pd.read_sql_query(sql, raw, params=params if params else None)
    finally:
        raw.close()
    return df


def get_distinct_values(column: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        f"SELECT DISTINCT {column} FROM lca_records WHERE {column} IS NOT NULL ORDER BY {column}"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]
