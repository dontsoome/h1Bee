"""Job listings routes with LCA enrichment JOIN."""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Query
from db import query_df, query_one
import re as _re

router = APIRouter()

US_STATE_CODES = {
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN',
    'IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV',
    'NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN',
    'TX','UT','VT','VA','WA','WV','WI','WY','DC'
}

STATE_NAME_MAP = {
    'ALABAMA':'AL','ALASKA':'AK','ARIZONA':'AZ','ARKANSAS':'AR',
    'CALIFORNIA':'CA','LOS ANGELES':'CA','SAN FRANCISCO':'CA','SAN JOSE':'CA',
    'COLORADO':'CO','DENVER':'CO','CONNECTICUT':'CT','DELAWARE':'DE',
    'FLORIDA':'FL','MIAMI':'FL','ORLANDO':'FL','TAMPA':'FL','JACKSONVILLE':'FL',
    'GEORGIA':'GA','ATLANTA':'GA','HAWAII':'HI','IDAHO':'ID','BOISE':'ID',
    'ILLINOIS':'IL','CHICAGO':'IL','INDIANA':'IN','INDIANAPOLIS':'IN',
    'IOWA':'IA','KANSAS':'KS','KENTUCKY':'KY','LOUISVILLE':'KY',
    'LOUISIANA':'LA','NEW ORLEANS':'LA','MAINE':'ME','MARYLAND':'MD',
    'BALTIMORE':'MD','MASSACHUSETTS':'MA','BOSTON':'MA','CAMBRIDGE':'MA',
    'MICHIGAN':'MI','DETROIT':'MI','ANN ARBOR':'MI','MINNESOTA':'MN',
    'MINNEAPOLIS':'MN','MISSISSIPPI':'MS','MISSOURI':'MO','ST LOUIS':'MO',
    'KANSAS CITY':'MO','MONTANA':'MT','NEBRASKA':'NE','OMAHA':'NE',
    'NEVADA':'NV','LAS VEGAS':'NV','RENO':'NV','NEW HAMPSHIRE':'NH',
    'NEW JERSEY':'NJ','NEWARK':'NJ','JERSEY CITY':'NJ','NEW MEXICO':'NM',
    'ALBUQUERQUE':'NM','NEW YORK':'NY','NEW YORK CITY':'NY','NYC':'NY',
    'BROOKLYN':'NY','MANHATTAN':'NY','QUEENS':'NY','BUFFALO':'NY',
    'NORTH CAROLINA':'NC','CHARLOTTE':'NC','RALEIGH':'NC','DURHAM':'NC',
    'NORTH DAKOTA':'ND','OHIO':'OH','COLUMBUS':'OH','CLEVELAND':'OH',
    'CINCINNATI':'OH','OKLAHOMA':'OK','OKLAHOMA CITY':'OK','TULSA':'OK',
    'OREGON':'OR','PORTLAND':'OR','PENNSYLVANIA':'PA','PHILADELPHIA':'PA',
    'PITTSBURGH':'PA','RHODE ISLAND':'RI','PROVIDENCE':'RI',
    'SOUTH CAROLINA':'SC','CHARLESTON':'SC','SOUTH DAKOTA':'SD',
    'TENNESSEE':'TN','NASHVILLE':'TN','MEMPHIS':'TN','TEXAS':'TX',
    'HOUSTON':'TX','DALLAS':'TX','AUSTIN':'TX','SAN ANTONIO':'TX',
    'FORT WORTH':'TX','UTAH':'UT','SALT LAKE CITY':'UT','VERMONT':'VT',
    'VIRGINIA':'VA','RICHMOND':'VA','NORFOLK':'VA','ARLINGTON':'VA',
    'WASHINGTON':'WA','SEATTLE':'WA','SPOKANE':'WA',
    'WASHINGTON DC':'DC','WASHINGTON D.C.':'DC','D.C.':'DC','DC':'DC',
    'DISTRICT OF COLUMBIA':'DC','WEST VIRGINIA':'WV','CHARLESTON':'WV',
    'WISCONSIN':'WI','MILWAUKEE':'WI','MADISON':'WI','WYOMING':'WY',
    'REMOTE': None,  # explicitly not a US state location
}


def normalize_to_state_code(value: str) -> str | None:
    if not value:
        return None
    v = value.strip().upper()
    # Already a valid 2-letter code
    if v in US_STATE_CODES:
        return v
    # Try extracting trailing 2-letter state code: "San Francisco, CA" or "New York, NY 10001"
    m = _re.search(r'\b([A-Z]{2})\b\s*\d*\s*$', v)
    if m and m.group(1) in US_STATE_CODES:
        return m.group(1)
    # Full name / city name lookup
    clean = _re.sub(r'[^A-Z\s]', '', v).strip()
    if clean in STATE_NAME_MAP:
        return STATE_NAME_MAP[clean]
    # Partial match on state name
    for key, code in STATE_NAME_MAP.items():
        if key in clean:
            return code
    return None


