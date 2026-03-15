"""ATS job scraper — Greenhouse, Lever, Ashby with slug-index + brute-force detection."""

from __future__ import annotations
import re
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; H1BEE/1.0)"}
TIMEOUT = 6
PROBE_TIMEOUT = 4

_SLUG_INDEX_URLS = {
    "greenhouse": "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/greenhouse_companies.json",
    "lever":      "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/lever_companies.json",
    "ashby":      "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/ashby_companies.json",
    "workday":    "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/workday_companies.json",
}

# Module-level cache — loaded once per process
_slug_sets: dict[str, set[str]] = {}           # greenhouse/lever/ashby → set of slugs
_workday_map: dict[str, str] = {}              # company_slug → full workday URL
_index_loaded = False
_index_lock = threading.Lock()


def _load_slug_index():
    """Download ATS slug lists once and cache in memory."""
    global _slug_sets, _workday_map, _index_loaded
    with _index_lock:
        if _index_loaded:
            return
        for ats, url in _SLUG_INDEX_URLS.items():
            try:
                r = requests.get(url, headers=HEADERS, timeout=10)
                r.raise_for_status()
                data = r.json()
                if ats == "workday":
                    # Format: "company|wdN|site_slug"
                    for entry in data:
                        parts = str(entry).split("|")
                        if len(parts) == 3:
                            company_slug, instance, site = parts
                            _workday_map[company_slug] = (
                                f"https://{company_slug}.{instance}.myworkdayjobs.com/{site}"
                            )
                else:
                    _slug_sets[ats] = set(data)
            except Exception:
                _slug_sets.setdefault(ats, set())
        _index_loaded = True


def _index_lookup(slug: str) -> tuple[str, str] | None:
    """Check slug against loaded index. Returns (ats_name, slug) or None."""
    _load_slug_index()
    for ats in ("greenhouse", "lever", "ashby"):
        slugs = _slug_sets.get(ats, set())
        if slug in slugs:
            return ats, slug
        # Prefix fallback: "doordash" → "doordashusa", "stripe" → "stripe-inc", etc.
        if len(slug) >= 4:
            for s in sorted(slugs):  # sorted for determinism
                if s.startswith(slug):
                    return ats, s
    if slug in _workday_map:
        return "workday", _workday_map[slug]
    return None


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

def detect_ats_for_company(company_name: str, career_url: str = "") -> tuple[str, str, str]:
    """
    Best-effort ATS detection pipeline:
      1. Pattern-match the stored career URL
      2. Follow redirects on the career URL
      3. Parallel brute-force slug probes

    Returns (ats_name, slug, detected_ats_url).
    detected_ats_url is the canonical ATS URL found (empty string if same as input or not found).
    ats_name: 'greenhouse' | 'lever' | 'ashby' | 'workday' | 'unknown'
    """
    # Step 1 — direct URL pattern match
    if career_url:
        ats, slug = detect_ats(career_url)
        if ats != "unknown":
            return ats, slug, ""

        # Step 2 — follow redirects
        try:
            r = requests.get(career_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            ats, slug = detect_ats(r.url)
            if ats != "unknown":
                return ats, slug, r.url
        except Exception:
            pass

    # Step 3 — slug index lookup (fast, no HTTP probes needed)
    for variant in _slug_variants(company_name):
        result = _index_lookup(variant)
        if result:
            ats_name, identifier = result
            # identifier is either a slug (greenhouse/lever/ashby) or full URL (workday)
            ats_url = identifier if ats_name == "workday" else _ats_canonical_url(ats_name, identifier)
            return ats_name, identifier, ats_url

    # Step 4 — parallel HTTP probe fallback (for companies not in the index)
    slugs = _slug_variants(company_name)
    tasks = [(ats_name, slug, probe) for slug in slugs for ats_name, probe in _PROBES]

    with ThreadPoolExecutor(max_workers=min(12, len(tasks))) as pool:
        futures = {pool.submit(probe, slug): (ats_name, slug) for ats_name, slug, probe in tasks}
        for fut in as_completed(futures):
            try:
                if fut.result():
                    ats_name, slug = futures[fut]
                    ats_url = _ats_canonical_url(ats_name, slug)
                    return ats_name, slug, ats_url
            except Exception:
                pass

    return "unknown", "", ""


def _ats_canonical_url(ats_name: str, slug: str) -> str:
    if ats_name == "greenhouse":
        return f"https://job-boards.greenhouse.io/{slug}"
    if ats_name == "lever":
        return f"https://jobs.lever.co/{slug}"
    if ats_name == "ashby":
        return f"https://jobs.ashbyhq.com/{slug}"
    return ""


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
        data = r.json()
        # API returns "jobs" (newer) or "jobPostings" (older boards)
        job_list = data.get("jobs") or data.get("jobPostings") or []
        return [
            {
                "title": j.get("title", ""),
                "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
                "location": j.get("location", "") or j.get("locationName", ""),
                "department": j.get("department", "") or j.get("departmentName", ""),
            }
            for j in job_list
        ]
    except Exception:
        return []


# ── Main entry point ──────────────────────────────────────────────────────────

def scrape_jobs(career_url: str, company_name: str = "") -> tuple[list[dict], str, str]:
    """
    Detect ATS and scrape jobs.
    Returns (jobs, ats_platform, detected_ats_url).
    detected_ats_url is non-empty when a better URL was found via redirect/brute-force.
    Each job: {title, url, location, department}
    """
    ats, identifier, detected_url = detect_ats_for_company(company_name, career_url)

    if ats == "greenhouse":
        return scrape_greenhouse(identifier), "greenhouse", detected_url
    if ats == "lever":
        return scrape_lever(identifier), "lever", detected_url
    if ats == "ashby":
        return scrape_ashby(identifier), "ashby", detected_url
    if ats == "workday":
        # identifier is the full Workday URL — return it so UI can show a direct link
        return [], "workday", identifier or detected_url
    return [], "unknown", ""
