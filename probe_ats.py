"""
Probe all employers in lca_records to detect their ATS platform.

Run from project root:
    python probe_ats.py               # probe all unprobed employers
    python probe_ats.py --limit 500   # probe first 500 (good for a test run)
    python probe_ats.py --reprobe     # re-probe everything (overwrites existing results)
    python probe_ats.py --workers 30  # increase parallelism (default 20)
"""

from __future__ import annotations
import os, sys, re, time, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import requests
import psycopg2
import psycopg2.extras
from db import _get_database_url, query_df

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; H1BEE/1.0)"}
TIMEOUT = 5

# Legal entity suffixes to strip when building slug candidates
_LEGAL = re.compile(
    r"\b(llc|inc|corp|corporation|ltd|limited|co|company|incorporated|"
    r"lp|llp|na|pc|pllc|plc|group|holding|holdings|solutions|services|"
    r"technologies|technology|systems|associates|partners|consulting|"
    r"international|global|enterprises|ventures|labs)\b\.?",
    re.IGNORECASE,
)

# ATS probe endpoints — {slug} is replaced per attempt
ATS_PROBES = {
    "greenhouse": "https://api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever":      "https://api.lever.co/v0/postings/{slug}?limit=1",
    "ashby":      "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


def _slugify(name: str) -> list[str]:
    """Generate URL slug candidates from an ALL-CAPS employer name."""
    s = name.lower()
    s = _LEGAL.sub(" ", s)
    s = re.sub(r"[^\w\s]", " ", s)   # remove punctuation
    # Drop purely numeric tokens (e.g. "1 TO 1 THERAPIES" → keep only "to", "therapies")
    words = [w for w in s.split() if not w.isdigit()]
    if not words:
        return []

    full_hyphen = "-".join(words)
    full_concat = "".join(words)

    candidates = [full_hyphen, full_concat]

    # Only add first-word slug when the company is effectively single-word after stripping.
    # Multi-word companies like "UNIVERSITY OF MICHIGAN" must not emit "university" alone —
    # that slug belongs to an unrelated company on the ATS.
    meaningful = [w for w in words if len(w) >= 4]
    if len(meaningful) == 1:
        candidates.append(meaningful[0])

    seen, out = set(), []
    for candidate in candidates:
        # Skip slugs that are too short or purely numeric — high false-positive risk
        if len(candidate) >= 4 and not candidate.isdigit():
            if candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


def _has_jobs(response: requests.Response) -> bool:
    """Return True if the JSON response looks like a real jobs listing."""
    try:
        data = response.json()
    except Exception:
        return False
    # Greenhouse: {"jobs": [...], "meta": {...}}
    # Lever:      [{"text": "Job Title", ...}, ...]  — empty list = valid slug but no openings
    # Ashby:      {"jobPostings": [...]}
    if isinstance(data, dict):
        return "jobs" in data or "jobPostings" in data
    if isinstance(data, list):
        return len(data) > 0  # require at least one posting to avoid false positives
    return False


def _greenhouse_name_matches(slug: str, employer_name: str) -> bool:
    """
    Verify a Greenhouse slug actually belongs to this employer.
    GET /v1/boards/{slug} returns {"name": "Actual Company Name", ...}.
    We do a loose token-overlap check to handle name variations.
    """
    try:
        r = requests.get(
            f"https://api.greenhouse.io/v1/boards/{slug}",
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return False
        board_name = r.json().get("name", "").lower()
    except Exception:
        return False

    # Strip legal suffixes and punctuation from both names for comparison
    def _tokens(s: str) -> set[str]:
        s = _LEGAL.sub(" ", s.lower())
        s = re.sub(r"[^\w\s]", " ", s)
        return {w for w in s.split() if len(w) >= 3 and not w.isdigit()}

    employer_tokens = _tokens(employer_name)
    board_tokens    = _tokens(board_name)
    if not employer_tokens or not board_tokens:
        return False

    # At least 50% of the shorter name's tokens must appear in the other
    overlap = employer_tokens & board_tokens
    min_len = min(len(employer_tokens), len(board_tokens))
    return len(overlap) / min_len >= 0.5


def _ashby_name_matches(response: requests.Response, employer_name: str) -> bool:
    """
    Verify an Ashby board belongs to this employer.
    Ashby returns {"organization": {"name": "Actual Company"}, "jobPostings": [...]}
    """
    try:
        org_name = response.json().get("organization", {}).get("name", "")
    except Exception:
        return False
    if not org_name:
        return False

    def _tokens(s: str) -> set[str]:
        s = _LEGAL.sub(" ", s.lower())
        s = re.sub(r"[^\w\s]", " ", s)
        return {w for w in s.split() if len(w) >= 3 and not w.isdigit()}

    employer_tokens = _tokens(employer_name)
    board_tokens    = _tokens(org_name)
    if not employer_tokens or not board_tokens:
        return False

    overlap = employer_tokens & board_tokens
    min_len = min(len(employer_tokens), len(board_tokens))
    return len(overlap) / min_len >= 0.5


def probe_company(employer_name: str) -> dict:
    """Try every ATS × slug combination. Returns first confirmed match."""
    slugs = _slugify(employer_name)
    for ats, url_template in ATS_PROBES.items():
        for slug in slugs:
            url = url_template.format(slug=slug)
            try:
                r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                if r.status_code == 200 and _has_jobs(r):
                    # Verify the board actually belongs to this employer
                    if ats == "greenhouse" and not _greenhouse_name_matches(slug, employer_name):
                        continue
                    if ats == "ashby" and not _ashby_name_matches(r, employer_name):
                        continue
                    return {
                        "employer_name": employer_name,
                        "ats_platform":  ats,
                        "ats_url":       url,
                        "auto_detected": True,
                    }
            except Exception:
                continue

    return {
        "employer_name": employer_name,
        "ats_platform":  "unknown",
        "ats_url":       "",
        "auto_detected": True,
    }


def _write_results(results: list[dict]):
    now = datetime.now(timezone.utc)
    rows = [
        (r["employer_name"], r["ats_platform"], r["ats_url"], r["auto_detected"], now)
        for r in results
    ]
    pg = psycopg2.connect(_get_database_url())
    cur = pg.cursor()
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO company_ats (employer_name, ats_platform, ats_url, auto_detected, probed_at)
           VALUES %s
           ON CONFLICT (employer_name) DO UPDATE SET
               ats_platform  = EXCLUDED.ats_platform,
               ats_url       = EXCLUDED.ats_url,
               auto_detected = EXCLUDED.auto_detected,
               probed_at     = EXCLUDED.probed_at""",
        rows,
        page_size=500,
    )
    pg.commit()
    pg.close()


def main():
    parser = argparse.ArgumentParser(description="Probe employer ATS platforms")
    parser.add_argument("--limit",   type=int, default=0,  help="Max employers to probe (0 = all)")
    parser.add_argument("--workers", type=int, default=20, help="Parallel HTTP workers")
    parser.add_argument("--reprobe", action="store_true",  help="Re-probe already detected companies")
    args = parser.parse_args()

    if args.reprobe:
        sql = "SELECT DISTINCT employer_name FROM lca_records ORDER BY employer_name"
    else:
        sql = """
            SELECT DISTINCT l.employer_name
            FROM lca_records l
            LEFT JOIN company_ats a ON l.employer_name = a.employer_name
            WHERE a.employer_name IS NULL
            ORDER BY l.employer_name
        """

    employers = query_df(sql)["employer_name"].tolist()
    if args.limit:
        employers = employers[:args.limit]

    total = len(employers)
    if total == 0:
        print("All employers already probed. Use --reprobe to re-check.")
        return

    print(f"Probing {total:,} employers  |  workers={args.workers}  |  ATS: {', '.join(ATS_PROBES)}")
    print("─" * 60)

    results, found, batch = [], 0, []
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(probe_company, name): name for name in employers}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            batch.append(result)
            if result["ats_platform"] != "unknown":
                found += 1

            # Flush to DB every 200 results to preserve progress
            if len(batch) >= 200:
                _write_results(batch)
                batch = []

            if i % 200 == 0 or i == total:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (total - i) / rate if rate > 0 else 0
                print(f"  {i:>6,}/{total:,}  detected={found}  {rate:.1f}/s  ETA {eta/60:.1f}m")

    if batch:
        _write_results(batch)

    # Summary
    counts: dict[str, int] = {}
    for r in results:
        counts[r["ats_platform"]] = counts.get(r["ats_platform"], 0) + 1

    print("\nResults:")
    for platform, count in sorted(counts.items(), key=lambda x: -x[1]):
        bar = "█" * min(40, count * 40 // max(counts.values()))
        print(f"  {platform:<20} {count:>6,}  {bar}")
    print(f"\n  Detected: {found:,} / {total:,}  ({found/total*100:.1f}%)")
    print("Done!")


if __name__ == "__main__":
    main()
