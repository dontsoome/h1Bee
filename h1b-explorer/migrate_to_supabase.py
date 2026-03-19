"""
One-time migration: copy all data from local h1b.db (SQLite) to Supabase (PostgreSQL).

Usage:
    python migrate_to_supabase.py

Requires DATABASE_URL in .env pointing to your Supabase project.
"""

import os
import sys
import sqlite3

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "h1b.db")
BATCH_SIZE = 2000


def migrate():
    import psycopg2
    import psycopg2.extras

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)

    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: SQLite DB not found at {SQLITE_PATH}")
        sys.exit(1)

    print("Connecting to SQLite...")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    print("Connecting to Supabase...")
    pg_conn = psycopg2.connect(database_url)
    pg_cur = pg_conn.cursor()

    # ── Create tables ────────────────────────────────────────────────
    from db import create_tables
    print("Creating tables in Supabase...")
    create_tables()

    # ── Migrate lca_records ──────────────────────────────────────────
    print("\nMigrating lca_records...")
    rows = sqlite_conn.execute("SELECT * FROM lca_records").fetchall()
    cols = [d[0] for d in sqlite_conn.execute("PRAGMA table_info(lca_records)").fetchall()]
    # Use column names from PRAGMA
    cols = [row[1] for row in sqlite_conn.execute("PRAGMA table_info(lca_records)").fetchall()]
    print(f"  {len(rows):,} records to migrate")

    col_names = ", ".join(cols)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "case_number")
    sql = f"INSERT INTO lca_records ({col_names}) VALUES %s ON CONFLICT (case_number) DO UPDATE SET {update_set}"

    for i in range(0, len(rows), BATCH_SIZE):
        batch = [tuple(r) for r in rows[i:i + BATCH_SIZE]]
        psycopg2.extras.execute_values(pg_cur, sql, batch, page_size=500)
        pg_conn.commit()
        print(f"  Inserted {min(i + BATCH_SIZE, len(rows)):,}/{len(rows):,}")

    # ── Migrate career_urls ──────────────────────────────────────────
    print("\nMigrating career_urls...")
    try:
        rows = sqlite_conn.execute(
            "SELECT employer_name, career_url, looked_up_at FROM career_urls"
        ).fetchall()
        if rows:
            psycopg2.extras.execute_values(
                pg_cur,
                "INSERT INTO career_urls (employer_name, career_url, looked_up_at) VALUES %s "
                "ON CONFLICT (employer_name) DO UPDATE SET career_url=EXCLUDED.career_url, looked_up_at=EXCLUDED.looked_up_at",
                [tuple(r) for r in rows],
            )
            pg_conn.commit()
            print(f"  {len(rows):,} records migrated")
        else:
            print("  No records found")
    except Exception as e:
        pg_conn.rollback()
        print(f"  Skipped: {e}")

    # ── Migrate company_cn_scores ────────────────────────────────────
    print("\nMigrating company_cn_scores...")
    try:
        rows = sqlite_conn.execute(
            "SELECT employer_name, cn_score, cn_label FROM company_cn_scores"
        ).fetchall()
        if rows:
            psycopg2.extras.execute_values(
                pg_cur,
                "INSERT INTO company_cn_scores (employer_name, cn_score, cn_label) VALUES %s "
                "ON CONFLICT (employer_name) DO UPDATE SET cn_score=EXCLUDED.cn_score, cn_label=EXCLUDED.cn_label",
                [tuple(r) for r in rows],
            )
            pg_conn.commit()
            print(f"  {len(rows):,} records migrated")
        else:
            print("  No records found")
    except Exception as e:
        pg_conn.rollback()
        print(f"  Skipped: {e}")

    # ── Migrate company_tags ─────────────────────────────────────────
    print("\nMigrating company_tags...")
    try:
        rows = sqlite_conn.execute(
            "SELECT employer_name, chinese_affiliated FROM company_tags"
        ).fetchall()
        if rows:
            psycopg2.extras.execute_values(
                pg_cur,
                "INSERT INTO company_tags (employer_name, chinese_affiliated) VALUES %s "
                "ON CONFLICT (employer_name) DO UPDATE SET chinese_affiliated=EXCLUDED.chinese_affiliated",
                [tuple(r) for r in rows],
            )
            pg_conn.commit()
            print(f"  {len(rows):,} records migrated")
        else:
            print("  No records found")
    except Exception as e:
        pg_conn.rollback()
        print(f"  Skipped: {e}")

    # ── Migrate saved_companies ──────────────────────────────────────
    print("\nMigrating saved_companies...")
    try:
        rows = sqlite_conn.execute(
            "SELECT employer_name, status, role, saved_at FROM saved_companies"
        ).fetchall()
        if rows:
            psycopg2.extras.execute_values(
                pg_cur,
                "INSERT INTO saved_companies (employer_name, status, role, saved_at) VALUES %s "
                "ON CONFLICT (employer_name) DO UPDATE SET status=EXCLUDED.status, role=EXCLUDED.role, saved_at=EXCLUDED.saved_at",
                [tuple(r) for r in rows],
            )
            pg_conn.commit()
            print(f"  {len(rows):,} records migrated")
        else:
            print("  No records found")
    except Exception as e:
        pg_conn.rollback()
        print(f"  Skipped: {e}")

    # ── Migrate job_applications ─────────────────────────────────────
    print("\nMigrating job_applications...")
    try:
        rows = sqlite_conn.execute(
            "SELECT company, job_title, job_urls, stage, notes, created_at, updated_at FROM job_applications"
        ).fetchall()
        if rows:
            psycopg2.extras.execute_values(
                pg_cur,
                "INSERT INTO job_applications (company, job_title, job_urls, stage, notes, created_at, updated_at) VALUES %s",
                [tuple(r) for r in rows],
            )
            pg_conn.commit()
            print(f"  {len(rows):,} records migrated")
        else:
            print("  No records found")
    except Exception as e:
        pg_conn.rollback()
        print(f"  Skipped: {e}")

    sqlite_conn.close()
    pg_conn.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    migrate()
