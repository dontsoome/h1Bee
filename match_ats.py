"""
Match ATS slugs from Common Crawl against H-1B employer names.

Three confidence tiers:
  HIGH   (F1 >= 0.90, employer has >=2 meaningful tokens) — accept directly
  MEDIUM (F1 0.60-0.90, OR single-token employer)         — verify via Claude or ATS API
  LOW    (F1 < 0.60)                                       — skip

Run from project root:
    python match_ats.py --dry-run --limit 300              # test on 300 employers, output CSV
    python match_ats.py --dry-run --limit 300 --claude-verify  # same + Claude verification
    python match_ats.py --skip-verify --limit 300 --dry-run    # fastest, no verification at all
    python match_ats.py                                    # full run, write to DB
    python match_ats.py --claude-verify                    # full run with Claude verification
"""

from __future__ import annotations
import os, sys, re, argparse, time
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pandas as pd
import requests
import psycopg2, psycopg2.extras
from db import query_df, _get_database_url

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR        = Path(__file__).parent / "data"
HEADERS         = {"User-Agent": "Mozilla/5.0 (compatible; H1BEE/1.0)"}
TIMEOUT         = 5
HIGH_THRESHOLD  = 0.90
MED_THRESHOLD   = 0.60
VERIFY_WORKERS  = 10
CLAUDE_BATCH    = 500   # pairs per Claude API call (~36k tokens, under 50k/min limit)
CLAUDE_WORKERS  = 1     # sequential — avoids rate limit (50k tokens/min)

ATS_CANONICAL = {
    "greenhouse":      "https://boards.greenhouse.io/{slug}",
    "lever":           "https://jobs.lever.co/{slug}",
    "ashby":           "https://jobs.ashbyhq.com/{slug}",
    "smartrecruiters": "https://jobs.smartrecruiters.com/{slug}",
    "jazzhr":          "https://{slug}.applytojob.com/apply",
}

NOISE_SLUGS = {
    "blog", "jobs", "careers", "about", "terms", "legal", "privacy",
    "login", "signup", "sign-in", "sign-up", "auth", "users", "demo",
    "pricing", "contact", "home", "index", "search", "api", "help",
    "support", "resources", "press", "news", "events", "solutions",
    "products", "services", "customers", "partners", "company",
    "history", "category", "author", "rss", "sitemap", "robots",
    "providers", "alternatives", "research", "docs", "documentation",
    "harvest", "e", "s", "r", "agreements", "incidents",
    "advanced-nurture", "terms-of-service", "provider-category",
    "ai-screening-companion", "recruiting-software-for-small-business",
    "recruiting-metrics-guide", "recruiting-resources", "wpa-stats-type",
    "history.rss", "media-and-press-inquiries",
    # Generic business words — no real company uses these as their primary ATS slug
    "service", "partner", "system", "consulting", "consult",
    "avenue", "center", "human", "healthcare",
    # Word fragments (truncations of common words — not real slugs)
    "compa", "inter", "proper", "digit",
}

# Only strip TRUE legal filing suffixes — words with zero identity information.
# We deliberately keep: group, technologies, solutions, global, international,
# partners, consulting, ventures, labs, systems, associates, etc.
# These are part of the company identity and help avoid false matches.
_LEGAL = re.compile(
    r"\b(llc|inc|corp|corporation|ltd|limited|lp|llp|na|pc|pllc|plc|"
    r"incorporated|the|and|of|for|in|at|by)\b\.?",
    re.IGNORECASE,
)


