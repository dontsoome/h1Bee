"""
Full overnight pipeline:
  1. Load all ATS slugs from data/ CSVs → company_ats (composite PK: employer_name + ats_platform)
  2. Probe every unverified/stale row → mark is_active TRUE/FALSE
  3. Scrape all active rows → job_listings
  4. Refresh materialized view

Run:
    python run_pipeline.py               # full pipeline
    python run_pipeline.py --skip-load   # skip CSV load (already loaded)
    python run_pipeline.py --skip-probe  # skip probe step
    python run_pipeline.py --workers 20  # parallelism (default 20)
"""

from __future__ import annotations
import os, sys, time, argparse, csv, requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent / "src"))

import psycopg2
import psycopg2.extras
from db import query_df, upsert_job_listings, mark_ats_inactive, get_connection

DATABASE_URL = os.environ["DATABASE_URL"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; H1BEE/1.0)"}
PROBE_TIMEOUT = 6


# ── Step 1: Load CSVs ─────────────────────────────────────────────────────────

def make_ats_url(platform: str, slug: str) -> str | None:
    if platform == "greenhouse":
        return f"https://boards.greenhouse.io/{slug}"
    if platform == "lever":
        return f"https://jobs.lever.co/{slug}"
    if platform == "ashby":
        return f"https://jobs.ashbyhq.com/{slug}"
    if platform == "smartrecruiters":
        return f"https://jobs.smartrecruiters.com/{slug}"
    if platform == "jazzhr":
        return f"https://{slug}.applytojob.com/apply"
    if platform == "icims":
        return f"https://{slug}.icims.com/jobs/search"
    return None


def load_csvs():
    print("\n── Step 1: Loading CSVs into company_ats ──")
    data_dir = Path(__file__).parent / "data"
    csv_files = list(data_dir.glob("*.csv.csv")) + list(data_dir.glob("*.csv"))

    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for fpath in sorted(csv_files):
        name = fpath.name.lower()
        if "lca" in name or "readme" in name:
            continue
        try:
            with open(fpath, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    platform = (row.get("ats") or "").strip().lower()
                    host = (row.get("url_host_name") or "").strip()

                    # Detect workday rows by platform column or url_host_name domain
                    if platform == "workday" or (not platform and "myworkdayjobs.com" in host):
                        platform = "workday"
                        if row.get("slug"):
                            slug = row["slug"].strip().lower()
                            board = (row.get("board") or "External").strip()
                            subdomain = "wd1"
                        elif host:
                            parts = host.split(".")
                            slug = parts[0].lower()
                            subdomain = parts[1] if len(parts) > 1 and parts[1].startswith("wd") else "wd1"
                            board = (row.get("board") or "").strip()
                            if not board:
                                path = (row.get("url_path") or "").strip("/")
                                board = path.split("/")[0] if path else "External"
                            board = board if board else "External"
                        else:
                            continue
                        key = f"workday:{slug}:{board}"
                        if key in seen:
                            continue
                        seen.add(key)
                        url = f"https://{slug}.{subdomain}.myworkdayjobs.com/{board}"
                        rows.append((slug, "workday", url))
                        continue

                    slug = (row.get("slug") or "").strip().lower()
                    if not slug or not platform:
                        continue
                    key = f"{platform}:{slug}"
                    if key in seen:
                        continue
                    seen.add(key)
                    url = make_ats_url(platform, slug)
                    if url:
                        rows.append((slug, platform, url))
        except Exception as e:
            print(f"  Warning: could not read {fpath.name}: {e}")

    print(f"  Found {len(rows):,} unique (slug, platform) pairs across all CSVs")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    inserted = skipped = 0
    batch_size = 500

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        for slug, platform, url in batch:
            cur.execute("""
                INSERT INTO company_ats (employer_name, ats_platform, ats_url, auto_detected, is_active)
                VALUES (%s, %s, %s, false, true)
                ON CONFLICT (employer_name, ats_platform) DO NOTHING
            """, (slug, platform, url))
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        conn.commit()

    cur.close()
    conn.close()
    print(f"  Inserted {inserted:,} new rows, skipped {skipped:,} already existing.")


# ── Step 2: Probe ─────────────────────────────────────────────────────────────

# Maps status codes to (is_active, reason)
def _classify_status(status: int) -> tuple[bool | None, str]:
    if status == 200:
        return True, "ok"
    if status in (404, 410):
        return False, f"http_{status}_not_found"
    if status in (401, 403):
        return False, f"http_{status}_unauthorized"
    if status == 429:
        return None, "rate_limited"       # transient — don't update
    if status >= 500:
        return None, f"http_{status}_server_error"  # transient
    return False, f"http_{status}_unknown"


def _probe_url(platform: str, slug: str, ats_url: str) -> tuple[bool | None, str]:
    """
    Returns (is_active, reason).
    None means transient error — don't update is_active.
    """
    try:
        parsed = urlparse(ats_url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        if platform == "greenhouse":
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                headers=HEADERS, timeout=PROBE_TIMEOUT,
            )
            return _classify_status(r.status_code)

        elif platform == "lever":
            r = requests.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json",
                headers=HEADERS, timeout=PROBE_TIMEOUT,
            )
            return _classify_status(r.status_code)

        elif platform == "ashby":
            r = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                headers=HEADERS, timeout=PROBE_TIMEOUT,
            )
            return _classify_status(r.status_code)

        elif platform == "smartrecruiters":
            r = requests.get(
                f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                params={"limit": 1},
                headers=HEADERS, timeout=PROBE_TIMEOUT,
            )
            return _classify_status(r.status_code)

        elif platform == "jazzhr":
            r = requests.get(
                f"https://{slug}.applytojob.com/apply",
                headers=HEADERS, timeout=PROBE_TIMEOUT,
                allow_redirects=True,
            )
            # JazzHR returns 200 even for dead boards, but with no job links
            if r.status_code == 200:
                return True, "ok"
            return _classify_status(r.status_code)

        elif platform == "icims":
            host = parsed.hostname or ""
            url_slug = host.split(".")[0]
            r = requests.get(
                f"https://{url_slug}.icims.com/jobs/search",
                params={"ss": 1, "in_iframe": 1},
                headers=HEADERS, timeout=PROBE_TIMEOUT,
                allow_redirects=True,
            )
            return _classify_status(r.status_code)

        elif platform == "workday":
            # Workday: try the stored URL directly
            host = parsed.hostname or ""
            slug_wd = host.split(".")[0]
            board = path_parts[1] if len(path_parts) >= 2 else (path_parts[0] if path_parts else "")
            for wdN in ("wd1", "wd3", "wd5"):
                try:
                    r = requests.post(
                        f"https://{slug_wd}.{wdN}.myworkdayjobs.com/wday/cxs/{slug_wd}/{board}/jobs",
                        json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
                        headers={**HEADERS, "Content-Type": "application/json"},
                        timeout=PROBE_TIMEOUT,
                    )
                    if r.status_code == 200:
                        return True, "ok"
                    if r.status_code in (404, 410):
                        continue
                except Exception:
                    continue
            return False, "workday_all_instances_failed"

        return None, "unknown_platform"

    except requests.exceptions.Timeout:
        return None, "timeout"
    except requests.exceptions.ConnectionError:
        return None, "connection_error"
    except Exception as e:
        return None, f"exception_{type(e).__name__}"


