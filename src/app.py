"""H1BEE — H-1B LCA Data Explorer (Streamlit UI)."""

import streamlit as st
import pandas as pd
import os
import sys
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from db import get_connection, query_df, get_distinct_values, DB_PATH
from filters import build_where_clause

st.set_page_config(page_title="H1BEE — H-1B Explorer", layout="wide")
st.title("H1BEE — H-1B LCA Data Explorer")

# Check if database exists
if not os.path.exists(DB_PATH):
    st.error(
        "Database not found. Run `python src/ingest.py` first to load data."
    )
    st.stop()

# Ensure saved_companies table exists
conn = get_connection()
conn.execute("""
    CREATE TABLE IF NOT EXISTS saved_companies (
        employer_name TEXT PRIMARY KEY,
        saved_at TEXT
    )
""")
conn.commit()

# Check if there are records
count = conn.execute("SELECT COUNT(*) FROM lca_records").fetchone()[0]
conn.close()
if count == 0:
    st.warning("Database is empty. Run `python src/ingest.py` to load data.")
    st.stop()

st.caption(f"{count:,} total LCA records in database")

# ── Load career URL map ─────────────────────────────────────────────────────
career_url_map = {}
try:
    conn_career = get_connection()
    career_rows = conn_career.execute(
        "SELECT employer_name, career_url FROM career_urls WHERE career_url IS NOT NULL AND career_url != ''"
    ).fetchall()
    conn_career.close()
    career_url_map = {r[0]: r[1] for r in career_rows}
except Exception:
    pass  # table may not exist yet

# ── Sidebar Filters ──────────────────────────────────────────────────────────

st.sidebar.header("Filters")

# Case status (default: Certified)
all_statuses = get_distinct_values("case_status")
default_statuses = ["Certified"] if "Certified" in [s.title() for s in all_statuses] else []
# Match case from DB
default_statuses = [s for s in all_statuses if s.upper() == "CERTIFIED"] or all_statuses[:1]
selected_statuses = st.sidebar.multiselect("Case Status", all_statuses, default=default_statuses)

# Fiscal year
all_years = get_distinct_values("fiscal_year")
selected_years = st.sidebar.multiselect("Fiscal Year", all_years)

# State
all_states = get_distinct_values("worksite_state")
selected_states = st.sidebar.multiselect("Worksite State", all_states)

# City
city_input = st.sidebar.text_input("Worksite City (contains)")

# Employer name
employer_input = st.sidebar.text_input("Employer Name (contains)")

# Career page filter
career_page_options = ["Direct career page", "Google search only"]
selected_career_filter = st.sidebar.multiselect("Career Page", career_page_options)

# Job title
job_title_input = st.sidebar.text_input("Job Title (comma-separated, e.g. software engineer, data analyst)")

# SOC title
all_soc_titles = get_distinct_values("soc_title")
selected_soc_titles = st.sidebar.multiselect("SOC Title", all_soc_titles)

# Wage level
all_levels = get_distinct_values("pw_wage_level")
selected_levels = st.sidebar.multiselect("Wage Level", all_levels)

# Wage range
st.sidebar.subheader("Annual Wage Range")
wage_min = st.sidebar.number_input("Min Annual Wage", min_value=0, value=0, step=10000)
wage_max = st.sidebar.number_input("Max Annual Wage", min_value=0, value=0, step=10000)

# Build filters dict
filters = {}
if selected_statuses:
    filters["case_statuses"] = selected_statuses
if selected_years:
    filters["fiscal_years"] = selected_years
if selected_states:
    filters["states"] = selected_states
if city_input.strip():
    filters["city"] = city_input.strip()
if employer_input.strip():
    filters["employer_name"] = employer_input.strip()
if job_title_input.strip():
    filters["job_title"] = job_title_input.strip()
if selected_soc_titles:
    filters["soc_titles"] = selected_soc_titles
if selected_levels:
    filters["wage_levels"] = selected_levels
if wage_min > 0:
    filters["wage_min"] = wage_min
if wage_max > 0:
    filters["wage_max"] = wage_max

where_sql, params = build_where_clause(filters)

# ── Company Aggregation Query ────────────────────────────────────────────────

agg_sql = f"""
SELECT
    employer_name AS "Company",
    COUNT(*) AS "Total LCAs",
    COUNT(DISTINCT job_title) AS "Unique Roles",
    COUNT(DISTINCT worksite_state) AS "Worksite States",
    ROUND(MIN(annual_wage_from), 0) AS "Min Salary",
    ROUND(AVG(annual_wage_from), 0) AS "Median Salary",
    ROUND(MAX(annual_wage_from), 0) AS "Max Salary",
    GROUP_CONCAT(DISTINCT pw_wage_level) AS "Wage Levels",
    GROUP_CONCAT(DISTINCT fiscal_year) AS "Years"
FROM lca_records
{where_sql}
GROUP BY employer_name
ORDER BY COUNT(*) DESC
"""

df_agg = query_df(agg_sql, tuple(params))

# Apply career page filter after aggregation
if selected_career_filter and len(selected_career_filter) == 1:
    if "Direct career page" in selected_career_filter:
        df_agg = df_agg[df_agg["Company"].isin(career_url_map.keys())]
    elif "Google search only" in selected_career_filter:
        df_agg = df_agg[~df_agg["Company"].isin(career_url_map.keys())]


# ── Helper: render career link ───────────────────────────────────────────────

def render_career_link(company):
    career_url = career_url_map.get(company)
    if career_url:
        st.markdown(f"[🔗 Careers Page]({career_url})")
    else:
        search_url = "https://www.google.com/search?q=" + urllib.parse.quote(company + " careers")
        st.markdown(f"[🔍 Search Careers]({search_url})")


# ── Helper: render company detail ────────────────────────────────────────────

