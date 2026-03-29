"""
Load all Workday companies from the GitHub slug index into company_ats
by matching slug/domain against LCA employer names already in the DB.

Strategy:
  1. Fetch all 1,199 Workday entries from the GitHub index (slug -> URL)
  2. Load all LCA employer names from the DB
  3. For each Workday slug, try to fuzzy-match against an LCA employer name
  4. Upsert matches into company_ats

Usage:
    python load_workday_index.py [--dry-run] [--min-score 60]
"""

from __future__ import annotations
import argparse
import re
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; H1BEE/1.0)"}
WORKDAY_INDEX_URL = "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/workday_companies.json"

_LEGAL_SUFFIXES = re.compile(
    r'\b(inc|llc|corp|ltd|co|pllc|pc|lp|llp|group|holdings|'
    r'technologies|technology|solutions|services|systems|global|'
    r'international|enterprises|consulting|labs|lab|usa)\b\.?',
    re.IGNORECASE,
)


def fetch_workday_index() -> dict[str, str]:
    """Returns {slug: full_workday_url}."""
    r = requests.get(WORKDAY_INDEX_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    result = {}
    for entry in r.json():
        parts = str(entry).split("|")
        if len(parts) == 3:
            slug, instance, site = parts
            result[slug] = f"https://{slug}.{instance}.myworkdayjobs.com/{site}"
    return result


def normalize(name: str) -> str:
    """Normalize a name for matching: lowercase, strip legal suffixes, strip non-alnum."""
    n = name.lower()
    n = _LEGAL_SUFFIXES.sub("", n)
    n = re.sub(r"[^a-z0-9]", "", n)
    return n.strip()


def load_lca_employers(conn) -> list[tuple[str, str]]:
    """Return list of (employer_key, normalized) from lca_employer_stats."""
    cur = conn.execute(
        "SELECT DISTINCT employer_key FROM lca_employer_stats ORDER BY employer_key"
    )
    rows = cur.fetchall()
    return [(row[0], normalize(row[0])) for row in rows]


def match_slug_to_employer(slug: str, employers: list[tuple[str, str]]) -> str | None:
    """
    Try to find an LCA employer name that matches the Workday slug.
    Slug is already a cleaned lowercase string like 'marriott', 'regeneron'.
    """
    slug_norm = normalize(slug)
    if not slug_norm or len(slug_norm) < 3:
        return None

    # Exact match
    for name, norm in employers:
        if norm == slug_norm:
            return name

    # Slug is a prefix of the employer's normalized name (e.g. "amazon" in "amazonwebservices")
    for name, norm in employers:
        if norm.startswith(slug_norm) and len(slug_norm) / len(norm) >= 0.7:
            return name

    # Employer's normalized name starts with slug (e.g. "marriott" in "marriottinternational")
    for name, norm in employers:
        if norm.startswith(slug_norm) and len(slug_norm) >= 5:
            return name

    # Slug contains employer name or vice versa (loose)
    for name, norm in employers:
        if len(norm) >= 5 and slug_norm.startswith(norm):
            return name

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-slug-len", type=int, default=4,
                        help="Skip slugs shorter than this")
    args = parser.parse_args()

    print("Step 1: Fetching Workday slug index from GitHub...")
    workday_map = fetch_workday_index()
    print(f"  Loaded {len(workday_map)} Workday entries")

    print("\nStep 2: Connecting to DB and loading LCA employer names...")
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from db import get_connection
    conn = get_connection()
    employers = load_lca_employers(conn)
    print(f"  Loaded {len(employers)} LCA employer names")

    print("\nStep 3: Matching slugs to LCA employers...")
    matched: list[tuple[str, str]] = []   # (employer_name, workday_url)
    unmatched: list[str] = []

    for slug, url in sorted(workday_map.items()):
        if len(slug) < args.min_slug_len:
            continue
        employer = match_slug_to_employer(slug, employers)
        if employer:
            matched.append((employer, url))
        else:
            unmatched.append(slug)

    print(f"  Matched:   {len(matched)}")
    print(f"  Unmatched: {len(unmatched)}")

    if matched:
        print("\nSample matches:")
        for emp, url in matched[:20]:
            print(f"  {emp!r:50s} -> {url}")

    print(f"\nStep 4: Upserting {len(matched)} records into company_ats...")
    if args.dry_run:
        print("  [DRY RUN] Skipping DB write.")
    else:
        sql = """
            INSERT INTO company_ats (employer_name, ats_platform, ats_url)
            VALUES (%s, %s, %s)
            ON CONFLICT (employer_name, ats_platform) DO UPDATE
                SET ats_url = EXCLUDED.ats_url
        """
        rows = [(emp, "workday", url) for emp, url in matched]
        conn.executemany(sql, rows)
        conn.commit()
        print(f"  Done. {len(rows)} rows upserted.")

    conn.close()

    if unmatched[:30]:
        print(f"\nFirst 30 unmatched slugs (not in LCA records):")
        for s in unmatched[:30]:
            print(f"  {s} -> {workday_map[s]}")


if __name__ == "__main__":
    main()
