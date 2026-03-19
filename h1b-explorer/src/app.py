"""H1BEE — H-1B LCA Data Explorer."""

from __future__ import annotations
import streamlit as st
import pandas as pd
import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta
from io import BytesIO

sys.path.insert(0, os.path.dirname(__file__))

# Inject Streamlit secrets into environment before any DB imports
if "DATABASE_URL" not in os.environ:
    try:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    except KeyError:
        st.error("DATABASE_URL not found in Streamlit secrets. Go to Settings → Secrets and add it.")
        st.stop()
    except Exception as e:
        st.error(f"Error reading Streamlit secrets: {e}")
        st.stop()

# Inject optional Brave Search API key (enables ATS auto-detection fallback)
if "BRAVE_API_KEY" not in os.environ:
    try:
        os.environ["BRAVE_API_KEY"] = st.secrets["BRAVE_API_KEY"]
    except (KeyError, Exception):
        pass  # Optional — Brave fallback just won't run without it

from db import (get_connection, query_df, get_distinct_values, get_all_filter_options,
                ensure_job_listings_table, get_cached_jobs, upsert_job_listings,
                search_job_listings, get_job_coverage)
from filters import build_where_clause
from scraper import scrape_jobs

st.set_page_config(page_title="H1BEE — H-1B Explorer", layout="wide")
st.title("H1BEE — H-1B LCA Data Explorer")

# ── DB connection check + one-time table migration ────────────────────────────
try:
    _c = get_connection()
    _c.close()
except Exception as e:
    st.error(f"Could not connect to database: {e}")
    st.stop()

@st.cache_resource
def _init_job_listings():
    try:
        ensure_job_listings_table()
    except Exception:
        pass  # Non-fatal — table may already exist

_init_job_listings()

# ── Cached filter options + total count (single DB connection) ────────────────
@st.cache_data(ttl=3600, show_spinner="Loading...")
def load_filter_options():
    return get_all_filter_options()

opts = load_filter_options()
st.caption(f"{opts['total_count']:,} total LCA records")

# ── Sidebar filters (wrapped in form — query only fires on Apply) ─────────────
st.sidebar.header("Filters")

with st.sidebar.form("filters_form"):
    default_statuses = [s for s in opts["statuses"] if s.upper() == "CERTIFIED"] or opts["statuses"][:1]
    default_years    = [y for y in opts["years"] if y in (2025, 2026)]
    default_states   = [s for s in opts["states"] if s in ("NY", "NJ")]
    default_levels   = [l for l in opts["levels"] if l in ("I", "II", "Level I", "Level II")]
    selected_statuses = st.multiselect("Case Status", opts["statuses"], default=default_statuses)
    selected_years    = st.multiselect("Fiscal Year", opts["years"], default=default_years)
    selected_states   = st.multiselect("Worksite State", opts["states"], default=default_states)
    city_input        = st.text_input("Worksite City (contains)")
    employer_input    = st.text_input("Employer Name (contains)")
    job_title_input   = st.text_input("Job Title (comma-separated)")
    selected_levels   = st.multiselect("Wage Level", opts["levels"], default=default_levels)
    st.subheader("Annual Wage Range")
    wage_min = st.number_input("Min Annual Wage", min_value=0, value=0, step=10000)
    wage_max = st.number_input("Max Annual Wage", min_value=0, value=0, step=10000)
    st.form_submit_button("Apply Filters", use_container_width=True)

filters = {}
if selected_statuses: filters["case_statuses"] = selected_statuses
if selected_years:    filters["fiscal_years"]  = selected_years
if selected_states:   filters["states"]        = selected_states
if city_input.strip():      filters["city"]          = city_input.strip()
if employer_input.strip():  filters["employer_name"] = employer_input.strip()
if job_title_input.strip(): filters["job_title"]     = job_title_input.strip()
if selected_levels:   filters["wage_levels"]   = selected_levels
if wage_min > 0:      filters["wage_min"]      = wage_min
if wage_max > 0:      filters["wage_max"]      = wage_max

where_sql, params = build_where_clause(filters)

HEAVY_FILTERS = {"states", "city", "job_title", "soc_titles", "wage_levels", "wage_min", "wage_max", "fiscal_years"}
use_stats_view = not any(k in filters for k in HEAVY_FILTERS)