def _split_csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@router.get("/api/jobs")
def get_jobs(
    search: Optional[str] = None,
    states: Optional[str] = None,       # comma-separated state abbrevs e.g. "CA,NY"
    city: Optional[str] = None,
    ats_platform: Optional[str] = None,  # comma-separated
    min_wage: Optional[float] = None,
    max_wage: Optional[float] = None,
    wage_level: Optional[str] = None,    # comma-separated e.g. "I,II"
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Return paginated job_listings with LCA enrichment via JOIN."""
    jl_clauses: list[str] = []
    params: list = []

    # Full-text search across job_title and employer_name
    if search:
        jl_clauses.append("(jl.job_title ILIKE %s OR jl.employer_name ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]

    # State filter — normalize to state codes and match ", CA" pattern
    state_list = _split_csv(states)
    if state_list:
        # Normalize each to a state code
        normalized = [normalize_to_state_code(s) or s for s in state_list]
        or_parts = " OR ".join(["jl.location ILIKE %s" for _ in normalized])
        jl_clauses.append(f"({or_parts})")
        params += [f"%, {code}%" for code in normalized]
    elif not city:
        # Default: only US jobs — filter to locations with a recognizable US state pattern
        jl_clauses.append(
            "(jl.location ~ ', [A-Z]{2}( |$|[0-9])' OR jl.location ILIKE '%%remote%%' OR jl.location ILIKE '%%united states%%')"
        )

    # City filter
    if city:
        jl_clauses.append("jl.location ILIKE %s")
        params.append(f"%{city}%")

    # ATS platform filter
    platforms = _split_csv(ats_platform)
    if platforms:
        placeholders = ",".join(["%s"] * len(platforms))
        jl_clauses.append(f"jl.ats_platform IN ({placeholders})")
        params += platforms

    where = ("WHERE " + " AND ".join(jl_clauses)) if jl_clauses else ""
    offset = (page - 1) * limit

    # Salary filters — applied as WHERE on the materialized view columns
    wage_levels = _split_csv(wage_level)
    if min_wage is not None:
        jl_clauses.append("les.avg_wage_from >= %s")
        params.append(min_wage)
    if max_wage is not None:
        jl_clauses.append("les.avg_wage_to <= %s")
        params.append(max_wage)
    if wage_levels:
        placeholders = ",".join(["%s"] * len(wage_levels))
        jl_clauses.append(f"les.top_wage_level IN ({placeholders})")
        params += wage_levels

    # Rebuild where after adding salary clauses
    where = ("WHERE " + " AND ".join(jl_clauses)) if jl_clauses else ""
    having = ""  # no longer needed

    # Count query
    count_sql = f"""
        SELECT COUNT(*) AS total_count
        FROM job_listings jl
        LEFT JOIN lca_employer_stats les ON LOWER(jl.employer_name) = les.employer_key
        {where}
    """
    count_row = query_one(count_sql, tuple(params))
    total_count = count_row["total_count"] if count_row else 0

    # Main query — join against pre-aggregated materialized view (fast)
    data_sql = f"""
        SELECT
            jl.id,
            jl.employer_name,
            jl.job_title,
            jl.job_url,
            jl.department,
            jl.location,
            jl.ats_platform,
            jl.scraped_at::text,
            COALESCE(les.lca_count, 0)    AS lca_count,
            les.avg_wage_from             AS avg_wage_from,
            les.avg_wage_to               AS avg_wage_to,
            les.top_wage_level            AS top_wage_level
        FROM job_listings jl
        LEFT JOIN lca_employer_stats les
            ON LOWER(jl.employer_name) = les.employer_key
        {where}
        {having}
        ORDER BY jl.scraped_at DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    data_params = tuple(params) + (limit, offset)
    rows = query_df(data_sql, data_params)

    for row in rows:
        if row.get("id") is not None:
            row["id"] = int(row["id"])
        if row.get("lca_count") is not None:
            row["lca_count"] = int(row["lca_count"])
        for key in ("avg_wage_from", "avg_wage_to"):
            if row.get(key) is not None:
                row[key] = float(row[key])

    return {
        "data": rows,
        "total_count": int(total_count),
        "page": page,
        "limit": limit,
        "total_pages": max(1, -(-int(total_count) // limit)),
    }


@router.get("/api/debug/state-samples")
def debug_state_samples():
    rows = query_df("""
        SELECT location, COUNT(*) as cnt
        FROM job_listings
        GROUP BY location
        ORDER BY cnt DESC
        LIMIT 100
    """, ())
    return {"samples": rows}
