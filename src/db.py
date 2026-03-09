import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "h1b.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_tables():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lca_records (
            case_number       TEXT PRIMARY KEY,
            case_status       TEXT,
            received_date     TEXT,
            decision_date     TEXT,
            visa_class        TEXT,
            employer_name     TEXT,
            trade_name_dba    TEXT,
            employer_city     TEXT,
            employer_state    TEXT,
            naics_code        TEXT,
            job_title         TEXT,
            soc_code          TEXT,
            soc_title         TEXT,
            full_time_position TEXT,
            begin_date        TEXT,
            end_date          TEXT,
            total_worker_positions INTEGER,
            worksite_city     TEXT,
            worksite_county   TEXT,
            worksite_state    TEXT,
            wage_from         REAL,
            wage_to           REAL,
            wage_unit         TEXT,
            prevailing_wage   REAL,
            pw_unit           TEXT,
            pw_wage_level     TEXT,
            h1b_dependent     TEXT,
            willful_violator  TEXT,
            annual_wage_from  REAL,
            annual_wage_to    REAL,
            fiscal_year       INTEGER,
            source_file       TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_employer_name ON lca_records(employer_name);
        CREATE INDEX IF NOT EXISTS idx_worksite_state ON lca_records(worksite_state);
        CREATE INDEX IF NOT EXISTS idx_soc_code ON lca_records(soc_code);
        CREATE INDEX IF NOT EXISTS idx_fiscal_year ON lca_records(fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_case_status ON lca_records(case_status);
        CREATE INDEX IF NOT EXISTS idx_job_title ON lca_records(job_title);

        CREATE TABLE IF NOT EXISTS career_urls (
            employer_name TEXT PRIMARY KEY,
            career_url    TEXT,
            looked_up_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS saved_companies (
            employer_name TEXT PRIMARY KEY,
            saved_at TEXT
        );
    """)
    conn.commit()
    conn.close()


def insert_records(records: list[dict]):
    """Insert/replace records into lca_records. Each dict should have matching column keys."""
    if not records:
        return
    conn = get_connection()
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
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    sql = f"INSERT OR REPLACE INTO lca_records ({col_names}) VALUES ({placeholders})"
    rows = []
    for r in records:
        rows.append(tuple(r.get(c) for c in cols))
    conn.executemany(sql, rows)
    conn.commit()
    conn.close()


def query(sql: str, params: tuple = ()):
    conn = get_connection()
    cursor = conn.execute(sql, params)
    results = cursor.fetchall()
    conn.close()
    return results


def query_df(sql: str, params: tuple = ()):
    import pandas as pd
    conn = get_connection()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


def get_distinct_values(column: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        f"SELECT DISTINCT {column} FROM lca_records WHERE {column} IS NOT NULL ORDER BY {column}"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]