# ── Normalization ─────────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    s = name.lower()
    s = _LEGAL.sub(" ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def name_tokens(name: str) -> set[str]:
    """Meaningful tokens from employer name after stripping legal-only suffixes."""
    return {t for t in normalize(name).split() if len(t) >= 3}


def slug_tokens(slug: str) -> set[str]:
    """Tokens from an ATS slug (split on hyphens/underscores + camelCase)."""
    s = slug.lower().replace("-", " ").replace("_", " ")
    s = re.sub(r"([a-z])([0-9])", r"\1 \2", s)
    return {t for t in s.split() if len(t) >= 3}


def slug_concat(slug: str) -> str:
    return slug.lower().replace("-", "").replace("_", "")


# ── Scoring (bidirectional F1) ─────────────────────────────────────────────────

def score_match(slug: str, employer: str) -> float:
    """
    Return match confidence 0-1 using bidirectional F1 scoring.

    employer_coverage = how much of the employer name the slug explains
    slug_coverage     = how much of the slug the employer name explains
    score             = F1 harmonic mean of both

    This prevents a 1-token slug from scoring HIGH against a 3-token employer:
      "dust" vs "DUST GROUP TECHNOLOGIES" → employer_coverage=1/3=0.33 → F1~0.50
    """
    norm_name  = normalize(employer)
    norm_slug  = slug_concat(slug)
    name_plain = re.sub(r"\s+", "", norm_name)

    # Exact concat match: "stripe" == "stripe"
    if norm_slug == name_plain:
        return 1.0

    # Slug is the brand PREFIX of the name: "jpmorgan" starts "jpmorganchase"
    # Must use startswith (not `in`) to avoid "service" matching "enterpriseservices".
    # Also require slug covers >= 50% of the name so short generic words don't qualify.
    if len(norm_slug) >= 6 and name_plain.startswith(norm_slug):
        if len(norm_slug) / len(name_plain) >= 0.50:
            return 0.95

    # Name is fully contained in slug: "figma" in "figmainc"
    if len(name_plain) >= 6 and name_plain in norm_slug:
        return 0.92

    # Bidirectional F1 token overlap
    s_tok = slug_tokens(slug)
    n_tok = name_tokens(employer)
    if not s_tok or not n_tok:
        return 0.0

    overlap = s_tok & n_tok
    if not overlap:
        return 0.0

    employer_coverage = len(overlap) / len(n_tok)   # % of employer explained
    slug_coverage     = len(overlap) / len(s_tok)   # % of slug matched

    # F1 harmonic mean — both directions must be satisfied
    f1 = 2 * employer_coverage * slug_coverage / (employer_coverage + slug_coverage)

    # First-token boost: if the slug exactly equals the first meaningful word of the
    # employer name (>= 4 chars) and the slug itself is >= 5 chars, promote to MEDIUM
    # so Claude can verify. e.g. "amazon" vs "AMAZON WEB SERVICES INC" (F1=0.5 → 0.60).
    if f1 < MED_THRESHOLD and len(norm_slug) >= 5:
        norm_tokens = normalize(employer).split()
        first_long = next((t for t in norm_tokens if len(t) >= 4), None)
        if first_long and norm_slug == first_long:
            f1 = MED_THRESHOLD

    return round(f1, 3)


def is_ambiguous_employer(employer: str) -> bool:
    """
    Returns True if the employer name normalizes to a single meaningful token.
    Single-token matches are inherently ambiguous (e.g. 'dust', 'alpha', 'blue')
    and must always go through verification regardless of score.
    """
    return len(name_tokens(employer)) <= 1


def has_number_prefix(employer: str) -> bool:
    """Returns True if employer name starts with a digit (e.g. '17 STORY LLC')."""
    return bool(re.match(r'^\d', employer.strip()))


def slug_matches_number_prefix(employer: str, slug: str) -> bool:
    """
    If an employer starts with a number, the slug must also start with that number.
    This distinguishes:
      - '1047 GAMES INC' + '1047games'  → slug starts with '1047' → valid ✓
      - '17 STORY LLC'  + 'story'        → slug doesn't start with '17' → reject ✗
      - '1UPHEALTH INC' + '1uphealth'    → slug starts with '1' → valid ✓
      - '59 DONUT CORP' + 'donut'        → slug doesn't start with '59' → reject ✗
    """
    m = re.match(r'^(\d+)', employer.strip())
    if not m:
        return True  # no number prefix — no restriction
    leading_num = m.group(1)
    return slug_concat(slug).startswith(leading_num)


def _fetch_board_name(platform: str, slug: str) -> str:
    """
    Fetch the actual company name registered on the ATS board.
    Returns '' if unavailable or platform has no name endpoint (Lever, Workday, JazzHR, iCIMS).
    """
    try:
        if platform == "greenhouse":
            r = requests.get(
                f"https://api.greenhouse.io/v1/boards/{slug}",
                headers=HEADERS, timeout=TIMEOUT,
            )
            if r.status_code == 200:
                return r.json().get("name", "")
        elif platform == "ashby":
            r = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                headers=HEADERS, timeout=TIMEOUT,
            )
            if r.status_code == 200:
                return r.json().get("organization", {}).get("name", "")
        elif platform == "smartrecruiters":
            r = requests.get(
                f"https://api.smartrecruiters.com/v1/companies/{slug}",
                headers=HEADERS, timeout=TIMEOUT,
            )
            if r.status_code == 200:
                return r.json().get("name", "")
        # lever, workday, jazzhr, icims: no public name endpoint — return ''
    except Exception:
        pass
    return ""


