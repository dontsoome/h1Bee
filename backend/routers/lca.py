"""LCA and filter option routes."""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Query
from db import query_df, query_one

router = APIRouter()


def _split_csv(value: Optional[str]) -> list[str]:
    """Split a comma-separated query param into a list, stripping whitespace."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


_COMPANIES_SORT_COLS = {"lca_count", "avg_wage_from", "avg_wage_to", "employer_name"}

@router.get("/api/lca/companies")
def get_companies(
    employer_name: Optional[str] = None,
    min_wage: Optional[float] = None,
    max_wage: Optional[float] = None,
    min_lcas: Optional[int] = None,
    max_lcas: Optional[int] = None,
    order_by: str = Query(default="lca_count"),
    order_dir: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
):
    """
    Return aggregated company stats from lca_employer_stats materialized view.
    Fast pre-computed aggregation — no live grouping on lca_records.
    """
    clauses: list[str] = []
    params: list = []

    if employer_name:
        clauses.append("employer_key ILIKE %s")
        params.append(f"%{employer_name}%")
    if min_wage is not None:
        clauses.append("avg_wage_from >= %s")
        params.append(min_wage)
    if max_wage is not None:
        clauses.append("avg_wage_to <= %s")
        params.append(max_wage)
    if min_lcas is not None:
        clauses.append("lca_count >= %s")
        params.append(min_lcas)
    if max_lcas is not None:
        clauses.append("lca_count <= %s")
        params.append(max_lcas)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * limit

    # Validate sort params to prevent SQL injection
    sort_col = order_by if order_by in _COMPANIES_SORT_COLS else "lca_count"
    sort_dir = "ASC" if order_dir.lower() == "asc" else "DESC"

    count_sql = f"SELECT COUNT(*) AS total_count FROM lca_employer_stats {where}"
    count_row = query_one(count_sql, tuple(params))
    total_count = count_row["total_count"] if count_row else 0

    data_sql = f"""
        SELECT
            employer_key AS employer_name,
            lca_count    AS total_lcas,
            avg_wage_from,
            avg_wage_to,
            top_wage_level
        FROM lca_employer_stats
        {where}
        ORDER BY {sort_col} {sort_dir} NULLS LAST
        LIMIT %s OFFSET %s
    """
    rows = query_df(data_sql, tuple(params) + (limit, offset))

    for row in rows:
        for key in ("avg_wage_from", "avg_wage_to"):
            if row.get(key) is not None:
                row[key] = float(row[key])
        if row.get("total_lcas") is not None:
            row["total_lcas"] = int(row["total_lcas"])

    return {
        "data": rows,
        "total_count": int(total_count),
        "page": page,
        "limit": limit,
        "total_pages": max(1, -(-int(total_count) // limit)),
    }


@router.get("/api/lca/records")
def get_lca_records(
    employer_name: Optional[str] = None,
    job_title: Optional[str] = None,
    search: Optional[str] = None,
    worksite_state: Optional[str] = None,
    wage_level: Optional[str] = None,
    min_wage: Optional[float] = None,
    max_wage: Optional[float] = None,
    fiscal_year: Optional[str] = None,
    case_status: Optional[str] = None,
    visa_class: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Return paginated lca_records rows with optional filters."""
    clauses: list[str] = []
    params: list = []

    if search:
        clauses.append("(job_title ILIKE %s OR employer_name ILIKE %s)")
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    if employer_name:
        clauses.append("employer_name ILIKE %s")
        params.append(f"%{employer_name}%")

    if job_title:
        clauses.append("job_title ILIKE %s")
        params.append(f"%{job_title}%")

    if worksite_state:
        clauses.append("worksite_state = %s")
        params.append(worksite_state)

    wage_levels = _split_csv(wage_level)
    if wage_levels:
        placeholders = ",".join(["%s"] * len(wage_levels))
        clauses.append(f"pw_wage_level IN ({placeholders})")
        params.extend(wage_levels)

    if min_wage is not None:
        clauses.append("annual_wage_from >= %s")
        params.append(min_wage)

    if max_wage is not None:
        clauses.append("annual_wage_to <= %s")
        params.append(max_wage)

    years = _split_csv(fiscal_year)
    if years:
        try:
            year_ints = [int(y) for y in years]
            placeholders = ",".join(["%s"] * len(year_ints))
            clauses.append(f"fiscal_year IN ({placeholders})")
            params.extend(year_ints)
        except ValueError:
            pass

    statuses = _split_csv(case_status)
    if statuses:
        placeholders = ",".join(["%s"] * len(statuses))
        clauses.append(f"case_status IN ({placeholders})")
        params.extend(statuses)

    visa_classes = _split_csv(visa_class)
    if visa_classes:
        placeholders = ",".join(["%s"] * len(visa_classes))
        clauses.append(f"visa_class IN ({placeholders})")
        params.extend(visa_classes)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * limit

    count_sql = f"SELECT COUNT(*) AS total_count FROM lca_records {where}"
    count_row = query_one(count_sql, tuple(params))
    total_count = count_row["total_count"] if count_row else 0

    data_sql = f"""
        SELECT
            employer_name, job_title, visa_class, case_status,
            worksite_city, worksite_state, employer_state,
            wage_from, wage_to, annual_wage_from, annual_wage_to,
            wage_unit, pw_wage_level, fiscal_year,
            soc_title, naics_code, full_time_position,
            begin_date, end_date, total_worker_positions
        FROM lca_records
        {where}
        ORDER BY annual_wage_from DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    data_params = tuple(params) + (limit, offset)
    rows = query_df(data_sql, data_params)

    # Normalize numeric types for JSON
    for row in rows:
        for key in ("wage_from", "wage_to", "annual_wage_from", "annual_wage_to"):
            if row.get(key) is not None:
                row[key] = float(row[key])
        for key in ("total_worker_positions", "fiscal_year"):
            if row.get(key) is not None:
                row[key] = int(row[key])

    return {
        "data": rows,
        "total_count": int(total_count),
        "page": page,
        "limit": limit,
        "total_pages": max(1, -(-int(total_count) // limit)),
    }


@router.get("/api/filters/options")
def get_filter_options():
    """Return distinct filter values for all relevant columns."""

    worksite_states = query_df(
        "SELECT DISTINCT worksite_state FROM lca_records WHERE worksite_state IS NOT NULL ORDER BY worksite_state"
    )
    pw_wage_levels = query_df(
        "SELECT DISTINCT pw_wage_level FROM lca_records WHERE pw_wage_level IS NOT NULL ORDER BY pw_wage_level"
    )
    visa_classes = query_df(
        "SELECT DISTINCT visa_class FROM lca_records WHERE visa_class IS NOT NULL ORDER BY visa_class"
    )
    fiscal_years = query_df(
        "SELECT DISTINCT fiscal_year FROM lca_records WHERE fiscal_year IS NOT NULL ORDER BY fiscal_year"
    )
    case_statuses = query_df(
        "SELECT DISTINCT case_status FROM lca_records WHERE case_status IS NOT NULL ORDER BY case_status"
    )
    ats_platforms = query_df(
        "SELECT DISTINCT ats_platform FROM job_listings WHERE ats_platform IS NOT NULL AND ats_platform != '' ORDER BY ats_platform"
    )

    return {
        "worksite_state": [r["worksite_state"] for r in worksite_states],
        "pw_wage_level": [r["pw_wage_level"] for r in pw_wage_levels],
        "visa_class": [r["visa_class"] for r in visa_classes],
        "fiscal_year": [int(r["fiscal_year"]) for r in fiscal_years if r["fiscal_year"] is not None],
        "case_status": [r["case_status"] for r in case_statuses],
        "ats_platform": [r["ats_platform"] for r in ats_platforms],
    }
