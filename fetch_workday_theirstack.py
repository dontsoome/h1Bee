"""
Fetch US companies that use Workday from TheirStack API,
cross-reference with our GitHub slug index, probe unknowns,
then upsert discovered Workday URLs into company_ats.

Usage:
    python fetch_workday_theirstack.py [--dry-run] [--max-pages N] [--min-employees N]
"""

from __future__ import annotations
import argparse
import os
import re
import sys
import time
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

THEIRSTACK_API_KEY = os.environ.get("THEIRSTACK_API_KEY", "")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; H1BEE/1.0)"}

# ── TheirStack pagination ──────────────────────────────────────────────────────

def fetch_theirstack_page(page: int, min_employees: int = 100) -> list[dict]:
    """Fetch one page of US Workday companies from TheirStack."""
    payload = {
        "company_technology_slug_or": ["workday"],
        "company_country_code_or": ["US"],
        "limit": 25,
        "page": page,
    }
    if min_employees > 0:
        payload["min_employee_count"] = min_employees

    r = requests.post(
        "https://api.theirstack.com/v1/companies/search",
        json=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {THEIRSTACK_API_KEY}",
        },
        timeout=15,
    )
    if r.status_code != 200:
        print(f"  TheirStack error {r.status_code}: {r.text[:200]}")
        return []
    data = r.json()
    if "error" in data:
        print(f"  TheirStack API error: {data['error']}")
        return []
    return data.get("data", [])


def fetch_all_companies(max_pages: int, min_employees: int) -> list[dict]:
    """Paginate through TheirStack until exhausted or max_pages reached."""
    companies = []
    for page in range(max_pages):
        print(f"  Fetching page {page} ...", end=" ", flush=True)
        batch = fetch_theirstack_page(page, min_employees)
        print(f"{len(batch)} companies")
        if not batch:
            break
        companies.extend(batch)
        time.sleep(0.5)  # be polite
    return companies


# ── Workday slug index (same as scraper) ──────────────────────────────────────

_WORKDAY_INDEX_URL = "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/workday_companies.json"
_workday_map: dict[str, str] = {}  # slug → full URL
_index_loaded = False
_index_lock = threading.Lock()


def load_workday_index() -> dict[str, str]:
    global _workday_map, _index_loaded
    with _index_lock:
        if _index_loaded:
            return _workday_map
        try:
            r = requests.get(_WORKDAY_INDEX_URL, headers=HEADERS, timeout=15)
            r.raise_for_status()
            for entry in r.json():
                parts = str(entry).split("|")
                if len(parts) == 3:
                    company_slug, instance, site = parts
                    _workday_map[company_slug] = (
                        f"https://{company_slug}.{instance}.myworkdayjobs.com/{site}"
                    )
            print(f"  Loaded {len(_workday_map)} entries from Workday slug index.")
        except Exception as e:
            print(f"  Warning: could not load Workday index: {e}")
        _index_loaded = True
    return _workday_map


# ── Slug derivation from company name / domain ────────────────────────────────

_LEGAL_SUFFIXES = re.compile(
    r'\b(inc|llc|corp|ltd|co|pllc|pc|lp|llp|group|holdings|'
    r'technologies|technology|solutions|services|systems|global|'
    r'international|enterprises|consulting|labs|lab)\b\.?',
    re.IGNORECASE,
)


def _slug_candidates(name: str, domain: str) -> list[str]:
    candidates = []

    # From domain: "marriott.com" → "marriott"
    if domain:
        dom_slug = domain.split(".")[0].lower()
        if dom_slug:
            candidates.append(dom_slug)

    # From company name
    clean = name.lower()
    clean = _LEGAL_SUFFIXES.sub("", clean)
    clean = re.sub(r"[^a-z0-9\s-]", "", clean).strip()
    words = clean.split()
    if words:
        candidates.append(words[0])
        if len(words) >= 2:
            candidates.append(f"{words[0]}-{words[1]}")
            candidates.append("".join(words[:2]))
        candidates.append("".join(words))

    # Deduplicate preserving order
    seen: set[str] = set()
    return [c for c in candidates if c and len(c) >= 2 and not (c in seen or seen.add(c))]  # type: ignore


def lookup_in_index(name: str, domain: str, workday_map: dict[str, str]) -> str | None:
    """Check if any slug candidate is in our Workday index. Returns URL or None."""
    for slug in _slug_candidates(name, domain):
        if slug in workday_map:
            return workday_map[slug]
        # Prefix match (e.g., "amazon" matches "amazon-corporate")
        for key in workday_map:
            if key.startswith(slug) or slug.startswith(key):
                return workday_map[key]
    return None


# ── Workday URL probe for companies not in index ─────────────────────────────

_COMMON_BOARDS = [
    "External_Careers", "ExternalCareers", "External-Careers",
    "Careers", "careers", "External_Career_Site", "CareerSite",
    "US_External", "External", "jobs", "Jobs",
]
_WD_INSTANCES = ["wd1", "wd3", "wd5", "wd12"]