def enrich_with_board_names(medium: list[dict], workers: int = 20) -> list[dict]:
    """
    Fetch the actual ATS board company name for Greenhouse and Ashby candidates.
    This is the key signal: Claude can then compare employer name vs board name directly.
    """
    print(f"  Fetching board names for {len(medium):,} candidates...")
    enriched = [dict(m) for m in medium]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _fetch_board_name,
                m["ats_platform"],
                m.get("url_slug", m["slug"]) if m["ats_platform"] == "icims" else m["slug"],
            ): i
            for i, m in enumerate(medium)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                enriched[idx]["board_name"] = fut.result()
            except Exception:
                enriched[idx]["board_name"] = ""

    fetched = sum(1 for m in enriched if m.get("board_name"))
    print(f"  Got board names for {fetched:,}/{len(medium):,}")
    return enriched


# ── Claude API Verification ────────────────────────────────────────────────────

def _claude_verify_batch(pairs: list[dict]) -> list[bool]:
    """
    Send a batch of candidates to Claude Haiku for YES/NO verification.
    Includes the actual ATS board company name (from API) when available,
    so Claude can compare employer vs board name directly rather than just slug.
    """
    import anthropic
    client = anthropic.Anthropic()

    lines = []
    for i, p in enumerate(pairs):
        board_name = p.get("board_name", "")
        if board_name:
            lines.append(
                f"{i+1}. H-1B Employer: {p['employer_name']} | "
                f"ATS Board Company: {board_name} | Platform: {p['ats_platform']}"
            )
        else:
            lines.append(
                f"{i+1}. H-1B Employer: {p['employer_name']} | "
                f"Slug: {p['slug']} | Platform: {p['ats_platform']} | (no board name available)"
            )

    prompt = f"""You are matching H-1B employer records (US Dept of Labor) to ATS job board companies.

For each entry, answer YES only if the H-1B employer and the ATS board company are the SAME legal entity.

Rules:
- When an "ATS Board Company" name is shown, compare it directly to the H-1B employer — they must refer to the same company
- Small businesses / LLCs / companies with number prefixes (like "17 Story LLC") are NOT the same as clean startup brands (like "Story")
- A dental practice named "Cottage Dental" is NOT the same as a tech company called "Cottage"
- Generic words (array, story, donut, cottage) as slugs almost never belong to multi-word companies with prefixes
- CORRECT: "STRIPE INC" matches board "Stripe", "GOLDMAN SACHS" matches board "Goldman Sachs"
- WRONG: "17 STORY LLC" matches board "Story" (completely different companies)
- WRONG: "32 COTTAGE DENTAL LLC" matches board "Cottage" (dental practice ≠ tech company)
- When in doubt, answer NO

{chr(10).join(lines)}

Reply with ONLY the number and YES/NO, one per line:
1. YES
2. NO
..."""

    for attempt in range(5):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=len(pairs) * 8,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text.strip()
            break
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < 4:
                wait = 65 * (attempt + 1)
                print(f"  Rate limited — waiting {wait}s before retry {attempt+2}/5...")
                time.sleep(wait)
            else:
                print(f"  Claude API error: {e}")
                return [False] * len(pairs)
    else:
        return [False] * len(pairs)

    results = [False] * len(pairs)
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"^(\d+)\.\s*(YES|NO)", line, re.IGNORECASE)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(pairs):
                results[idx] = m.group(2).upper() == "YES"
    return results


