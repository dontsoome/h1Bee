"""
One-time setup: create indexes and materialized view in Supabase.
Run from project root: python setup_supabase.py
"""

import os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import psycopg2
from db import _get_database_url

conn = psycopg2.connect(_get_database_url())
conn.autocommit = True
cur = conn.cursor()

steps = [
    ("Composite index: status+employer",
     "CREATE INDEX IF NOT EXISTS idx_status_employer ON lca_records(case_status, employer_name)"),
    ("Composite index: status+state+employer",
     "CREATE INDEX IF NOT EXISTS idx_status_state_employer ON lca_records(case_status, worksite_state, employer_name)"),
    ("Composite index: status+year+employer",
     "CREATE INDEX IF NOT EXISTS idx_status_year_employer ON lca_records(case_status, fiscal_year, employer_name)"),
    ("Composite index: employer+wage",
     "CREATE INDEX IF NOT EXISTS idx_employer_wage ON lca_records(employer_name, annual_wage_from)"),
    ("Drop old materialized view if exists",
     "DROP MATERIALIZED VIEW IF EXISTS company_stats"),
    ("Create materialized view company_stats", """
        CREATE MATERIALIZED VIEW company_stats AS
        SELECT
            employer_name,
            case_status,
            COUNT(*)                                 AS total_lcas,
            COUNT(DISTINCT job_title)                AS unique_roles,
            COUNT(DISTINCT worksite_state)           AS states_count,
            ROUND(MIN(annual_wage_from)::numeric, 0) AS min_salary,
            ROUND(AVG(annual_wage_from)::numeric, 0) AS avg_salary,
            ROUND(MAX(annual_wage_from)::numeric, 0) AS max_salary
        FROM lca_records
        GROUP BY employer_name, case_status
        WITH DATA
    """),
    ("Index on company_stats(case_status, total_lcas)",
     "CREATE INDEX ON company_stats(case_status, total_lcas DESC)"),
    ("Index on company_stats(employer_name)",
     "CREATE INDEX ON company_stats(employer_name)"),
    ("Enable pg_trgm extension",
     "CREATE EXTENSION IF NOT EXISTS pg_trgm"),
    ("Trigram index on lca_records(employer_name)",
     "CREATE INDEX IF NOT EXISTS idx_employer_trgm ON lca_records USING gin(employer_name gin_trgm_ops)"),
    ("Trigram index on company_stats(employer_name)",
     "CREATE INDEX IF NOT EXISTS idx_stats_employer_trgm ON company_stats USING gin(employer_name gin_trgm_ops)"),
]

for label, sql in steps:
    print(f"  {label}...", end=" ", flush=True)
    cur.execute(sql)
    print("done")

cur.close()
conn.close()
print("\nSetup complete!")
