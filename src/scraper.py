"""ATS job scraper — Greenhouse, Lever, Ashby (JSON APIs, no browser needed)."""

from __future__ import annotations
import re
import requests
from urllib.parse import urlparse

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; H1BEE/1.0)"}
TIMEOUT = 10


def detect_ats(career_url: str) -> tuple[str, str]:
    """
    Returns (ats_name, slug).
    ats_name: 'greenhouse' | 'lever' | 'ashby' | 'workday' | 'unknown'
    slug: company identifier used in API calls
    """
    if not career_url:
        return "unknown", ""
    parsed = urlparse(career_url.strip())
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    slug = path.split("/")[0] if path else ""

    if "greenhouse.io" in host:
        return "greenhouse", slug
    if "lever.co" in host:
        return "lever", slug
    if "ashbyhq.com" in host:
        return "ashby", slug
    if "myworkdayjobs.com" in host:
        return "workday", career_url
    return "unknown", ""


def scrape_greenhouse(slug: str) -> list[dict]:
    """Fetch jobs from Greenhouse public JSON API."""
    try:
        r = requests.get(
            f"https://boards.greenhouse.io/embed/job_board/jobs?for={slug}",
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        jobs = []
        for j in r.json().get("jobs", []):
            jobs.append({
                "title": j.get("title", ""),
                "url": j.get("absolute_url", ""),
                "location": j.get("location", {}).get("name", ""),
                "department": ", ".join(d.get("name", "") for d in j.get("departments", [])),
            })
        return jobs
    except Exception:
        return []


def scrape_lever(slug: str) -> list[dict]:
    """Fetch jobs from Lever public JSON API."""
    try:
        r = requests.get(
            f"https://api.lever.co/v0/postings/{slug}?mode=json",
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        jobs = []
        for j in r.json():
            cats = j.get("categories", {})
            jobs.append({
                "title": j.get("text", ""),
                "url": j.get("hostedUrl", ""),
                "location": cats.get("location", ""),
                "department": cats.get("department", ""),
            })
        return jobs
    except Exception:
        return []


def scrape_ashby(slug: str) -> list[dict]:
    """Fetch jobs from Ashby public JSON API."""
    try:
        r = requests.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        jobs = []
        for j in r.json().get("jobPostings", []):
            jobs.append({
                "title": j.get("title", ""),
                "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
                "location": j.get("locationName", ""),
                "department": j.get("departmentName", ""),
            })
        return jobs
    except Exception:
        return []


def scrape_jobs(career_url: str) -> tuple[list[dict], str]:
    """
    Main entry point. Returns (jobs, ats_platform).
    Each job dict: {title, url, location, department}
    Returns ([], 'workday') or ([], 'unknown') for unsupported platforms.
    """
    ats, slug = detect_ats(career_url)
    if ats == "greenhouse":
        return scrape_greenhouse(slug), "greenhouse"
    if ats == "lever":
        return scrape_lever(slug), "lever"
    if ats == "ashby":
        return scrape_ashby(slug), "ashby"
    return [], ats