def verify_with_claude(
    medium: list[dict],
    batch_size: int = CLAUDE_BATCH,
    workers: int = CLAUDE_WORKERS,
) -> list[dict]:
    """
    Verify MEDIUM-tier candidates using Claude Haiku in parallel batches.
    Returns confirmed matches only.
    """
    print(f"\nVerifying {len(medium):,} medium-confidence candidates via Claude Haiku...")
    print(f"  Batch size: {batch_size} | Workers: {workers}")

    # Enrich with actual ATS board names (Greenhouse + Ashby only — Lever has no endpoint)
    medium = enrich_with_board_names(medium, workers=20)

    batches = [medium[i:i+batch_size] for i in range(0, len(medium), batch_size)]
    all_results: list[bool] = [False] * len(medium)

    start = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_range = {}
        offset = 0
        for batch in batches:
            future_to_range[pool.submit(_claude_verify_batch, batch)] = (offset, len(batch))
            offset += len(batch)

        for i, fut in enumerate(as_completed(future_to_range), 1):
            start_idx, length = future_to_range[fut]
            try:
                verdicts = fut.result()
                for j, v in enumerate(verdicts):
                    all_results[start_idx + j] = v
            except Exception as e:
                print(f"  Batch error: {e}")

            elapsed = time.time() - start
            processed = min((i * batch_size), len(medium))
            rate = processed / elapsed if elapsed > 0 else 0
            print(f"  Batch {i}/{len(batches)} done  ({processed:,}/{len(medium):,} pairs)  {rate:.0f}/s")

    # Collect confirmed, one per employer (prefer highest score)
    seen_employers: set[str] = set()
    confirmed = []
    for m, ok in sorted(
        zip(medium, all_results),
        key=lambda x: -x[0]["score"]
    ):
        if ok and m["employer_name"] not in seen_employers:
            seen_employers.add(m["employer_name"])
            confirmed.append({**m, "verified": True, "verify_method": "claude"})

    yes_count = sum(all_results)
    print(f"  Claude said YES: {yes_count:,}/{len(medium):,}")
    print(f"  Confirmed (deduped by employer): {len(confirmed):,}")
    return confirmed


# ── HTTP API Verification (fallback) ──────────────────────────────────────────

def _verify_greenhouse(slug: str, employer: str) -> bool:
    try:
        r = requests.get(
            f"https://api.greenhouse.io/v1/boards/{slug}",
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return False
        board_name = r.json().get("name", "")
        if not board_name:
            return False
        b_tok = name_tokens(board_name)
        e_tok = name_tokens(employer)
        if not b_tok or not e_tok:
            return False
        overlap = b_tok & e_tok
        return len(overlap) / min(len(b_tok), len(e_tok)) >= 0.4
    except Exception:
        return False


def _verify_lever(slug: str, employer: str) -> bool:
    try:
        r = requests.get(
            f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1",
            headers=HEADERS, timeout=TIMEOUT,
        )
        return r.status_code == 200
    except Exception:
        return False


def _verify_ashby(slug: str, employer: str) -> bool:
    try:
        r = requests.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return False
        org_name = r.json().get("organization", {}).get("name", "")
        if not org_name:
            return r.status_code == 200
        b_tok = name_tokens(org_name)
        e_tok = name_tokens(employer)
        if not b_tok or not e_tok:
            return False
        overlap = b_tok & e_tok
        return len(overlap) / min(len(b_tok), len(e_tok)) >= 0.4
    except Exception:
        return False


_VERIFIERS = {
    "greenhouse": _verify_greenhouse,
    "lever":      _verify_lever,
    "ashby":      _verify_ashby,
}


def verify_medium_http(medium: list[dict], workers: int = VERIFY_WORKERS) -> list[dict]:
    """Verify MEDIUM candidates via ATS HTTP APIs (fallback if no Claude key)."""
    print(f"\nVerifying {len(medium):,} candidates via ATS APIs...")
    confirmed = []
    seen_employers: set[str] = set()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_VERIFIERS.get(m["ats_platform"], lambda s, e: False),
                        m["slug"], m["employer_name"]): m
            for m in medium
        }
        for i, fut in enumerate(as_completed(futures), 1):
            m = futures[fut]
            try:
                ok = fut.result()
            except Exception:
                ok = False
            if ok and m["employer_name"] not in seen_employers:
                seen_employers.add(m["employer_name"])
                confirmed.append({**m, "verified": True, "verify_method": "http"})
            if i % 500 == 0:
                print(f"  {i:,}/{len(medium):,} done, {len(confirmed):,} confirmed")

    print(f"  Confirmed: {len(confirmed):,}")
    return confirmed


