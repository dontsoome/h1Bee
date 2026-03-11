"""
Run CN affiliation scoring for all employers not yet in company_cn_scores.

Run locally after each new ingest:
    python src/score_companies.py
"""

from __future__ import annotations
import os
import sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

sys.path.insert(0, os.path.dirname(__file__))

import psycopg2.extras
from db import get_connection, _get_database_url
from heuristics import score_company, get_affiliation_label


def main():
    conn = get_connection()

    print("Finding unscored employers...")
    rows = conn.execute("""
        SELECT l.employer_name,
               MIN(l.trade_name_dba) AS trade_name_dba,
               MIN(l.employer_city)  AS employer_city
        FROM lca_records l
        LEFT JOIN company_cn_scores s ON l.employer_name = s.employer_name
        WHERE s.employer_name IS NULL
        GROUP BY l.employer_name
    """).fetchall()

    if not rows:
        print("All employers already scored.")
        conn.close()
        return

    print(f"Scoring {len(rows):,} employers...")
    batch = []
    for r in rows:
        s = score_company(r[0], r[1], r[2])
        label = get_affiliation_label(s)
        batch.append((r[0], s, label))

    raw = psycopg2.connect(_get_database_url())
    cur = raw.cursor()
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO company_cn_scores (employer_name, cn_score, cn_label) VALUES %s "
        "ON CONFLICT (employer_name) DO UPDATE SET cn_score=EXCLUDED.cn_score, cn_label=EXCLUDED.cn_label",
        batch,
        page_size=1000,
    )
    raw.commit()
    raw.close()
    conn.close()
    print(f"Done. {len(batch):,} employers scored.")


if __name__ == "__main__":
    main()