def _probe_one(row: dict) -> tuple[str, str, bool | None, str]:
    employer = row["employer_name"]
    platform = row["ats_platform"]
    url = row["ats_url"]
    slug = urlparse(url).path.strip("/").split("/")[0] if platform not in ("jazzhr", "icims", "workday") else ""
    if not slug:
        # derive slug from url for jazzhr/icims/workday
        parsed = urlparse(url)
        host = parsed.hostname or ""
        slug = host.split(".")[0]

    is_active, reason = _probe_url(platform, slug, url)
    return employer, platform, is_active, reason


def update_probe_result(employer: str, platform: str, is_active: bool):
    conn = get_connection()
    conn.execute(
        """UPDATE company_ats
           SET is_active = %s, probed_at = NOW()
           WHERE employer_name = %s AND ats_platform = %s""",
        (is_active, employer, platform),
    )
    conn.commit()
    conn.close()


def probe_all(workers: int):
    print("\n── Step 2: Probing ATS URLs ──")
    # Only probe rows not yet probed or probed > 7 days ago
    rows = query_df("""
        SELECT employer_name, ats_platform, ats_url
        FROM company_ats
        WHERE ats_platform NOT IN ('unknown')
          AND (probed_at IS NULL OR probed_at < NOW() - INTERVAL '7 days')
        ORDER BY employer_name
    """)
    total = len(rows)
    if total == 0:
        print("  All rows probed recently. Skipping.")
        return

    print(f"  Probing {total:,} rows with {workers} workers...")
    active = inactive = skipped = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_probe_one, row): row["employer_name"]
            for _, row in rows.iterrows()
        }
        for i, future in enumerate(as_completed(futures), 1):
            employer, platform, is_active, reason = future.result()

            if is_active is True:
                update_probe_result(employer, platform, True)
                active += 1
            elif is_active is False:
                update_probe_result(employer, platform, False)
                inactive += 1
            else:
                skipped += 1  # transient error — leave is_active unchanged

            if i % 500 == 0 or i == total:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (total - i) / rate if rate > 0 else 0
                print(f"  {i:>6,}/{total:,}  active={active:,}  inactive={inactive:,}  skipped={skipped:,}  ETA {eta/60:.1f}m")

    print(f"  Done. Active={active:,}  Inactive={inactive:,}  Transient/skipped={skipped:,}")


# ── Step 3: Scrape ────────────────────────────────────────────────────────────