# ── Load all companies (cached; pagination done in Python) ────────────────────
@st.cache_data(ttl=300)
def load_all_companies(use_stats: bool, where_sql: str, params: tuple,
                       stats_statuses: tuple, stats_employer: str) -> pd.DataFrame:
    if use_stats:
        clauses, p = [], []
        if stats_statuses:
            clauses.append("case_status IN (" + ",".join(["%s"] * len(stats_statuses)) + ")")
            p.extend(stats_statuses)
        if stats_employer:
            clauses.append("employer_name LIKE %s")
            p.append(f"%{stats_employer.upper()}%")
        w = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT
                employer_name     AS "Company",
                SUM(total_lcas)   AS "Total LCAs",
                SUM(unique_roles) AS "Unique Roles",
                SUM(states_count) AS "States",
                MIN(min_salary)   AS "Min Salary",
                MAX(max_salary)   AS "Max Salary"
            FROM company_stats {w}
            GROUP BY employer_name
            ORDER BY SUM(total_lcas) DESC
        """
        return query_df(sql, tuple(p))
    else:
        sql = f"""
            SELECT
                employer_name                              AS "Company",
                COUNT(*)                                   AS "Total LCAs",
                COUNT(DISTINCT worksite_state)             AS "States",
                ROUND(MIN(annual_wage_from)::numeric, 0)   AS "Min Salary",
                ROUND(MAX(annual_wage_from)::numeric, 0)   AS "Max Salary"
            FROM lca_records
            {where_sql}
            GROUP BY employer_name
            ORDER BY COUNT(*) DESC
        """
        return query_df(sql, tuple(params))

all_companies_df = load_all_companies(
    use_stats_view, where_sql, tuple(params),
    stats_statuses=tuple(selected_statuses),
    stats_employer=employer_input.strip(),
)
company_count = len(all_companies_df)

# ── Pagination state ──────────────────────────────────────────────────────────
PAGE_SIZE = 50
total_pages = max(1, -(-company_count // PAGE_SIZE))

if "page" not in st.session_state:
    st.session_state.page = 1
if "last_filter_key" not in st.session_state:
    st.session_state.last_filter_key = ""
filter_key = str((where_sql, params))
if filter_key != st.session_state.last_filter_key:
    st.session_state.page = 1
    st.session_state.last_filter_key = filter_key
st.session_state.page = max(1, min(st.session_state.page, total_pages))

# ── DB helpers ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_company_detail(company: str, where_sql: str, params: tuple) -> pd.DataFrame:
    detail_where = (where_sql + " AND employer_name = %s") if where_sql else "WHERE employer_name = %s"
    sql = f"""
        SELECT
            case_number       AS "Case #",
            case_status       AS "Status",
            job_title         AS "Job Title",
            soc_title         AS "SOC Title",
            annual_wage_from  AS "Annual Wage",
            pw_wage_level     AS "Level",
            worksite_city     AS "City",
            worksite_state    AS "State",
            begin_date        AS "Start",
            decision_date     AS "Decision",
            fiscal_year       AS "FY"
        FROM lca_records
        {detail_where}
        ORDER BY decision_date DESC
        LIMIT 500
    """
    df = query_df(sql, tuple(params) + (company,))
    if "Annual Wage" in df.columns:
        df["Annual Wage"] = df["Annual Wage"].apply(
            lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A"
        )
    return df

@st.cache_data(ttl=600)
def get_career_url(company: str) -> str:
    conn = get_connection()
    row = conn.execute(
        "SELECT career_url FROM career_urls WHERE employer_name = %s", (company,)
    ).fetchone()
    conn.close()
    return row[0] if row and row[0] else ""

@st.cache_data(ttl=60)
def get_tracked_companies() -> set:
    rows = query_df("SELECT DISTINCT company FROM job_applications")
    return set(rows["company"].tolist()) if not rows.empty else set()

def add_to_tracker(company: str):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        """INSERT INTO job_applications (company, job_title, job_urls, stage, notes, created_at, updated_at)
           VALUES (%s, '', '', 'Interested', '', %s, %s)""",
        (company, now, now),
    )
    conn.commit()
    conn.close()

def add_job_to_tracker(company: str, job_title: str, job_url: str):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        """INSERT INTO job_applications (company, job_title, job_urls, stage, notes, created_at, updated_at)
           VALUES (%s, %s, %s, 'Interested', '', %s, %s)""",
        (company, job_title, job_url, now, now),
    )
    conn.commit()
    conn.close()


def remove_from_tracker(company: str):
    conn = get_connection()
    conn.execute("DELETE FROM job_applications WHERE company = %s", (company,))
    conn.commit()
    conn.close()

def load_tracker() -> pd.DataFrame:
    return query_df("""
        SELECT id, company AS "Company", job_title AS "Job Title",
               job_urls AS "Link", stage AS "Status", notes AS "Notes"
        FROM job_applications
        ORDER BY updated_at DESC
    """)

def save_tracker_changes(changes: dict, base_df: pd.DataFrame):
    col_map = {"Company": "company", "Job Title": "job_title",
               "Link": "job_urls", "Status": "stage", "Notes": "notes"}
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    for row_idx, col_updates in changes.get("edited_rows", {}).items():
        row_id = base_df.iloc[row_idx]["id"]
        for col, val in col_updates.items():
            db_col = col_map.get(col)
            if db_col:
                conn.execute(
                    f"UPDATE job_applications SET {db_col} = %s, updated_at = %s WHERE id = %s",
                    (val, now, row_id),
                )
    for row in changes.get("added_rows", []):
        conn.execute(
            """INSERT INTO job_applications (company, job_title, job_urls, stage, notes, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (row.get("Company", ""), row.get("Job Title", ""), row.get("Link", ""),
             row.get("Status", "Interested"), row.get("Notes", ""), now, now),
        )
    for row_idx in changes.get("deleted_rows", []):
        row_id = base_df.iloc[row_idx]["id"]
        conn.execute("DELETE FROM job_applications WHERE id = %s", (row_id,))
    conn.commit()
    conn.close()

