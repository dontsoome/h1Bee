"""H1BEE — H-1B LCA Data Explorer."""

from __future__ import annotations
import streamlit as st
import pandas as pd
import os
import sys
import urllib.parse
from datetime import datetime
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

# ── Sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.header("Filters")

default_statuses = [s for s in opts["statuses"] if s.upper() == "CERTIFIED"] or opts["statuses"][:1]
selected_statuses = st.sidebar.multiselect("Case Status", opts["statuses"], default=default_statuses)
selected_years    = st.sidebar.multiselect("Fiscal Year", opts["years"])
selected_states   = st.sidebar.multiselect("Worksite State", opts["states"])
city_input        = st.sidebar.text_input("Worksite City (contains)")
employer_input    = st.sidebar.text_input("Employer Name (contains)")
job_title_input   = st.sidebar.text_input("Job Title (comma-separated)")
selected_levels   = st.sidebar.multiselect("Wage Level", opts["levels"])
st.sidebar.subheader("Annual Wage Range")
wage_min = st.sidebar.number_input("Min Annual Wage", min_value=0, value=0, step=10000)
wage_max = st.sidebar.number_input("Max Annual Wage", min_value=0, value=0, step=10000)

filters = {}
if selected_statuses: filters["case_statuses"] = selected_statuses
if selected_years:    filters["fiscal_years"]  = selected_years
if selected_states:   filters["states"]        = selected_states
if city_input.strip():        filters["city"]          = city_input.strip()
if employer_input.strip():    filters["employer_name"] = employer_input.strip()
if job_title_input.strip():   filters["job_title"]     = job_title_input.strip()
if selected_levels:   filters["wage_levels"]   = selected_levels
if wage_min > 0:      filters["wage_min"]      = wage_min
if wage_max > 0:      filters["wage_max"]      = wage_max

where_sql, params = build_where_clause(filters)

# ── Company count (for pagination) ───────────────────────────────────────────
@st.cache_data(ttl=300)
def get_company_count(where_sql: str, params: tuple) -> int:
    sql = f"SELECT COUNT(DISTINCT employer_name) FROM lca_records {where_sql}"
    conn = get_connection()
    n = conn.execute(sql, params).fetchone()[0]
    conn.close()
    return n

company_count = get_company_count(where_sql, tuple(params))

# ── Pagination ────────────────────────────────────────────────────────────────
PAGE_SIZE = 25
total_pages = max(1, -(-company_count // PAGE_SIZE))

if "page" not in st.session_state:
    st.session_state.page = 1
st.session_state.page = max(1, min(st.session_state.page, total_pages))

offset = (st.session_state.page - 1) * PAGE_SIZE

# ── Aggregation query (paginated at DB level) ─────────────────────────────────
@st.cache_data(ttl=300)
def load_companies(where_sql: str, params: tuple, limit: int, offset: int) -> pd.DataFrame:
    sql = f"""
        SELECT
            employer_name                                    AS "Company",
            COUNT(*)                                         AS "Total LCAs",
            COUNT(DISTINCT job_title)                        AS "Unique Roles",
            COUNT(DISTINCT worksite_state)                   AS "States",
            ROUND(MIN(annual_wage_from)::numeric, 0)         AS "Min Salary",
            ROUND(AVG(annual_wage_from)::numeric, 0)         AS "Avg Salary",
            ROUND(MAX(annual_wage_from)::numeric, 0)         AS "Max Salary",
            STRING_AGG(DISTINCT pw_wage_level, ', ')         AS "Wage Levels",
            STRING_AGG(DISTINCT CAST(fiscal_year AS TEXT), ', ') AS "Years"
        FROM lca_records
        {where_sql}
        GROUP BY employer_name
        ORDER BY COUNT(*) DESC
        LIMIT %s OFFSET %s
    """
    p = tuple(params) + (limit, offset)
    return query_df(sql, p)

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

# ── Main table ────────────────────────────────────────────────────────────────
st.subheader(f"Companies ({company_count:,} results)")

if company_count == 0:
    st.info("No results. Adjust the sidebar filters.")
else:
    df = load_companies(where_sql, tuple(params), PAGE_SIZE, offset)

    # Format salary columns
    for col in ["Min Salary", "Avg Salary", "Max Salary"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")

    selection = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="main_table",
    )

    # ── Pagination controls ───────────────────────────────────────────────────
    col_prev, col_page, col_info, col_next = st.columns([0.3, 0.4, 2.5, 0.3])
    with col_prev:
        if st.button("←", disabled=st.session_state.page <= 1, key="prev"):
            st.session_state.page -= 1
            st.rerun()
    with col_page:
        new_page = st.number_input(
            "Page", min_value=1, max_value=total_pages,
            value=st.session_state.page,
            label_visibility="collapsed", key="page_input",
        )
        if new_page != st.session_state.page:
            st.session_state.page = new_page
            st.rerun()
    with col_info:
        st.markdown(
            f"<p style='margin:0;padding-top:6px;font-size:0.85rem;color:gray;'>"
            f"Page {st.session_state.page} of {total_pages:,} ({company_count:,} companies)</p>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("→", disabled=st.session_state.page >= total_pages, key="next"):
            st.session_state.page += 1
            st.rerun()

    # ── Company drill-down ────────────────────────────────────────────────────
    selected_company = None
    if selection and selection.selection and selection.selection.rows:
        idx = selection.selection.rows[0]
        if idx < len(df):
            selected_company = df.iloc[idx]["Company"]

    if selected_company:
        with st.container(border=True):
            st.markdown(f"### {selected_company}")

            search_url = "https://www.google.com/search?q=" + urllib.parse.quote(selected_company + " careers")
            st.markdown(f"[Search Careers]({search_url})")

            df_detail = load_company_detail(selected_company, where_sql, tuple(params))
            st.write(f"**{len(df_detail):,} records** (capped at 500)")
            st.dataframe(df_detail, use_container_width=True, hide_index=True)

    # ── Export ────────────────────────────────────────────────────────────────
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    st.download_button(
        "📥 Export This Page (.xlsx)",
        data=buf.getvalue(),
        file_name="h1b_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ── Attribution ───────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Data from the [U.S. Department of Labor — OFLC](https://flag.dol.gov/programs/lca). "
    "Not affiliated with or endorsed by the DOL."
)