def render_company_detail(company, detail_where_sql, detail_base_params):
    detail_where = detail_where_sql
    detail_params = list(detail_base_params)

    if detail_where:
        detail_where += " AND employer_name = ?"
    else:
        detail_where = "WHERE employer_name = ?"
    detail_params.append(company)

    detail_sql = f"""
    SELECT
        case_number AS "Case Number",
        case_status AS "Status",
        job_title AS "Job Title",
        soc_code AS "SOC Code",
        soc_title AS "SOC Title",
        annual_wage_from AS "Annual Wage From",
        annual_wage_to AS "Annual Wage To",
        wage_unit AS "Wage Unit",
        pw_wage_level AS "Wage Level",
        worksite_city AS "City",
        worksite_state AS "State",
        begin_date AS "Begin Date",
        decision_date AS "Decision Date",
        fiscal_year AS "FY",
        full_time_position AS "Full Time"
    FROM lca_records
    {detail_where}
    ORDER BY decision_date DESC
    """

    df_detail = query_df(detail_sql, tuple(detail_params))

    st.write(f"**{len(df_detail):,} records**")

    for col in ["Annual Wage From", "Annual Wage To"]:
        if col in df_detail.columns:
            df_detail[col] = df_detail[col].apply(
                lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A"
            )

    st.dataframe(df_detail, use_container_width=True, hide_index=True)


# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_explore, tab_saved = st.tabs(["🔍 Explore", "⭐ Saved Companies"])

# ── Explore Tab ──────────────────────────────────────────────────────────────

with tab_explore:
    st.subheader(f"Companies ({len(df_agg):,} results)")

    if df_agg.empty:
        st.info("No results match your filters. Try adjusting the sidebar filters.")
    else:
        # Format salary columns for display
        df_display = df_agg.copy()
        for col in ["Min Salary", "Median Salary", "Max Salary"]:
            df_display[col] = df_display[col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")

        # Display company table
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # ── Paginated Company Rows ────────────────────────────────────────────
        PAGE_SIZE = 25
        company_list = df_agg["Company"].tolist()
        total_lca_list = df_agg["Total LCAs"].tolist()
        total_companies = len(company_list)
        total_pages = max(1, -(-total_companies // PAGE_SIZE))  # ceiling division

        if "explore_page" not in st.session_state:
            st.session_state.explore_page = 1

        # Clamp page to valid range
        st.session_state.explore_page = max(1, min(st.session_state.explore_page, total_pages))

        def render_pagination(prefix):
            col_prev, col_info, col_spacer, col_next = st.columns([0.6, 1.2, 3, 0.6])
            with col_prev:
                if st.button("← Previous", disabled=st.session_state.explore_page <= 1, key=f"{prefix}_prev"):
                    st.session_state.explore_page -= 1
                    st.rerun()
            with col_info:
                st.markdown(
                    f"<p style='margin:0; padding-top:6px; font-size:0.85rem; color:gray;'>"
                    f"Page {st.session_state.explore_page} of {total_pages} ({total_companies:,} companies)</p>",
                    unsafe_allow_html=True,
                )
            with col_next:
                if st.button("Next →", disabled=st.session_state.explore_page >= total_pages, key=f"{prefix}_next"):
                    st.session_state.explore_page += 1
                    st.rerun()

        # Top pagination
        render_pagination("top")

        start_idx = (st.session_state.explore_page - 1) * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, total_companies)

        for i in range(start_idx, end_idx):
            company = company_list[i]
            total = total_lca_list[i]
            with st.expander(f"{company} — {total} LCAs"):
                # Career link (hybrid: direct or Google search)
                render_career_link(company)

                # Save / Unsave button
                conn_check = get_connection()
                is_saved = conn_check.execute(
                    "SELECT 1 FROM saved_companies WHERE employer_name = ?", (company,)
                ).fetchone() is not None
                conn_check.close()

                if is_saved:
                    if st.button("✓ Saved", key=f"unsave_{i}_{company}", type="secondary"):
                        conn_op = get_connection()
                        conn_op.execute("DELETE FROM saved_companies WHERE employer_name = ?", (company,))
                        conn_op.commit()
                        conn_op.close()
                        st.rerun()
                else:
                    if st.button("⭐ Save", key=f"save_{i}_{company}"):
                        conn_op = get_connection()
                        conn_op.execute(
                            "INSERT OR IGNORE INTO saved_companies (employer_name, saved_at) VALUES (?, ?)",
                            (company, datetime.now().isoformat()),
                        )
                        conn_op.commit()
                        conn_op.close()
                        st.rerun()

                # Detail records
                render_company_detail(company, where_sql, params)

        # Bottom pagination
        render_pagination("bottom")

# ── Saved Companies Tab ──────────────────────────────────────────────────────

with tab_saved:
    st.subheader("Saved Companies")

    conn_saved = get_connection()
    saved_rows = conn_saved.execute(
        "SELECT employer_name, saved_at FROM saved_companies ORDER BY saved_at DESC"
    ).fetchall()
    conn_saved.close()

    if not saved_rows:
        st.info("No saved companies yet. Use the ⭐ Save button in the Explore tab to bookmark companies.")
    else:
        st.caption(f"{len(saved_rows)} saved company/companies")

        for row in saved_rows:
            company_name = row[0]
            with st.expander(company_name):
                # Career link
                render_career_link(company_name)

                # Unsave button
                if st.button("Unsave", key=f"unsave_saved_{company_name}"):
                    conn_op = get_connection()
                    conn_op.execute("DELETE FROM saved_companies WHERE employer_name = ?", (company_name,))
                    conn_op.commit()
                    conn_op.close()
                    st.rerun()

                # Show LCA records (no filters applied — show all records for saved company)
                render_company_detail(company_name, "", [])
