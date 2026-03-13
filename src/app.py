"""H1BEE — H-1B LCA Data Explorer."""

from __future__ import annotations
import streamlit as st
import pandas as pd
import os
import sys
import urllib.parse
from datetime import datetime, timezone
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

from db import get_connection, query_df, get_distinct_values
from filters import build_where_clause

st.set_page_config(page_title="H1BEE — H-1B Explorer", layout="wide")
st.title("H1BEE — H-1B LCA Data Explorer")

# ── DB connection check ───────────────────────────────────────────────────────
try:
    _c = get_connection()
    _c.close()
except Exception as e:
    st.error(f"Could not connect to database: {e}")
    st.stop()

# ── Cached filter options ─────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_filter_options():
    return {
        "statuses": get_distinct_values("case_status"),
        "years":    get_distinct_values("fiscal_year"),
        "states":   get_distinct_values("worksite_state"),
        "levels":   get_distinct_values("pw_wage_level"),
    }

@st.cache_data(ttl=3600)
def get_total_count():
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM lca_records").fetchone()[0]
    conn.close()
    return n

opts = load_filter_options()
total_records = get_total_count()
st.caption(f"{total_records:,} total LCA records")

# ── Sidebar filters (wrapped in form — query only fires on Apply) ─────────────
st.sidebar.header("Filters")

with st.sidebar.form("filters_form"):
    default_statuses = [s for s in opts["statuses"] if s.upper() == "CERTIFIED"] or opts["statuses"][:1]
    selected_statuses = st.multiselect("Case Status", opts["statuses"], default=default_statuses)
    selected_years    = st.multiselect("Fiscal Year", opts["years"])
    selected_states   = st.multiselect("Worksite State", opts["states"])
    city_input        = st.text_input("Worksite City (contains)")
    employer_input    = st.text_input("Employer Name (contains)")
    job_title_input   = st.text_input("Job Title (comma-separated)")
    selected_levels   = st.multiselect("Wage Level", opts["levels"])
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
def load_all_companies(use_stats: bool, where_sql: str, params: tuple) -> pd.DataFrame:
    if use_stats:
        clauses, p = [], []
        if selected_statuses:
            clauses.append("case_status IN (" + ",".join(["%s"]*len(selected_statuses)) + ")")
            p.extend(selected_statuses)
        if employer_input.strip():
            clauses.append("employer_name LIKE %s")
            p.append(f"%{employer_input.strip().upper()}%")
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

@st.cache_data(ttl=600)
def load_nynj_companies() -> pd.DataFrame:
    """Pre-filtered: CERTIFIED, NY+NJ, 2025/2026, Wage Level I/II."""
    try:
        return query_df("""
            SELECT
                employer_name AS "Company",
                total_lcas    AS "Total LCAs",
                unique_roles  AS "Unique Roles",
                min_salary    AS "Min Salary",
                avg_salary    AS "Avg Salary",
                max_salary    AS "Max Salary"
            FROM company_stats_nynj
            ORDER BY total_lcas DESC
        """)
    except Exception:
        return query_df("""
            SELECT
                employer_name                              AS "Company",
                COUNT(*)                                   AS "Total LCAs",
                COUNT(DISTINCT job_title)                  AS "Unique Roles",
                ROUND(MIN(annual_wage_from)::numeric, 0)   AS "Min Salary",
                ROUND(AVG(annual_wage_from)::numeric, 0)   AS "Avg Salary",
                ROUND(MAX(annual_wage_from)::numeric, 0)   AS "Max Salary"
            FROM lca_records
            WHERE case_status = 'CERTIFIED'
              AND worksite_state IN ('NY', 'NJ')
              AND fiscal_year IN (2025, 2026)
              AND pw_wage_level = ANY(ARRAY['I', 'II', 'Level I', 'Level II'])
            GROUP BY employer_name
            ORDER BY COUNT(*) DESC
        """)

all_companies_df = load_all_companies(use_stats_view, where_sql, tuple(params))
company_count = len(all_companies_df)

nynj_df = load_nynj_companies()

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

if "nynj_page" not in st.session_state:
    st.session_state.nynj_page = 1
nynj_total_pages = max(1, -(-len(nynj_df) // PAGE_SIZE))
st.session_state.nynj_page = max(1, min(st.session_state.nynj_page, nynj_total_pages))

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

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_explorer, tab_nynj, tab_tracker = st.tabs(["Explorer", "NY/NJ (2025–26)", "Job Tracker"])

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
with tab_nynj:
    st.caption("Pre-filtered: CERTIFIED · NY + NJ · Fiscal 2025–2026 · Wage Level I & II")
    show_company_table(
        source_df=nynj_df,
        page_key="nynj_page",
        table_key="nynj_table",
        search_pending_key="_pending_search_nynj",
        search_key="nynj_company_search",
        drilldown_where="",   # show all records for the company in drill-down
        drilldown_params=(),
    )

# ══════════════════════════════════════════════════════════════════════════════
with tab_tracker:
    st.subheader("Job Tracker")
    tracker_df = load_tracker()

    STAGES = ["Interested", "Applied", "Phone Screen", "Interview", "Offer", "Rejected"]

    if tracker_df.empty:
        st.info("No saved companies yet. Select a company and click '+ Save to Tracker'.")

    col_config = {
        "id":        None,
        "Company":   st.column_config.TextColumn("Company", width="medium"),
        "Job Title": st.column_config.TextColumn("Job Title", width="medium"),
        "Link":      st.column_config.TextColumn("Link", width="medium"),
        "Status":    st.column_config.SelectboxColumn("Status", options=STAGES, width="small"),
        "Notes":     st.column_config.TextColumn("Notes", width="large"),
    }

    st.data_editor(
        tracker_df,
        column_config=col_config,
        column_order=["Company", "Job Title", "Link", "Status", "Notes"],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="tracker_editor",
    )

    if st.button("Save Changes", type="primary", key="tracker_save"):
        changes = st.session_state.get("tracker_editor", {})
        if any(changes.get(k) for k in ("edited_rows", "added_rows", "deleted_rows")):
            save_tracker_changes(changes, tracker_df)
            st.success("Changes saved.")
            st.rerun()
        else:
            st.info("No changes to save.")

# ── Attribution ───────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Data from the [U.S. Department of Labor — OFLC](https://flag.dol.gov/programs/lca). "
    "Not affiliated with or endorsed by the DOL."
)
