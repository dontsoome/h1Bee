"""
Trim lca_records to relevant states only, then refresh materialized views.
Run from project root: python trim_data.py
"""

import os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import psycopg2
from db import _get_database_url

# States covering ~90%+ of H-1B activity
KEEP_STATES = (
    "NY", "NJ", "CA", "WA", "TX", "IL", "MA",
    "GA", "VA", "NC", "CO", "FL", "PA", "OH",
    "MN", "AZ", "MI", "UT", "OR", "MD", "CT",
)

conn = psycopg2.connect(_get_database_url())
conn.autocommit = True
cur = conn.cursor()

# Before count
cur.execute("SELECT COUNT(*) FROM lca_records")
before = cur.fetchone()[0]
print(f"Before: {before:,} rows")

placeholders = ",".join(["%s"] * len(KEEP_STATES))

print(f"Deleting records outside {len(KEEP_STATES)} states...", flush=True)
cur.execute(f"DELETE FROM lca_records WHERE worksite_state NOT IN ({placeholders})", KEEP_STATES)
deleted = cur.rowcount
print(f"Deleted {deleted:,} rows")

# After count
cur.execute("SELECT COUNT(*) FROM lca_records")
after = cur.fetchone()[0]
print(f"After:  {after:,} rows  ({before - after:,} removed, {after/before*100:.1f}% kept)")

print("\nRefreshing company_stats...", end=" ", flush=True)
cur.execute("REFRESH MATERIALIZED VIEW company_stats")
print("done")

try:
    print("Refreshing company_stats_nynj...", end=" ", flush=True)
    cur.execute("REFRESH MATERIALIZED VIEW company_stats_nynj")
    print("done")
except Exception:
    print("skipped (view may not exist yet)")

cur.close()
conn.close()
print("\nTrim complete!")