# ── Data loading ──────────────────────────────────────────────────────────────

_ICIMS_PREFIX = re.compile(r"^(careers?|jobs?|recruiting|talent|hr)-", re.IGNORECASE)


def load_slugs() -> pd.DataFrame:
    dfs = []
    for f in DATA_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(f)
            if "slug" in df.columns and "ats" in df.columns:
                cols = ["slug", "ats"]
                if "board" in df.columns:
                    cols.append("board")
                dfs.append(df[cols].dropna(subset=["slug", "ats"]))
        except Exception as e:
            print(f"  Warning: could not read {f.name}: {e}")

    combined = pd.concat(dfs, ignore_index=True)
    if "board" not in combined.columns:
        combined["board"] = ""
    else:
        combined["board"] = combined["board"].fillna("")

    combined = combined.drop_duplicates(subset=["slug", "ats"])
    combined = combined[~combined["slug"].str.lower().isin(NOISE_SLUGS)]
    combined = combined[combined["slug"].str.len() >= 3]
    combined = combined[~combined["slug"].str.match(r"^\d+$")]
    combined = combined[~combined["slug"].str.match(r"^[a-z]$")]

    # For iCIMS: preserve original slug in url_slug, strip prefix from slug for matching
    combined["url_slug"] = combined["slug"]
    icims_mask = combined["ats"] == "icims"
    combined.loc[icims_mask, "slug"] = (
        combined.loc[icims_mask, "slug"].apply(lambda s: _ICIMS_PREFIX.sub("", s))
    )

    print(f"Loaded {len(combined):,} slugs")
    for ats in ["greenhouse", "lever", "ashby", "workday", "smartrecruiters", "jazzhr", "icims"]:
        print(f"  {ats}: {len(combined[combined['ats']==ats]):,}")
    return combined


def load_employers(limit: int = 0) -> list[str]:
    df = query_df("SELECT DISTINCT employer_name FROM lca_records ORDER BY employer_name")
    employers = df["employer_name"].tolist()
    if limit:
        employers = employers[:limit]
    print(f"\nLoaded {len(employers):,} H-1B employers")
    return employers


# ── Matching ──────────────────────────────────────────────────────────────────

def build_slug_index(slugs_df: pd.DataFrame) -> dict[str, list[tuple[str, str, str, str]]]:
    index: dict[str, list[tuple[str, str, str, str]]] = {}
    for _, row in slugs_df.iterrows():
        slug     = str(row["slug"]).lower()
        ats      = str(row["ats"])
        board    = str(row.get("board", ""))
        url_slug = str(row.get("url_slug", slug))
        key      = slug_concat(slug)[:4]
        index.setdefault(key, []).append((slug, ats, board, url_slug))
    return index


def find_candidates(employer: str, index: dict) -> list[tuple[str, str, float, str, str]]:
    norm   = normalize(employer)
    plain  = re.sub(r"\s+", "", norm)
    tokens = name_tokens(employer)

    keys = {t[:4] for t in tokens if len(t) >= 4}
    keys.add(plain[:4])

    seen: set[tuple[str, str]] = set()
    candidates = []

    for key in keys:
        for slug, ats, board, url_slug in index.get(key, []):
            if (slug, ats) in seen:
                continue
            seen.add((slug, ats))
            s = score_match(slug, employer)
            if s >= MED_THRESHOLD:
                candidates.append((slug, ats, s, board, url_slug))

    return sorted(candidates, key=lambda x: -x[2])


