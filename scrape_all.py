"""
Batch scrape job listings for all ATS-detected employers.

Run from project root:
    python scrape_all.py                          # scrape companies not scraped in last 24h
    python scrape_all.py --all                    # re-scrape everything
    python scrape_all.py --platform greenhouse    # single platform only
    python scrape_all.py --workers 25             # parallelism (default 10)
    python scrape_all.py --limit 200              # cap at 200 companies
"""

from __future__ import annotations
import os, sys, time, argparse
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from db import query_df, upsert_job_listings, mark_ats_inactive
import re
from scraper import scrape_greenhouse, scrape_lever, scrape_ashby, scrape_workday, scrape_smartrecruiters, scrape_jazzhr, scrape_icims


def _parse_ats_info(platform: str, ats_url: str) -> tuple[str, str, str]:
    """
    Returns (slug, board, url_slug) from a stored ats_url.
    slug     — for scraper calls (iCIMS has prefix stripped)
    board    — Workday board name
    url_slug — full subdomain for iCIMS (e.g. 'careers-amazon')
    """
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
        url_slug = host.split(".")[0]  # e.g. "careers-amazon"
        slug = re.sub(r"^(careers?|jobs?|recruiting|talent|hr)-", "", url_slug, flags=re.IGNORECASE)
        return slug, "", url_slug

    elif platform == "workday":
        slug = host.split(".")[0]
        board = path_parts[1] if len(path_parts) >= 2 else (path_parts[0] if path_parts else "")
        return slug, board, slug

    return "", "", ""


def _scrape_one(employer_name: str, platform: str, ats_url: str) -> tuple[str, list[dict], str]:
    slug, board, url_slug = _parse_ats_info(platform, ats_url)
    if not slug and not url_slug:
        return employer_name, [], platform

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

    return employer_name, jobs, platform


def main():
    parser = argparse.ArgumentParser(description="Batch scrape ATS job listings")
    parser.add_argument("--limit",    type=int, default=0,     help="Max companies to scrape (0 = all)")
    parser.add_argument("--workers",  type=int, default=10,    help="Parallel scrape workers (default 10)")
    parser.add_argument("--all",      action="store_true",     help="Re-scrape even recently scraped companies")
    parser.add_argument("--platform", type=str, default=None,  help="Scrape a single platform only (e.g. greenhouse)")
    args = parser.parse_args()

    platform_filter = f"AND a.ats_platform = '{args.platform}'" if args.platform else ""

    if args.all:
        sql = f"""
            SELECT employer_name, ats_platform, ats_url
            FROM company_ats
            WHERE ats_platform NOT IN ('unknown')
              AND is_active = TRUE
            {platform_filter.replace('a.ats_platform', 'ats_platform')}
            ORDER BY employer_name
        """
    else:
        sql = f"""
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
            ORDER BY a.employer_name
        """

    df = query_df(sql)
    if args.limit:
        df = df.head(args.limit)

    total = len(df)
    if total == 0:
        print("All companies scraped recently. Use --all to re-scrape.")
        return

    platform_label = args.platform or "all platforms"
    print(f"Scraping {total:,} companies  |  platform={platform_label}  |  workers={args.workers}")
    print("-" * 60)

    scraped, jobs_found = 0, 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_scrape_one, row["employer_name"], row["ats_platform"], row["ats_url"]): row["employer_name"]
            for _, row in df.iterrows()
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

            if i % 50 == 0 or i == total:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (total - i) / rate if rate > 0 else 0
                print(f"  {i:>5,}/{total:,}  companies_with_jobs={scraped}  total_jobs={jobs_found:,}  ETA {eta/60:.1f}m")

    elapsed = time.time() - start
    print(f"\nDone! Scraped {scraped:,} companies with jobs, {jobs_found:,} total listings in {elapsed/60:.1f}m")


if __name__ == "__main__":
    main()
