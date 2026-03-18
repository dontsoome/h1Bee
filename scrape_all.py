"""
Batch scrape job listings for all ATS-detected H-1B employers.

Run from project root:
    python scrape_all.py                  # scrape companies not scraped in last 24h
    python scrape_all.py --limit 200      # cap at 200 companies
    python scrape_all.py --all            # re-scrape everything
    python scrape_all.py --workers 10     # parallelism (default 5)
"""

from __future__ import annotations
import os, sys, time, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from db import query_df, upsert_job_listings
from scraper import scrape_greenhouse, scrape_lever, scrape_ashby


def _extract_slug(platform: str, probe_url: str) -> str:
    """Extract the ATS board slug from the probe URL stored in company_ats."""
    # Greenhouse: https://api.greenhouse.io/v1/boards/{slug}/jobs
    # Lever:      https://api.lever.co/v0/postings/{slug}?limit=1
    # Ashby:      https://api.ashbyhq.com/posting-api/job-board/{slug}
    parts = urlparse(probe_url).path.strip("/").split("/")
    if platform in ("greenhouse", "lever", "ashby") and len(parts) >= 3:
        return parts[2]
    return ""


def _scrape_one(employer_name: str, platform: str, ats_url: str) -> tuple[str, list[dict], str]:
    slug = _extract_slug(platform, ats_url)
    if not slug:
        return employer_name, [], platform

    try:
        if platform == "greenhouse":
            jobs = scrape_greenhouse(slug)
        elif platform == "lever":
            jobs = scrape_lever(slug)
        elif platform == "ashby":
            jobs = scrape_ashby(slug)
        else:
            jobs = []
    except Exception:
        jobs = []

    return employer_name, jobs, platform


def main():
    parser = argparse.ArgumentParser(description="Batch scrape ATS job listings")
    parser.add_argument("--limit",   type=int, default=0,     help="Max companies to scrape (0 = all)")
    parser.add_argument("--workers", type=int, default=5,     help="Parallel scrape workers (default 5)")
    parser.add_argument("--all",     action="store_true",     help="Re-scrape even recently scraped companies")
    args = parser.parse_args()

    if args.all:
        sql = """
            SELECT employer_name, ats_platform, ats_url
            FROM company_ats
            WHERE ats_platform NOT IN ('unknown', 'workday')
            ORDER BY employer_name
        """
    else:
        sql = """
            SELECT a.employer_name, a.ats_platform, a.ats_url
            FROM company_ats a
            LEFT JOIN (
                SELECT employer_name, MAX(scraped_at) AS last_scraped
                FROM job_listings
                GROUP BY employer_name
            ) j ON a.employer_name = j.employer_name
            WHERE a.ats_platform NOT IN ('unknown', 'workday')
              AND (j.last_scraped IS NULL OR j.last_scraped < NOW() - INTERVAL '24 hours')
            ORDER BY a.employer_name
        """

    df = query_df(sql)
    if args.limit:
        df = df.head(args.limit)

    total = len(df)
    if total == 0:
        print("All companies scraped recently. Use --all to re-scrape.")
        return

    print(f"Scraping {total:,} companies  |  workers={args.workers}")
    print("─" * 60)

    scraped, jobs_found = 0, 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_scrape_one, row["employer_name"], row["ats_platform"], row["ats_url"]): row["employer_name"]
            for _, row in df.iterrows()
        }
        for i, future in enumerate(as_completed(futures), 1):
            employer, jobs, platform = future.result()
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