def match_all(slugs_df: pd.DataFrame, employers: list[str]) -> tuple[list[dict], list[dict]]:
    """
    Returns (high_confidence, needs_verification).

    HIGH requires BOTH:
      - score >= HIGH_THRESHOLD
      - employer has >= 2 meaningful tokens (single-token names are ambiguous)

    MEDIUM: everything else that passes MED_THRESHOLD, including high-scoring
    single-token employers that need verification to confirm.
    """
    index = build_slug_index(slugs_df)
    high, medium = [], []

    print(f"\nMatching {len(employers):,} employers...")
    for employer in employers:
        candidates = find_candidates(employer, index)
        if not candidates:
            continue

        best_slug, best_ats, best_score, best_board, best_url_slug = candidates[0]
        ambiguous = is_ambiguous_employer(employer)

        # Pre-filter: if employer starts with a number, every candidate slug must
        # also start with that number — otherwise it's a different company.
        # "1047 GAMES INC" + "1047games" → slug starts with "1047" → OK
        # "17 STORY LLC"   + "story"     → slug doesn't start with "17" → skip
        # "59 DONUT CORP"  + "donut"     → slug doesn't start with "59" → skip
        num_prefix = has_number_prefix(employer)
        if num_prefix:
            candidates = [
                (slug, ats, score, board, url_slug)
                for slug, ats, score, board, url_slug in candidates
                if slug_matches_number_prefix(employer, slug)
            ]
            if not candidates:
                continue
            best_slug, best_ats, best_score, best_board, best_url_slug = candidates[0]

        if best_score >= HIGH_THRESHOLD and not ambiguous:
            high.append({
                "employer_name": employer,
                "ats_platform":  best_ats,
                "slug":          best_slug,
                "score":         best_score,
                "tier":          "HIGH",
                "verified":      True,
                "verify_method": "heuristic",
                "board":         best_board,
                "url_slug":      best_url_slug,
            })
        else:
            # Include top 3 candidates for MEDIUM verification
            if ambiguous:
                reason = "single_token"
            elif num_prefix:
                reason = "number_prefix"
            else:
                reason = "score"
            for slug, ats, score, board, url_slug in candidates[:3]:
                medium.append({
                    "employer_name": employer,
                    "ats_platform":  ats,
                    "slug":          slug,
                    "score":         score,
                    "tier":          "MEDIUM",
                    "verified":      False,
                    "verify_method": None,
                    "medium_reason": reason,
                    "board":         board,
                    "url_slug":      url_slug,
                })

    print(f"  High confidence (direct accept): {len(high):,}")
    print(f"  Medium confidence (needs verify): {len(medium):,} pairs")
    single_tok = sum(1 for m in medium if m.get("medium_reason") == "single_token")
    print(f"    Of which single-token ambiguous: {single_tok:,}")
    return high, medium


# ── Output ────────────────────────────────────────────────────────────────────

def _make_ats_url(platform: str, slug: str, board: str, url_slug: str) -> str:
    """Construct the canonical ATS board URL for a given platform."""
    if platform == "greenhouse":
        return f"https://boards.greenhouse.io/{slug}"
    if platform == "lever":
        return f"https://jobs.lever.co/{slug}"
    if platform == "ashby":
        return f"https://jobs.ashbyhq.com/{slug}"
    if platform == "workday":
        if board:
            return f"https://{slug}.wd1.myworkdayjobs.com/en-US/{board}"
        return f"https://{slug}.wd1.myworkdayjobs.com"
    if platform == "smartrecruiters":
        return f"https://jobs.smartrecruiters.com/{slug}"
    if platform == "jazzhr":
        return f"https://{slug}.applytojob.com/apply"
    if platform == "icims":
        return f"https://{url_slug}.icims.com/jobs/search"
    return ""


def build_results(high: list[dict], verified_medium: list[dict]) -> list[dict]:
    all_matches = high + verified_medium
    seen: set[str] = set()
    final = []
    for m in sorted(all_matches, key=lambda x: -x["score"]):
        if m["employer_name"] not in seen:
            seen.add(m["employer_name"])
            m["ats_url"] = _make_ats_url(
                m["ats_platform"],
                m["slug"],
                m.get("board", ""),
                m.get("url_slug", m["slug"]),
            )
            final.append(m)
    return final


def write_to_db(results: list[dict]):
    now = datetime.now(timezone.utc)
    rows = [
        (r["employer_name"], r["ats_platform"], r["ats_url"], True, now)
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
        rows, page_size=500,
    )
    pg.commit()
    pg.close()
    print(f"Wrote {len(results):,} matches to company_ats")


