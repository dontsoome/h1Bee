"""ATS job scraper — Greenhouse, Lever, Ashby with brute-force detection."""

from __future__ import annotations
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; H1BEE/1.0)"}
TIMEOUT = 6   # per individual HTTP request
PROBE_TIMEOUT = 4  # for ATS probe requests


# ── ATS URL detection ─────────────────────────────────────────────────────────

def detect_ats(url: str) -> tuple[str, str]:
    """
    Pattern-match a URL to an ATS.
    Returns (ats_name, slug) or ('unknown', '').
    """
    if not url:
        return "unknown", ""
    parsed = urlparse(url.strip())
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
        return "workday", url
    return "unknown", ""


# ── Slug generation ───────────────────────────────────────────────────────────

_LEGAL_SUFFIXES = re.compile(
    r'\b(inc|llc|corp|ltd|co|pllc|pc|lp|llp|group|holdings|'
    r'technologies|technology|solutions|services|systems|global|'
    r'international|enterprises|consulting|labs|lab)\b\.?',
    re.IGNORECASE,
)

def _slug_variants(company_name: str) -> list[str]:
    """
    Generate likely ATS slug candidates from a company name.
    e.g. 'ZOCDOC INC' -> ['zocdoc', 'zocdocinc']
         'LABELBOX INC' -> ['labelbox', 'labelboxinc']
    """
    name = company_name.lower()
    name = _LEGAL_SUFFIXES.sub("", name)
    name = re.sub(r"[^a-z0-9\s-]", "", name).strip()

    words = name.split()
    variants: list[str] = []

    if words:
        variants.append(words[0])                          # "zocdoc"
        if len(words) >= 2:
            variants.append(f"{words[0]}-{words[1]}")     # "zocdoc-inc"
            variants.append("".join(words[:2]))            # "zocdocinc"
        variants.append("".join(words))                    # all words joined

    # Deduplicate while preserving order
    seen: set[str] = set()
    return [v for v in variants if v and len(v) >= 2 and not (v in seen or seen.add(v))]  # type: ignore


# ── ATS probe helpers ─────────────────────────────────────────────────────────

def _probe_greenhouse(slug: str) -> bool:
    try:
        r = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            headers=HEADERS, timeout=PROBE_TIMEOUT,
        )
        return r.status_code == 200 and "jobs" in r.text
    except Exception:
        return False


def _probe_lever(slug: str) -> bool:
    try:
        r = requests.get(
            f"https://api.lever.co/v0/postings/{slug}?mode=json",
            headers=HEADERS, timeout=PROBE_TIMEOUT,
        )
        return r.status_code == 200
    except Exception:
        return False


def _probe_ashby(slug: str) -> bool:
    try:
        r = requests.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            headers=HEADERS, timeout=PROBE_TIMEOUT,
        )
        return r.status_code == 200
    except Exception:
        return False


_PROBES = [
    ("greenhouse", _probe_greenhouse),
    ("lever",      _probe_lever),
    ("ashby",      _probe_ashby),
]


# ── Full ATS detection ────────────────────────────────────────────────────────

def detect_ats_for_company(company_name: str, career_url: str = "") -> tuple[str, str]:
    """
    Best-effort ATS detection pipeline:
      1. Pattern-match the stored career URL
      2. Follow redirects on the career URL
      3. Parallel brute-force slug probes

    Returns (ats_name, slug_or_identifier).
    ats_name: 'greenhouse' | 'lever' | 'ashby' | 'workday' | 'unknown'
    """
    # Step 1 — direct URL pattern
    if career_url:
        ats, slug = detect_ats(career_url)
        if ats != "unknown":
            return ats, slug

        # Step 2 — follow redirects
        try:
            r = requests.get(career_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            ats, slug = detect_ats(r.url)
            if ats != "unknown":
                return ats, slug
        except Exception:
            pass

    # Step 3 — parallel brute-force
    slugs = _slug_variants(company_name)
    tasks = [(ats_name, slug, probe) for slug in slugs for ats_name, probe in _PROBES]

    with ThreadPoolExecutor(max_workers=min(12, len(tasks))) as pool:
        futures = {pool.submit(probe, slug): (ats_name, slug) for ats_name, slug, probe in tasks}
        for fut in as_completed(futures):
            try:
                if fut.result():
                    return futures[fut]
            except Exception:
                pass

    return "unknown", ""


# ── Scrapers ──────────────────────────────────────────────────────────────────

def scrape_greenhouse(slug: str) -> list[dict]:
    try:
        r = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [
            {
                "title": j.get("title", ""),
                "url": j.get("absolute_url", ""),
                "location": j.get("location", {}).get("name", ""),
                "department": ", ".join(d.get("name", "") for d in j.get("departments", [])),
            }
            for j in r.json().get("jobs", [])
        ]
    except Exception:
        return []


def scrape_lever(slug: str) -> list[dict]:
    try:
        r = requests.get(
            f"https://api.lever.co/v0/postings/{slug}?mode=json",
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [
            {
                "title": j.get("text", ""),
                "url": j.get("hostedUrl", ""),
                "location": j.get("categories", {}).get("location", ""),
                "department": j.get("categories", {}).get("department", ""),
            }
            for j in r.json()
        ]
    except Exception:
        return []


def scrape_ashby(slug: str) -> list[dict]:
    try:
        r = requests.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [
            {
                "title": j.get("title", ""),
                "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
                "location": j.get("locationName", ""),
                "department": j.get("departmentName", ""),
            }
            for j in r.json().get("jobPostings", [])
        ]
    except Exception:
        return []


# ── Main entry point ──────────────────────────────────────────────────────────

def scrape_jobs(career_url: str, company_name: str = "") -> tuple[list[dict], str]:
    """
    Detect ATS and scrape jobs. Returns (jobs, ats_platform).
    Each job: {title, url, location, department}
    """
    ats, identifier = detect_ats_for_company(company_name, career_url)

    if ats == "greenhouse":
        return scrape_greenhouse(identifier), "greenhouse"
    if ats == "lever":
        return scrape_lever(identifier), "lever"
    if ats == "ashby":
        return scrape_ashby(identifier), "ashby"
    return [], ats
