"""
Load all ATS company slugs from data/ CSVs into company_ats.
Skips companies already in the table (ON CONFLICT DO NOTHING).

Run from project root:
    python load_all_ats.py
"""
from __future__ import annotations
import os, sys, csv, glob
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import psycopg2
from urllib.parse import urlparse

DATABASE_URL = os.environ["DATABASE_URL"]

# Build ATS URL from slug — must match what _parse_ats_info in scrape_all.py expects
def make_ats_url(platform: str, slug: str) -> str | None:
    if platform == "greenhouse":
        return f"https://boards.greenhouse.io/{slug}"
    elif platform == "lever":
        return f"https://jobs.lever.co/{slug}"
    elif platform == "ashby":
        return f"https://jobs.ashbyhq.com/{slug}"
    elif platform == "smartrecruiters":
        return f"https://jobs.smartrecruiters.com/{slug}"
    elif platform == "jazzhr":
        return f"https://{slug}.applytojob.com/apply"
    # workday and icims need more info than just a slug — skip for now
    return None


def main():
    data_dir = Path(__file__).parent / "data"
    csv_files = list(data_dir.glob("*.csv.csv")) + list(data_dir.glob("*.csv"))

    # Collect all (employer_name, platform, ats_url) rows
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()  # deduplicate by (slug, platform)

    for fpath in sorted(csv_files):
        with open(fpath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                slug = (row.get("slug") or "").strip()
                platform = (row.get("ats") or "").strip().lower()
                if not slug or not platform:
                    continue
                key = f"{platform}:{slug}"
                if key in seen:
                    continue
                seen.add(key)
                url = make_ats_url(platform, slug)
                if url:
                    rows.append((slug, platform, url))

    print(f"Found {len(rows)} unique company slugs across all CSVs")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    inserted = 0
    skipped = 0
    batch_size = 500

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        for slug, platform, url in batch:
            cur.execute("""
                INSERT INTO company_ats (employer_name, ats_platform, ats_url, auto_detected)
                VALUES (%s, %s, %s, false)
                ON CONFLICT (employer_name) DO NOTHING
            """, (slug, platform, url))
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
        print(f"  Processed {min(i + batch_size, len(rows))}/{len(rows)} — inserted {inserted}, skipped {skipped}")

    cur.close()
    conn.close()
    print(f"\nDone. Inserted {inserted} new companies, skipped {skipped} already existing.")


if __name__ == "__main__":
    main()