def _probe_workday_url(slug: str, board: str) -> str | None:
    """Return URL if this slug+board combination returns jobs, else None."""
    for wdN in _WD_INSTANCES:
        base = f"https://{slug}.{wdN}.myworkdayjobs.com"
        api_url = f"{base}/wday/cxs/{slug}/{board}/jobs"
        try:
            r = requests.post(
                api_url,
                json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("jobPostings") or data.get("total", 0) > 0:
                    return f"{base}/en-US/{board}"
        except Exception:
            pass
    return None


def discover_workday_url(name: str, domain: str) -> str | None:
    """Try to probe a company's Workday URL by slug+board combinations."""
    candidates = _slug_candidates(name, domain)
    tasks = [(slug, board) for slug in candidates for board in _COMMON_BOARDS]

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_probe_workday_url, slug, board): (slug, board)
                   for slug, board in tasks}
        for fut in as_completed(futures):
            try:
                url = fut.result()
                if url:
                    return url
            except Exception:
                pass
    return None


# ── Database upsert ───────────────────────────────────────────────────────────

def upsert_to_db(records: list[dict], dry_run: bool):
    """
    records = [{"employer_name": ..., "ats_url": ..., "ats_platform": "workday"}]
    """
    if not records:
        return

    if dry_run:
        print(f"\n[DRY RUN] Would upsert {len(records)} records:")
        for r in records[:20]:
            print(f"  {r['employer_name']} → {r['ats_url']}")
        if len(records) > 20:
            print(f"  ... and {len(records) - 20} more")
        return

    from src.db import get_conn
    conn = get_conn()
    sql = """
        INSERT INTO company_ats (employer_name, ats_platform, ats_url)
        VALUES (%s, %s, %s)
        ON CONFLICT (employer_name) DO UPDATE
            SET ats_platform = EXCLUDED.ats_platform,
                ats_url      = EXCLUDED.ats_url
    """
    rows = [(r["employer_name"], "workday", r["ats_url"]) for r in records]
    conn.executemany(sql, rows)
    conn.commit()
    conn.close()
    print(f"  Upserted {len(rows)} rows into company_ats.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch Workday companies from TheirStack and upsert into DB.")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to DB")
    parser.add_argument("--max-pages", type=int, default=40, help="Max TheirStack pages to fetch (25/page)")
    parser.add_argument("--min-employees", type=int, default=100, help="Minimum employee count filter")
    parser.add_argument("--skip-probe", action="store_true", help="Skip probing for companies not in index")
    args = parser.parse_args()

    if not THEIRSTACK_API_KEY:
        print("ERROR: THEIRSTACK_API_KEY not set in .env")
        sys.exit(1)

    print(f"Step 1: Loading Workday slug index from GitHub...")
    workday_map = load_workday_index()

    print(f"\nStep 2: Fetching US Workday companies from TheirStack (max {args.max_pages} pages)...")
    companies = fetch_all_companies(args.max_pages, args.min_employees)
    print(f"  Total companies fetched: {len(companies)}")

    print(f"\nStep 3: Cross-referencing with Workday index...")
    found_in_index: list[dict] = []
    not_in_index: list[dict] = []

    for c in companies:
        name = c.get("name", "")
        domain = c.get("domain", "") or ""
        url = lookup_in_index(name, domain, workday_map)
        if url:
            found_in_index.append({"employer_name": name, "ats_url": url})
        else:
            not_in_index.append(c)

    print(f"  Found in index:  {len(found_in_index)}")
    print(f"  Not in index:    {len(not_in_index)}")

    # Probe companies not in index
    probe_found: list[dict] = []
    if not args.skip_probe and not_in_index:
        print(f"\nStep 4: Probing {len(not_in_index)} companies not in index (this may take a while)...")
        for i, c in enumerate(not_in_index, 1):
            name = c.get("name", "")
            domain = c.get("domain", "") or ""
            print(f"  [{i}/{len(not_in_index)}] {name} ({domain})", end=" ... ", flush=True)
            url = discover_workday_url(name, domain)
            if url:
                print(f"FOUND: {url}")
                probe_found.append({"employer_name": name, "ats_url": url})
            else:
                print("not found")
    else:
        print(f"\nStep 4: Skipping probe (--skip-probe flag set)")

    all_records = found_in_index + probe_found
    print(f"\nTotal Workday URLs discovered: {len(all_records)}")
    print(f"  From index: {len(found_in_index)}")
    print(f"  From probe: {len(probe_found)}")
    print(f"  Unresolved: {len(not_in_index) - len(probe_found)}")

    print(f"\nStep 5: Upserting to database...")
    upsert_to_db(all_records, dry_run=args.dry_run)

    if not_in_index and args.skip_probe:
        print(f"\nUnresolved companies (run without --skip-probe to try probing):")
        for c in not_in_index[:20]:
            print(f"  {c['name']} | {c.get('domain')} | {c.get('employee_count')} employees")
        if len(not_in_index) > 20:
            print(f"  ... and {len(not_in_index) - 20} more")


if __name__ == "__main__":
    main()
