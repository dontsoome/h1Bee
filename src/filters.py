"""Build dynamic SQL WHERE clauses from filter parameters."""


def build_where_clause(filters: dict) -> tuple[str, list]:
    """
    Build a WHERE clause from a dict of filter parameters.

    Supported filters:
        states: list[str]         — worksite_state IN (...)
        city: str                 — worksite_city LIKE %...%
        job_title: str            — job_title LIKE %phrase1% OR LIKE %phrase2% (comma-separated phrases)
        soc_codes: list[str]      — soc_code IN (...)
        wage_levels: list[str]    — pw_wage_level IN (...)
        wage_min: float           — annual_wage_from >= ...
        wage_max: float           — annual_wage_from <= ...
        fiscal_years: list[int]   — fiscal_year IN (...)
        case_statuses: list[str]  — case_status IN (...)
        employer_name: str        — employer_name LIKE %...%

    Returns (where_sql, params) where where_sql starts with "WHERE ..." or is empty.
    """
    clauses = []
    params = []

    # Multi-select: states
    if filters.get("states"):
        placeholders = ", ".join(["%s"] * len(filters["states"]))
        clauses.append(f"worksite_state IN ({placeholders})")
        params.extend(filters["states"])

    # Text contains: city
    if filters.get("city"):
        clauses.append("worksite_city LIKE %s")
        params.append(f"%{filters['city'].upper()}%")

    # Text contains with OR for multiple keywords: job_title
    if filters.get("job_title"):
        keywords = [k.strip() for k in filters["job_title"].split(",") if k.strip()]
        if keywords:
            kw_clauses = []
            for kw in keywords:
                kw_clauses.append("job_title LIKE %s")
                params.append(f"%{kw.upper()}%")
            clauses.append(f"({' OR '.join(kw_clauses)})")

    # Multi-select: soc_codes
    if filters.get("soc_codes"):
        placeholders = ", ".join(["%s"] * len(filters["soc_codes"]))
        clauses.append(f"soc_code IN ({placeholders})")
        params.extend(filters["soc_codes"])

    # Multi-select: soc_titles
    if filters.get("soc_titles"):
        placeholders = ", ".join(["%s"] * len(filters["soc_titles"]))
        clauses.append(f"soc_title IN ({placeholders})")
        params.extend(filters["soc_titles"])

    # Multi-select: wage_levels
    if filters.get("wage_levels"):
        placeholders = ", ".join(["%s"] * len(filters["wage_levels"]))
        clauses.append(f"pw_wage_level IN ({placeholders})")
        params.extend(filters["wage_levels"])

    # Range: wage
    if filters.get("wage_min") is not None:
        clauses.append("annual_wage_from >= %s")
        params.append(filters["wage_min"])
    if filters.get("wage_max") is not None:
        clauses.append("annual_wage_from <= %s")
        params.append(filters["wage_max"])

    # Multi-select: fiscal_years
    if filters.get("fiscal_years"):
        placeholders = ", ".join(["%s"] * len(filters["fiscal_years"]))
        clauses.append(f"fiscal_year IN ({placeholders})")
        params.extend(filters["fiscal_years"])

    # Multi-select: case_statuses
    if filters.get("case_statuses"):
        placeholders = ", ".join(["%s"] * len(filters["case_statuses"]))
        clauses.append(f"case_status IN ({placeholders})")
        params.extend(filters["case_statuses"])

    # Text contains: employer_name
    if filters.get("employer_name"):
        clauses.append("employer_name LIKE %s")
        params.append(f"%{filters['employer_name'].upper()}%")

    if clauses:
        return "WHERE " + " AND ".join(clauses), params
    return "", []