def scrape_all(workers: int, platforms: list[str] | None = None):
    print("\n── Step 3: Scraping active companies ──")
    from scraper import (scrape_greenhouse, scrape_lever, scrape_ashby,
                         scrape_workday, scrape_smartrecruiters,
                         scrape_jazzhr, scrape_icims)
    import re as _re

    def _parse_ats_info(platform: str, ats_url: str):
        parsed = urlparse(ats_url)
        host = parsed.hostname or ""
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if platform in ("greenhouse", "lever", "ashby", "smartrecruiters"):
            slug = path_parts[0] if path_parts else ""
            return slug, "", slug
        elif platform == "jazzhr":
            slug = host.split(".")[0]
            return slug, "", slug
        elif platform == "icims":
            url_slug = host.split(".")[0]
            slug = _re.sub(r"^(careers?|jobs?|recruiting|talent|hr)-", "", url_slug, flags=_re.IGNORECASE)
            return slug, "", url_slug
        elif platform == "workday":
            slug = host.split(".")[0]
            board = path_parts[1] if len(path_parts) >= 2 else (path_parts[0] if path_parts else "")
            return slug, board, slug
        return "", "", ""

    def _scrape_one(employer: str, platform: str, ats_url: str):
        slug, board, url_slug = _parse_ats_info(platform, ats_url)
        if not slug and not url_slug:
            return employer, [], platform
        try:
            if platform == "greenhouse":
                jobs = scrape_greenhouse(slug)
            elif platform == "lever":
                jobs = scrape_lever(slug)
            elif platform == "ashby":
                jobs = scrape_ashby(slug)
            elif platform == "workday":
                jobs = scrape_workday(slug, board)
            elif platform == "smartrecruiters":
                jobs = scrape_smartrecruiters(slug)
            elif platform == "jazzhr":
                jobs = scrape_jazzhr(slug)
            elif platform == "icims":
                jobs = scrape_icims(url_slug)
            else:
                jobs = []
        except Exception:
            jobs = []
        return employer, jobs, platform

    platform_filter = ""
    platform_params: tuple = ()
    if platforms:
        placeholders = ",".join(["%s"] * len(platforms))
        platform_filter = f"AND a.ats_platform IN ({placeholders})"
        platform_params = tuple(platforms)

    rows = query_df(f"""
        SELECT a.employer_name, a.ats_platform, a.ats_url
        FROM company_ats a
        LEFT JOIN (
            SELECT employer_name, MAX(scraped_at) AS last_scraped
            FROM job_listings
            GROUP BY employer_name
        ) j ON a.employer_name = j.employer_name
        WHERE a.ats_platform NOT IN ('unknown')
          AND a.is_active = TRUE
          AND (j.last_scraped IS NULL OR j.last_scraped < NOW() - INTERVAL '24 hours')
          {platform_filter}
        ORDER BY RANDOM()
    """, platform_params)

    total = len(rows)
    if total == 0:
        print("  All active companies scraped recently.")
        return

    print(f"  Scraping {total:,} companies with {workers} workers...")
    scraped = jobs_found = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_scrape_one, row["employer_name"], row["ats_platform"], row["ats_url"]): row["employer_name"]
            for _, row in rows.iterrows()
        }
        for i, future in enumerate(as_completed(futures), 1):
            employer, jobs, platform = future.result()
            if jobs is None:
                mark_ats_inactive(employer, platform)
            else:
                upsert_job_listings(employer, jobs, platform)
            if jobs:
                scraped += 1
                jobs_found += len(jobs)

            if i % 100 == 0 or i == total:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (total - i) / rate if rate > 0 else 0
                print(f"  {i:>6,}/{total:,}  with_jobs={scraped:,}  total_jobs={jobs_found:,}  ETA {eta/60:.1f}m")

    print(f"  Done. {scraped:,} companies with jobs, {jobs_found:,} listings.")


# ── Step 4: Refresh MV ────────────────────────────────────────────────────────

def refresh_mv():
    print("\n── Step 4: Refreshing materialized view ──")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    conn.cursor().execute("REFRESH MATERIALIZED VIEW CONCURRENTLY job_listings_enriched")
    conn.close()
    print("  Done.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Full H1BEE pipeline: load → probe → scrape → refresh")
    parser.add_argument("--skip-load",  action="store_true", help="Skip CSV load step")
    parser.add_argument("--skip-probe", action="store_true", help="Skip ATS probe step")
    parser.add_argument("--skip-scrape",action="store_true", help="Skip scrape step")
    parser.add_argument("--workers",    type=int, default=20, help="Workers for probe + scrape (default 20)")
    parser.add_argument("--platform",   type=str, default=None, help="Comma-separated platforms to scrape, e.g. greenhouse,lever,ashby")
    args = parser.parse_args()

    total_start = time.time()
    print("═" * 60)
    print("  H1BEE Pipeline")
    print("═" * 60)

    if not args.skip_load:
        load_csvs()

    if not args.skip_probe:
        probe_all(args.workers)

    if not args.skip_scrape:
        platforms = [p.strip() for p in args.platform.split(",")] if args.platform else None
        scrape_all(args.workers, platforms=platforms)

    refresh_mv()

    elapsed = time.time() - total_start
    print(f"\n═══ Pipeline complete in {elapsed/60:.1f} minutes ═══")


if __name__ == "__main__":
    main()