def write_unmatched_to_db(all_employers: list[str], matched_employers: set[str]):
    """
    Write all unmatched H-1B employers to company_ats with ats_platform='unknown'.
    These companies may have their own career pages and can be manually enriched
    via the career_urls table, or targeted by custom scrapers in the future.

    Uses DO NOTHING on conflict so existing confirmed matches are never overwritten.
    """
    unmatched = [e for e in all_employers if e not in matched_employers]
    if not unmatched:
        return
    now = datetime.now(timezone.utc)
    rows = [(e, "unknown", "", True, now) for e in unmatched]
    pg = psycopg2.connect(_get_database_url())
    cur = pg.cursor()
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO company_ats (employer_name, ats_platform, ats_url, auto_detected, probed_at)
           VALUES %s
           ON CONFLICT (employer_name) DO NOTHING""",
        rows, page_size=500,
    )
    pg.commit()
    pg.close()
    print(f"Wrote {len(unmatched):,} unmatched employers to company_ats (platform=unknown)")


def print_summary(results: list[dict], show: int = 40):
    from collections import Counter
    print("\n" + "=" * 100)
    print(f"TOTAL MATCHED: {len(results):,}")
    counts = Counter(r["ats_platform"] for r in results)
    for ats, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {ats:<15} {n:,}")

    tiers = Counter(r["tier"] for r in results)
    print(f"\nBy tier:")
    for tier, n in sorted(tiers.items()):
        print(f"  {tier:<10} {n:,}")

    methods = Counter(r.get("verify_method") or "none" for r in results)
    print(f"\nBy verify method:")
    for method, n in sorted(methods.items()):
        print(f"  {method:<15} {n:,}")

    print(f"\nSample matches (top {show} by score):")
    print(f"{'Employer':<45} {'ATS':<12} {'Slug':<25} {'Score':<7} {'Tier':<8} {'Method'}")
    print("-" * 110)
    for r in sorted(results, key=lambda x: -x["score"])[:show]:
        print(
            f"{r['employer_name']:<45} {r['ats_platform']:<12} {r['slug']:<25} "
            f"{r['score']:<7.2f} {r['tier']:<8} {r.get('verify_method','?')}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Match Common Crawl ATS slugs to H-1B employers")
    parser.add_argument("--dry-run",      action="store_true", help="Output CSV only, no DB writes")
    parser.add_argument("--limit",        type=int, default=0, help="Process only first N employers")
    parser.add_argument("--workers",      type=int, default=VERIFY_WORKERS, help="HTTP verify workers")
    parser.add_argument("--claude-verify",action="store_true", help="Use Claude Haiku for MEDIUM verification")
    parser.add_argument("--claude-batch", type=int, default=CLAUDE_BATCH, help="Pairs per Claude API call")
    parser.add_argument("--skip-verify",  action="store_true", help="Skip all verification (fastest, least accurate)")
    args = parser.parse_args()

    start = time.time()

    slugs_df  = load_slugs()
    employers = load_employers(limit=args.limit)
    high, medium = match_all(slugs_df, employers)

    if args.skip_verify:
        # Accept medium unverified — useful to see raw candidate quality
        seen: set[str] = set()
        medium_deduped = []
        for m in sorted(medium, key=lambda x: -x["score"]):
            if m["employer_name"] not in seen:
                seen.add(m["employer_name"])
                medium_deduped.append(m)
        results = build_results(high, medium_deduped)

    elif args.claude_verify:
        verified = verify_with_claude(medium, batch_size=args.claude_batch, workers=CLAUDE_WORKERS)
        results  = build_results(high, verified)

    else:
        # Default: HTTP API verification
        verified = verify_medium_http(medium, workers=args.workers)
        results  = build_results(high, verified)

    print_summary(results)

    matched_employers = {r["employer_name"] for r in results}

    if args.dry_run:
        out = Path(__file__).parent / "match_results.csv"
        pd.DataFrame(results).to_csv(out, index=False)

        # Also export unmatched so you can inspect them
        unmatched = [e for e in employers if e not in matched_employers]
        out_unmatched = Path(__file__).parent / "unmatched_employers.csv"
        pd.DataFrame({"employer_name": unmatched}).to_csv(out_unmatched, index=False)

        print(f"\nDry run — matched saved to {out}")
        print(f"           unmatched saved to {out_unmatched}  ({len(unmatched):,} companies)")
        print("Review both CSVs, then run without --dry-run to write to DB.")
    else:
        write_to_db(results)
        write_unmatched_to_db(employers, matched_employers)

    print(f"\nDone in {time.time()-start:.1f}s")


if __name__ == "__main__":
    main()