# ── Job listing helpers ───────────────────────────────────────────────────────
def _is_stale(scraped_at_str: str, hours: int = 6) -> bool:
    if not scraped_at_str:
        return True
    try:
        scraped = datetime.fromisoformat(str(scraped_at_str).replace("Z", "+00:00"))
        if scraped.tzinfo is None:
            scraped = scraped.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - scraped) > timedelta(hours=hours)
    except Exception:
        return True


def _format_age(scraped_at_str: str) -> str:
    if not scraped_at_str:
        return "unknown"
    try:
        scraped = datetime.fromisoformat(str(scraped_at_str).replace("Z", "+00:00"))
        if scraped.tzinfo is None:
            scraped = scraped.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - scraped
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m ago"
        elif hours < 24:
            return f"{hours:.1f}h ago"
        return f"{delta.days}d ago"
    except Exception:
        return "unknown"


def _show_jobs_section(company: str, career_url: str, key_suffix: str):
    st.markdown("#### Open Positions")

    jobs, cached_ats, scraped_at = get_cached_jobs(company)

    col_info, col_btn = st.columns([4, 1])
    with col_info:
        if jobs:
            st.caption(f"{len(jobs)} jobs via **{cached_ats}** · scraped {_format_age(scraped_at)}")
        else:
            st.caption("No jobs fetched yet")
    with col_btn:
        btn_label = "Refresh" if jobs else "Fetch Jobs"
        if st.button(btn_label, key=f"fetch_jobs_{key_suffix}", use_container_width=True):
            with st.spinner("Detecting ATS and fetching jobs..."):
                new_jobs, new_ats, detected_url = scrape_jobs(career_url, company_name=company)
            # If we found a better ATS URL via redirect/brute-force, save it
            if detected_url and detected_url != career_url:
                conn = get_connection()
                conn.execute(
                    "UPDATE career_urls SET career_url = %s WHERE employer_name = %s",
                    (detected_url, company),
                )
                conn.commit()
                conn.close()
                get_career_url.clear()
            if new_ats in ("unknown", "workday") and not new_jobs:
                fallback = career_url or (
                    "https://www.google.com/search?q=" + urllib.parse.quote(company + " jobs")
                )
                msg = "Workday — manual browsing required" if new_ats == "workday" else "ATS not detected"
                st.warning(f"Could not auto-scrape ({msg}). [Browse directly]({fallback})")
                if new_ats != "workday":
                    st.session_state[f"_show_url_override_{key_suffix}"] = True
            else:
                upsert_job_listings(company, new_jobs, new_ats)
                st.rerun()

    # Manual URL override — shown after a failed fetch, or via expander
    override_key = f"_show_url_override_{key_suffix}"
    if st.session_state.get(override_key) or st.checkbox(
        "Set ATS URL manually", key=f"_url_override_toggle_{key_suffix}", value=False
    ):
        st.session_state[override_key] = True
        manual_url = st.text_input(
            "Paste Greenhouse / Lever / Ashby URL:",
            placeholder="https://job-boards.greenhouse.io/yourcompany",
            key=f"_manual_url_{key_suffix}",
        )
        if st.button("Save & Fetch", key=f"_manual_save_{key_suffix}"):
            url_to_save = manual_url.strip()
            if url_to_save:
                conn = get_connection()
                conn.execute(
                    """INSERT INTO career_urls (employer_name, career_url, looked_up_at)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (employer_name) DO UPDATE
                       SET career_url=EXCLUDED.career_url, looked_up_at=EXCLUDED.looked_up_at""",
                    (company, url_to_save, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                conn.close()
                get_career_url.clear()
                st.session_state.pop(override_key, None)
                st.rerun()

    if not jobs:
        return

    kw = st.text_input(
        "Filter jobs", placeholder="e.g. engineer, analyst, manager",
        key=f"job_filter_{key_suffix}", label_visibility="collapsed",
    )

    filtered = jobs
    if kw.strip():
        kw_lower = kw.strip().lower()
        filtered = [
            j for j in jobs
            if kw_lower in j["title"].lower() or kw_lower in j.get("department", "").lower()
        ]

    if not filtered:
        st.caption("No jobs match that filter.")
        return

    df_jobs = pd.DataFrame(filtered)[["title", "location", "department", "url"]]
    df_jobs.columns = ["Job Title", "Location", "Department", "Link"]
    st.dataframe(
        df_jobs,
        use_container_width=True,
        hide_index=True,
        column_config={"Link": st.column_config.LinkColumn("Link", display_text="Apply →")},
        height=min(450, 38 + len(filtered) * 35),
    )


# ── Shared drill-down ─────────────────────────────────────────────────────────
def show_drilldown(company: str, where_sql: str, params: tuple, key_suffix: str = ""):
    tracked = get_tracked_companies()
    with st.container(border=True):
        col_name, col_btn = st.columns([5, 1])
        with col_name:
            st.markdown(f"### {company}")
        with col_btn:
            if company in tracked:
                if st.button("Remove from Tracker", key=f"remove_btn_{key_suffix}", use_container_width=True):
                    remove_from_tracker(company)
                    st.rerun()
            else:
                if st.button("+ Save to Tracker", key=f"save_btn_{key_suffix}", use_container_width=True):
                    add_to_tracker(company)
                    st.rerun()

        career_url = get_career_url(company)
        if career_url:
            st.markdown(f"[Careers Page]({career_url})")
        else:
            search_url = "https://www.google.com/search?q=" + urllib.parse.quote(company + " careers")
            st.markdown(f"[Search Careers on Google]({search_url})")

        _show_jobs_section(company, career_url, key_suffix)

        with st.expander(f"H-1B LCA Records", expanded=False):
            df_detail = load_company_detail(company, where_sql, params)
            st.write(f"**{len(df_detail):,} records** (capped at 500)")
            st.dataframe(df_detail, use_container_width=True, hide_index=True)

# ── Shared company table + pagination ─────────────────────────────────────────
def show_company_table(source_df: pd.DataFrame, page_key: str, table_key: str,
                       search_pending_key: str, search_key: str,
                       drilldown_where: str = "", drilldown_params: tuple = ()):
    """Render sort controls, table, pagination, and drill-down for any company DataFrame."""
    count = len(source_df)
    total_pg = max(1, -(-count // PAGE_SIZE))
    st.session_state[page_key] = max(1, min(st.session_state.get(page_key, 1), total_pg))

    # ── Search bar — apply any pending sync from row click ────────────────────
    if search_pending_key in st.session_state:
        st.session_state[search_key] = st.session_state.pop(search_pending_key)

    all_names = [""] + source_df["Company"].tolist()
    st.selectbox(
        "Search for a company",
        options=all_names,
        format_func=lambda x: "Type to search a company..." if x == "" else x,
        key=search_key,
    )
    search_company = st.session_state.get(search_key, "")

    st.subheader(f"Companies ({count:,} results)")

    if count == 0:
        st.info("No results.")
        return

    # ── Sort controls ─────────────────────────────────────────────────────────
    sort_cols = [c for c in ["Total LCAs", "Min Salary", "Max Salary", "Avg Salary", "States", "Company"]
                 if c in source_df.columns]
    sc1, sc2 = st.columns([3, 1])
    with sc1:
        sort_by = st.selectbox("Sort by", sort_cols, index=0,
                               label_visibility="collapsed", key=f"sort_{table_key}")
    with sc2:
        sort_asc = st.checkbox("Ascending", value=False, key=f"asc_{table_key}")

    sorted_df = source_df.sort_values(sort_by, ascending=sort_asc, na_position="last")
    offset = (st.session_state[page_key] - 1) * PAGE_SIZE
    page_df = sorted_df.iloc[offset : offset + PAGE_SIZE].reset_index(drop=True)

    # Format salary columns for display (copy so cache isn't mutated)
    display_df = page_df.copy()
    for col in ["Min Salary", "Avg Salary", "Max Salary"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")

    selection = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=600,
        key=table_key,
    )

    # ── Pagination controls ───────────────────────────────────────────────────
    col_prev, col_page, col_info, col_next = st.columns([0.3, 0.4, 2.5, 0.3])
    with col_prev:
        prev_clicked = st.button("←", disabled=st.session_state[page_key] <= 1,
                                 key=f"prev_{table_key}")
    with col_page:
        new_page = st.number_input("Page", min_value=1, max_value=total_pg,
                                   value=st.session_state[page_key],
                                   label_visibility="collapsed", key=f"pgnum_{table_key}")
    with col_info:
        st.markdown(
            f"<p style='margin:0;padding-top:6px;font-size:0.85rem;color:gray;'>"
            f"Page {st.session_state[page_key]} of {total_pg:,} ({count:,} companies)</p>",
            unsafe_allow_html=True,
        )
    with col_next:
        next_clicked = st.button("→", disabled=st.session_state[page_key] >= total_pg,
                                 key=f"next_{table_key}")

    if prev_clicked:
        st.session_state[page_key] -= 1
        st.rerun()
    elif next_clicked:
        st.session_state[page_key] += 1
        st.rerun()
    elif int(new_page) != st.session_state[page_key]:
        st.session_state[page_key] = int(new_page)
        st.rerun()

    # ── Sync row click → search bar (via pending key, applied next render) ────
    if selection and selection.selection and selection.selection.rows:
        idx = selection.selection.rows[0]
        if idx < len(page_df):
            table_company = page_df.iloc[idx]["Company"]
            if table_company != search_company:
                st.session_state[search_pending_key] = table_company
                st.rerun()

    # ── Drill-down ────────────────────────────────────────────────────────────
    selected_company = search_company or None
    if selected_company:
        show_drilldown(selected_company, drilldown_where, drilldown_params,
                       key_suffix=table_key)

    # ── Export ────────────────────────────────────────────────────────────────
    buf = BytesIO()
    display_df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    st.download_button("📥 Export This Page (.xlsx)", data=buf.getvalue(),
                       file_name="h1b_results.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"export_{table_key}")

# ── Global custom styles ──────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Job cards ── */
.job-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 2px;
    min-height: 130px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.job-company {
    font-size: 0.72rem;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 75%;
}
.job-title {
    font-size: 0.93rem;
    font-weight: 700;
    color: #0f172a;
    margin: 5px 0 6px 0;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.job-meta { font-size: 0.78rem; color: #94a3b8; }
.ats-pill {
    font-size: 0.62rem;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    white-space: nowrap;
}
.ats-greenhouse { background: #dcfce7; color: #15803d; }
.ats-lever      { background: #dbeafe; color: #1d4ed8; }
.ats-ashby      { background: #fef9c3; color: #a16207; }

/* ── Tracker kanban ── */
.kanban-header {
    font-size: 0.75rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 7px 12px;
    border-radius: 8px;
    text-align: center;
    margin-bottom: 10px;
}
.stage-Interested   { background:#f1f5f9; color:#475569; }
.stage-Applied      { background:#dbeafe; color:#1d4ed8; }
.stage-Phone-Screen { background:#ede9fe; color:#6d28d9; }
.stage-Interview    { background:#fef3c7; color:#b45309; }
.stage-Offer        { background:#dcfce7; color:#15803d; }
.stage-Rejected     { background:#fee2e2; color:#b91c1c; }

.app-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 6px;
}
.app-card-company {
    font-size: 0.7rem;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.app-card-title {
    font-size: 0.88rem;
    font-weight: 700;
    color: #0f172a;
    margin: 3px 0 4px 0;
    line-height: 1.3;
}
.app-card-notes { font-size: 0.78rem; color: #94a3b8; font-style: italic; }

/* ── Coverage pill row ── */
.cov-pill {
    display: inline-block;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.78rem;
    color: #475569;
    margin-right: 8px;
}
.cov-pill b { color: #0f172a; }
</style>
""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_explorer, tab_jobs, tab_tracker = st.tabs(["🔍 Explorer", "💼 Jobs", "📋 Tracker"])

# ══════════════════════════════════════════════════════════════════════════════
with tab_explorer:
    show_company_table(
        source_df=all_companies_df,
        page_key="page",
        table_key="main_table",
        search_pending_key="_pending_search",
        search_key="company_search",
        drilldown_where=where_sql,
        drilldown_params=tuple(params),
    )

# ══════════════════════════════════════════════════════════════════════════════
with tab_jobs:

    @st.cache_data(ttl=120)
    def _job_coverage():
        return get_job_coverage()

    cov = _job_coverage()

    # ── Coverage pills ────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="margin-bottom:16px">'
        f'<span class="cov-pill"><b>{cov["total_jobs"]:,}</b> jobs indexed</span>'
        f'<span class="cov-pill"><b>{cov["companies_scraped"]:,}</b> companies scraped</span>'
        f'<span class="cov-pill"><b>{cov["ats_detected"]:,}</b> H-1B employers with ATS</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── State → ILIKE pattern mapping ─────────────────────────────────────────
    STATE_PATTERNS = {
        "NY": [", NY", "New York"],
        "NJ": [", NJ", "New Jersey", "Jersey City"],
        "CA": [", CA", "California", "San Francisco", "Los Angeles"],
        "WA": [", WA", "Seattle"],
        "TX": [", TX", "Texas"],
        "MA": [", MA", "Boston"],
        "IL": [", IL", "Chicago"],
        "GA": [", GA", "Atlanta"],
        "CO": [", CO", "Denver"],
        "FL": [", FL", "Miami", "Florida"],
        "VA": [", VA", "Virginia"],
        "NC": [", NC", "Charlotte", "Raleigh"],
        "PA": [", PA", "Philadelphia"],
        "OH": [", OH", "Ohio"],
        "AZ": [", AZ", "Phoenix"],
    }

    # ── Search bar ────────────────────────────────────────────────────────────
    jc1, jc2 = st.columns([4, 3])
    with jc1:
        job_keyword = st.text_input("", placeholder="🔍  Search by job title (e.g. software engineer)",
                                    label_visibility="collapsed", key="job_keyword")
    with jc2:
        job_company = st.text_input("", placeholder="🏢  Filter by company name",
                                    label_visibility="collapsed", key="job_company_filter")

    # ── Location + work type filters ──────────────────────────────────────────
    fc1, fc2 = st.columns([3, 2])
    with fc1:
        selected_states = st.multiselect(
            "State",
            options=list(STATE_PATTERNS.keys()),
            default=["NY", "NJ"],
            label_visibility="collapsed",
            placeholder="📍 Filter by state (default: NY/NJ)",
            key="job_states",
        )
    with fc2:
        work_type = st.radio(
            "Work type",
            ["All", "Remote", "Hybrid", "On-site"],
            horizontal=True,
            label_visibility="collapsed",
            key="job_work_type",
        )

    # Build location patterns from selected states
    state_patterns: list[str] = []
    for s in selected_states:
        state_patterns.extend(STATE_PATTERNS.get(s, [f", {s}"]))

    # ── Results ───────────────────────────────────────────────────────────────
    if cov["total_jobs"] == 0:
        st.markdown("""
        <div style="text-align:center; padding:60px 20px; color:#94a3b8;">
            <div style="font-size:2.5rem; margin-bottom:12px">💼</div>
            <div style="font-size:1.1rem; font-weight:600; color:#475569; margin-bottom:8px">No jobs scraped yet</div>
            <div style="font-size:0.85rem">Run <code>python scrape_all.py</code> to populate job listings,<br>
            or click <b>Fetch Jobs</b> on any company in the Explorer tab.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        @st.cache_data(ttl=120, show_spinner="Searching...")
        def _search_jobs(kw: str, co: str, states: tuple, wtype: str):
            return search_job_listings(
                keyword=kw, company=co,
                state_patterns=list(states) if states else None,
                work_type=wtype,
                limit=500,
            )

        jobs_df = _search_jobs(
            job_keyword.strip(), job_company.strip(),
            tuple(state_patterns), work_type,
        )

        if jobs_df.empty and not (job_keyword or job_company):
            st.markdown("""
            <div style="text-align:center; padding:40px 20px; color:#94a3b8;">
                <div style="font-size:1.8rem; margin-bottom:8px">🔍</div>
                <div style="font-size:0.95rem; color:#475569">Search above to find H-1B sponsored jobs</div>
            </div>
            """, unsafe_allow_html=True)
        elif jobs_df.empty:
            st.markdown("""
            <div style="text-align:center; padding:40px 20px; color:#94a3b8;">
                <div style="font-size:1.8rem; margin-bottom:8px">😕</div>
                <div style="font-size:0.95rem; color:#475569">No jobs match your search</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            JOBS_PAGE_SIZE = 30
            total_jobs_found = len(jobs_df)

            if "jobs_page" not in st.session_state:
                st.session_state.jobs_page = 1
            if "last_job_search" not in st.session_state:
                st.session_state.last_job_search = ""
            search_key = f"{job_keyword}|{job_company}|{'_'.join(selected_states)}|{work_type}"
            if search_key != st.session_state.last_job_search:
                st.session_state.jobs_page = 1
                st.session_state.last_job_search = search_key

            total_job_pages = max(1, -(-total_jobs_found // JOBS_PAGE_SIZE))
            st.session_state.jobs_page = max(1, min(st.session_state.jobs_page, total_job_pages))

            offset = (st.session_state.jobs_page - 1) * JOBS_PAGE_SIZE
            page_jobs = jobs_df.iloc[offset: offset + JOBS_PAGE_SIZE]

            # Result count + pagination header
            rc1, rc2 = st.columns([4, 2])
            with rc1:
                st.markdown(
                    f'<p style="margin:0;padding-top:4px;font-size:0.85rem;color:#64748b;">'
                    f'<b style="color:#0f172a">{total_jobs_found:,}</b> jobs found'
                    f' · page {st.session_state.jobs_page} of {total_job_pages}</p>',
                    unsafe_allow_html=True,
                )
            with rc2:
                pg_c1, pg_c2, pg_c3 = st.columns(3)
                with pg_c1:
                    if st.button("←", key="jobs_prev", disabled=st.session_state.jobs_page <= 1,
                                 use_container_width=True):
                        st.session_state.jobs_page -= 1
                        st.rerun()
                with pg_c2:
                    st.markdown(
                        f'<p style="text-align:center;margin:0;padding-top:6px;font-size:0.85rem;">'
                        f'{st.session_state.jobs_page}/{total_job_pages}</p>',
                        unsafe_allow_html=True,
                    )
                with pg_c3:
                    if st.button("→", key="jobs_next",
                                 disabled=st.session_state.jobs_page >= total_job_pages,
                                 use_container_width=True):
                        st.session_state.jobs_page += 1
                        st.rerun()

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            # ── Job cards grid (3 columns) ────────────────────────────────────
            ATS_COLORS = {
                "greenhouse": ("ats-greenhouse", "Greenhouse"),
                "lever":      ("ats-lever",      "Lever"),
                "ashby":      ("ats-ashby",       "Ashby"),
            }

            cols = st.columns(3)
            for i, (_, job) in enumerate(page_jobs.iterrows()):
                ats_key   = str(job.get("ats_platform", "")).lower()
                pill_cls, pill_label = ATS_COLORS.get(ats_key, ("ats-pill", ats_key.title()))
                location  = job.get("location", "") or ""
                dept      = job.get("department", "") or ""
                meta_parts = [p for p in [location, dept] if p]
                meta      = " · ".join(meta_parts) if meta_parts else "Location not listed"

                with cols[i % 3]:
                    st.markdown(f"""
                    <div class="job-card">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px">
                            <span class="job-company">{job['employer_name']}</span>
                            <span class="ats-pill {pill_cls}">{pill_label}</span>
                        </div>
                        <div class="job-title">{job['job_title']}</div>
                        <div class="job-meta">📍 {meta}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    btn_a, btn_s = st.columns(2)
                    with btn_a:
                        st.link_button("Apply →", job.get("job_url", "#"),
                                       use_container_width=True)
                    with btn_s:
                        if st.button("+ Save", key=f"save_job_{offset+i}",
                                     use_container_width=True):
                            add_job_to_tracker(job["employer_name"], job["job_title"],
                                               job.get("job_url", ""))
                            get_tracked_companies.clear()
                            st.toast(f"Saved: {job['job_title']}", icon="✅")

# ══════════════════════════════════════════════════════════════════════════════
with tab_tracker:

    STAGES = ["Interested", "Applied", "Phone Screen", "Interview", "Offer", "Rejected"]
    STAGE_COLORS = {
        "Interested":   ("#f1f5f9", "#475569"),
        "Applied":      ("#dbeafe", "#1d4ed8"),
        "Phone Screen": ("#ede9fe", "#6d28d9"),
        "Interview":    ("#fef3c7", "#b45309"),
        "Offer":        ("#dcfce7", "#15803d"),
        "Rejected":     ("#fee2e2", "#b91c1c"),
    }

    tracker_df = load_tracker()

    if tracker_df.empty:
        st.markdown("""
        <div style="text-align:center; padding:60px 20px;">
            <div style="font-size:2.5rem; margin-bottom:12px">📋</div>
            <div style="font-size:1.1rem; font-weight:600; color:#475569; margin-bottom:8px">
                Your tracker is empty
            </div>
            <div style="font-size:0.85rem; color:#94a3b8">
                Search for jobs in the <b>Jobs</b> tab and click <b>+ Save</b>,<br>
                or click <b>+ Save to Tracker</b> on any company in the Explorer.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # ── Summary bar ───────────────────────────────────────────────────────
        counts = tracker_df["Status"].value_counts().to_dict()
        pills_html = ""
        for stage in STAGES:
            n = counts.get(stage, 0)
            if n == 0:
                continue
            bg, fg = STAGE_COLORS[stage]
            pills_html += (
                f'<span style="background:{bg};color:{fg};font-size:0.75rem;font-weight:700;'
                f'padding:4px 12px;border-radius:20px;margin-right:8px;display:inline-block;margin-bottom:4px">'
                f'{stage} <b>{n}</b></span>'
            )
        st.markdown(f'<div style="margin-bottom:20px">{pills_html}</div>', unsafe_allow_html=True)

        # ── Active stage filter ────────────────────────────────────────────────
        active_stages = [s for s in STAGES if s in counts]
        selected_stage = st.radio(
            "Filter by stage",
            ["All"] + active_stages,
            horizontal=True,
            label_visibility="collapsed",
            key="tracker_stage_filter",
        )

        view_df = tracker_df if selected_stage == "All" else tracker_df[tracker_df["Status"] == selected_stage]
        st.markdown(f'<p style="font-size:0.82rem;color:#94a3b8;margin:8px 0 16px">{len(view_df)} application{"s" if len(view_df)!=1 else ""}</p>',
                    unsafe_allow_html=True)

        # ── Application cards ─────────────────────────────────────────────────
        for _, row in view_df.iterrows():
            row_id = row["id"]
            stage  = row.get("Status", "Interested")
            bg, fg = STAGE_COLORS.get(stage, ("#f1f5f9", "#475569"))
            job_url = row.get("Link", "") or ""
            notes   = row.get("Notes", "") or ""
            job_title = row.get("Job Title", "") or ""

            with st.container():
                st.markdown(f"""
                <div class="app-card">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start">
                        <div style="flex:1;min-width:0">
                            <div class="app-card-company">{row['Company']}</div>
                            <div class="app-card-title">{job_title or '(no job title)'}</div>
                            {f'<div class="app-card-notes">{notes}</div>' if notes else ''}
                        </div>
                        <span style="background:{bg};color:{fg};font-size:0.68rem;font-weight:700;
                                     padding:3px 10px;border-radius:20px;white-space:nowrap;
                                     margin-left:10px;flex-shrink:0">{stage}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                c1, c2, c3, c4 = st.columns([3, 2, 2, 1])

                with c1:
                    # Inline notes edit
                    new_notes = st.text_input(
                        "Notes", value=notes,
                        placeholder="Add notes...",
                        label_visibility="collapsed",
                        key=f"notes_{row_id}",
                    )
                with c2:
                    new_stage = st.selectbox(
                        "Stage", STAGES,
                        index=STAGES.index(stage) if stage in STAGES else 0,
                        label_visibility="collapsed",
                        key=f"stage_{row_id}",
                    )
                with c3:
                    if job_url:
                        st.link_button("View Job →", job_url, use_container_width=True)
                with c4:
                    if st.button("🗑", key=f"del_{row_id}", use_container_width=True,
                                 help="Remove from tracker"):
                        conn = get_connection()
                        conn.execute("DELETE FROM job_applications WHERE id = %s", (row_id,))
                        conn.commit()
                        conn.close()
                        get_tracked_companies.clear()
                        st.rerun()

                # Save if stage or notes changed
                if new_stage != stage or new_notes != notes:
                    now = datetime.now(timezone.utc).isoformat()
                    conn = get_connection()
                    conn.execute(
                        "UPDATE job_applications SET stage=%s, notes=%s, updated_at=%s WHERE id=%s",
                        (new_stage, new_notes, now, row_id),
                    )
                    conn.commit()
                    conn.close()
                    st.rerun()

                st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)

# ── Attribution ───────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Data from the [U.S. Department of Labor — OFLC](https://flag.dol.gov/programs/lca). "
    "Not affiliated with or endorsed by the DOL."
)
