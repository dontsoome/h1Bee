"""H1BEE — H-1B LCA Data Explorer (Streamlit UI)."""

import streamlit as st
import pandas as pd
import os
import sys
import urllib.parse
from datetime import datetime
from io import BytesIO

sys.path.insert(0, os.path.dirname(__file__))

from db import get_connection, query_df, get_distinct_values, DB_PATH
from filters import build_where_clause
from heuristics import score_company, get_affiliation_label

st.set_page_config(page_title="H1BEE — H-1B Explorer", layout="wide")
st.title("H1BEE — H-1B LCA Data Explorer")

# Check if database exists
if not os.path.exists(DB_PATH):
    st.error(
        "Database not found. Run `python src/ingest.py` first to load data."
    )
    st.stop()

# ── Ensure tables exist with current schema ──────────────────────────────────
conn = get_connection()
conn.execute("""
    CREATE TABLE IF NOT EXISTS saved_companies (
        employer_name TEXT PRIMARY KEY,
        status TEXT DEFAULT 'Interested',
        role TEXT DEFAULT '',
        saved_at TEXT
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS company_tags (
        employer_name TEXT PRIMARY KEY,
        chinese_affiliated INTEGER DEFAULT 0
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS company_cn_scores (
        employer_name TEXT PRIMARY KEY,
        cn_score INTEGER DEFAULT 0,
        cn_label TEXT DEFAULT ''
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS job_applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL,
        job_title TEXT NOT NULL DEFAULT '',
        job_urls TEXT NOT NULL DEFAULT '',
        stage TEXT NOT NULL DEFAULT 'Interested',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    )
""")
conn.commit()

# Migrate: add columns if they don't exist (for existing DBs)
for col_sql in [
    "ALTER TABLE saved_companies ADD COLUMN status TEXT DEFAULT 'Interested'",
    "ALTER TABLE saved_companies ADD COLUMN role TEXT DEFAULT ''",
]:
    try:
        conn.execute(col_sql)
        conn.commit()
    except Exception:
        pass

# ── Pre-compute CN affiliation scores (one-time, cached in DB) ───────────────
cached_count = conn.execute("SELECT COUNT(*) FROM company_cn_scores").fetchone()[0]
total_employers = conn.execute("SELECT COUNT(DISTINCT employer_name) FROM lca_records").fetchone()[0]

if cached_count < total_employers:
    # Rebuild cache
    rows = conn.execute("""
        SELECT employer_name, MIN(trade_name_dba), MIN(employer_city)
        FROM lca_records GROUP BY employer_name
    """).fetchall()
    batch = []
    for r in rows:
        s = score_company(r[0], r[1], r[2])
        label = get_affiliation_label(s)
        batch.append((r[0], s, label))
    conn.executemany(
        "INSERT OR REPLACE INTO company_cn_scores (employer_name, cn_score, cn_label) VALUES (?, ?, ?)",
        batch,
    )
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

# ── Load manual tags + cached CN scores into maps ────────────────────────────
conn_maps = get_connection()
tag_rows = conn_maps.execute("SELECT employer_name, chinese_affiliated FROM company_tags").fetchall()
manual_tags = {r[0]: r[1] for r in tag_rows}
cn_rows = conn_maps.execute("SELECT employer_name, cn_label FROM company_cn_scores").fetchall()
cn_label_map = {r[0]: r[1] for r in cn_rows}
conn_maps.close()

# ── Sidebar Filters ──────────────────────────────────────────────────────────

st.sidebar.header("Filters")

# Case status (default: Certified)
all_statuses = get_distinct_values("case_status")
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

# Chinese-affiliated filter
chinese_filter_options = ["Likely", "Maybe", "Manually tagged"]
selected_chinese_filter = st.sidebar.multiselect("Chinese/Taiwanese Affiliated", chinese_filter_options)

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

# ── Add CN Affiliated column from cached scores + manual overrides ───────────
if not df_agg.empty:
    def _resolve_cn(company):
        manual = manual_tags.get(company, 0)
        if manual == 1:
            return "Manually tagged"
        if manual == -1:
            return ""
        return cn_label_map.get(company, "")

    df_agg["CN Affiliated"] = df_agg["Company"].apply(_resolve_cn)

    # Apply Chinese-affiliation filter
    if selected_chinese_filter:
        df_agg = df_agg[df_agg["CN Affiliated"].isin(selected_chinese_filter)]


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


# ── Helper: export dataframe to xlsx bytes ───────────────────────────────────

def to_xlsx_bytes(df):
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf.getvalue()


# ── Status constants ─────────────────────────────────────────────────────────

STATUS_ORDER = ["Interested", "To Apply", "Applied", "Interviewing", "Offer", "Rejected"]

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_explore, tab_saved, tab_tracker = st.tabs(["🔍 Explore", "⭐ Saved Companies", "📋 Job Tracker"])

# ── Explore Tab ──────────────────────────────────────────────────────────────

with tab_explore:
    st.subheader(f"Companies ({len(df_agg):,} results)")

    if df_agg.empty:
        st.info("No results match your filters. Try adjusting the sidebar filters.")
    else:
        # ── Build display dataframe ──────────────────────────────────
        df_display = df_agg.copy()
        for col in ["Min Salary", "Median Salary", "Max Salary"]:
            df_display[col] = df_display[col].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")

        # Load saved statuses
        conn_status = get_connection()
        saved_status_rows = conn_status.execute(
            "SELECT employer_name, status FROM saved_companies"
        ).fetchall()
        conn_status.close()
        saved_status_map = {r[0]: r[1] for r in saved_status_rows}

        # Add Status column, move CN Affiliated to front
        df_display.insert(0, "Status", df_display["Company"].map(saved_status_map).fillna("—"))
        if "CN Affiliated" in df_display.columns:
            cn_col = df_display.pop("CN Affiliated")
            df_display.insert(2, "CN Affiliated", cn_col)

        # ── Pagination ───────────────────────────────────────────────
        PAGE_SIZE = 25
        company_list = df_agg["Company"].tolist()
        total_companies = len(company_list)
        total_pages = max(1, -(-total_companies // PAGE_SIZE))

        if "explore_page" not in st.session_state:
            st.session_state.explore_page = 1
        st.session_state.explore_page = max(1, min(st.session_state.explore_page, total_pages))

        start_idx = (st.session_state.explore_page - 1) * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, total_companies)

        page_slice = df_display.iloc[start_idx:end_idx].reset_index(drop=True)

        # ── Interactive table with row selection ─────────────────────
        selection = st.dataframe(
            page_slice,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="explore_table",
        )

        # Determine which row was selected
        selected_company = None
        if selection and selection.selection and selection.selection.rows:
            selected_row_idx = selection.selection.rows[0]
            if selected_row_idx < len(page_slice):
                selected_company = page_slice.iloc[selected_row_idx]["Company"]

        # ── Inline detail panel ──────────────────────────────────────
        if selected_company:
            with st.container(border=True):
                st.markdown(f"### {selected_company}")

                col_link, col_action = st.columns([3, 1])
                with col_link:
                    render_career_link(selected_company)
                with col_action:
                    conn_check = get_connection()
                    is_saved = conn_check.execute(
                        "SELECT 1 FROM saved_companies WHERE employer_name = ?", (selected_company,)
                    ).fetchone() is not None
                    conn_check.close()

                    if is_saved:
                        if st.button("✓ Saved", key=f"unsave_explore_{selected_company}", type="secondary"):
                            conn_op = get_connection()
                            conn_op.execute("DELETE FROM saved_companies WHERE employer_name = ?", (selected_company,))
                            conn_op.commit()
                            conn_op.close()
                            st.rerun()
                    else:
                        if st.button("⭐ Save", key=f"save_explore_{selected_company}"):
                            conn_op = get_connection()
                            conn_op.execute(
                                "INSERT OR IGNORE INTO saved_companies (employer_name, status, role, saved_at) VALUES (?, 'Interested', '', ?)",
                                (selected_company, datetime.now().isoformat()),
                            )
                            conn_op.commit()
                            conn_op.close()
                            st.rerun()

                # Chinese-affiliation manual tag
                conn_tag = get_connection()
                current_tag = conn_tag.execute(
                    "SELECT chinese_affiliated FROM company_tags WHERE employer_name = ?",
                    (selected_company,)
                ).fetchone()
                conn_tag.close()
                current_tag_val = current_tag[0] if current_tag else 0

                tag_options = {"Auto-detect": 0, "Yes": 1, "No": -1}
                current_label = next(k for k, v in tag_options.items() if v == current_tag_val)
                new_tag_label = st.radio(
                    "Chinese/Taiwanese affiliated?",
                    list(tag_options.keys()),
                    index=list(tag_options.keys()).index(current_label),
                    key=f"cn_tag_{selected_company}",
                    horizontal=True,
                )
                new_tag_val = tag_options[new_tag_label]
                if new_tag_val != current_tag_val:
                    conn_tag = get_connection()
                    conn_tag.execute(
                        "INSERT OR REPLACE INTO company_tags (employer_name, chinese_affiliated) VALUES (?, ?)",
                        (selected_company, new_tag_val),
                    )
                    conn_tag.commit()
                    conn_tag.close()
                    st.rerun()

                render_company_detail(selected_company, where_sql, params)

        # ── Pagination controls ──────────────────────────────────────
        col_prev, col_page, col_info, col_next = st.columns([0.3, 0.4, 2.5, 0.3])
        with col_prev:
            if st.button("←", disabled=st.session_state.explore_page <= 1, key="explore_prev"):
                st.session_state.explore_page -= 1
                st.rerun()
        with col_page:
            new_page = st.number_input(
                "Page", min_value=1, max_value=total_pages,
                value=st.session_state.explore_page,
                label_visibility="collapsed", key="explore_page_input",
            )
            if new_page != st.session_state.explore_page:
                st.session_state.explore_page = new_page
                st.rerun()
        with col_info:
            st.markdown(
                f"<p style='margin:0; padding-top:6px; font-size:0.85rem; color:gray;'>"
                f"of {total_pages:,} pages ({total_companies:,} companies)</p>",
                unsafe_allow_html=True,
            )
        with col_next:
            if st.button("→", disabled=st.session_state.explore_page >= total_pages, key="explore_next"):
                st.session_state.explore_page += 1
                st.rerun()

        # ── Export Results ────────────────────────────────────────────
        st.download_button(
            label="📥 Export Results (.xlsx)",
            data=to_xlsx_bytes(df_display),
            file_name="h1b_explore_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ── Saved Companies Tab ──────────────────────────────────────────────────────

with tab_saved:
    st.subheader("Saved Companies")

    conn_saved = get_connection()
    saved_rows = conn_saved.execute(
        "SELECT employer_name, status, role, saved_at FROM saved_companies ORDER BY saved_at DESC"
    ).fetchall()
    conn_saved.close()

    if not saved_rows:
        st.info("No saved companies yet. Use the ⭐ Save button in the Explore tab to bookmark companies.")
    else:
        st.caption(f"{len(saved_rows)} saved company/companies")

        # ── Open Career Pages button (To Apply companies) ────────────
        to_apply_companies = [r[0] for r in saved_rows if r[1] == "To Apply"]
        to_apply_urls = []
        for c in to_apply_companies:
            url = career_url_map.get(c)
            if url:
                to_apply_urls.append((c, url))
            else:
                search_url = "https://www.google.com/search?q=" + urllib.parse.quote(c + " careers")
                to_apply_urls.append((c, search_url))

        if to_apply_urls:
            if st.button(f"🌐 Open Career Pages ({len(to_apply_urls)} To Apply)"):
                js_opens = "\n".join(f'window.open("{url}", "_blank");' for _, url in to_apply_urls)
                st.components.v1.html(
                    f"<script>{js_opens}</script>",
                    height=0,
                )
                st.markdown("**Opened career pages:**")
                for name, url in to_apply_urls:
                    st.markdown(f"- [{name}]({url})")

        # ── Export Saved Companies ───────────────────────────────────
        export_rows = []
        for row in saved_rows:
            company_name = row[0]
            status = row[1] or "Interested"
            role = row[2] or ""
            career_url = career_url_map.get(company_name, "")
            if not career_url:
                career_url = "https://www.google.com/search?q=" + urllib.parse.quote(company_name + " careers")

            stats = query_df(
                "SELECT COUNT(*) AS total, ROUND(MIN(annual_wage_from),0) AS min_sal, "
                "ROUND(AVG(annual_wage_from),0) AS avg_sal, ROUND(MAX(annual_wage_from),0) AS max_sal "
                "FROM lca_records WHERE employer_name = ?",
                (company_name,),
            )
            total_lcas = int(stats["total"].iloc[0]) if not stats.empty else 0
            min_sal = stats["min_sal"].iloc[0] if not stats.empty else None
            avg_sal = stats["avg_sal"].iloc[0] if not stats.empty else None
            max_sal = stats["max_sal"].iloc[0] if not stats.empty else None

            export_rows.append({
                "Company": company_name,
                "Status": status,
                "Role": role,
                "Career URL": career_url,
                "Total LCAs": total_lcas,
                "Min Salary": min_sal,
                "Avg Salary": avg_sal,
                "Max Salary": max_sal,
            })

        df_export = pd.DataFrame(export_rows)
        st.download_button(
            label="📥 Export Saved Companies (.xlsx)",
            data=to_xlsx_bytes(df_export),
            file_name="h1b_saved_companies.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # ── Group by status ──────────────────────────────────────────
        saved_by_status = {}
        for row in saved_rows:
            status = row[1] or "Interested"
            saved_by_status.setdefault(status, []).append(row)

        for status in STATUS_ORDER:
            rows_in_status = saved_by_status.get(status, [])
            if not rows_in_status:
                continue

            st.markdown(f"#### {status} ({len(rows_in_status)})")

            for row in rows_in_status:
                company_name = row[0]
                current_status = row[1] or "Interested"
                current_role = row[2] or ""

                with st.expander(company_name):
                    col_status, col_role = st.columns(2)

                    with col_status:
                        new_status = st.selectbox(
                            "Status",
                            STATUS_ORDER,
                            index=STATUS_ORDER.index(current_status) if current_status in STATUS_ORDER else 0,
                            key=f"status_{company_name}",
                        )

                    with col_role:
                        soc_titles = query_df(
                            "SELECT DISTINCT soc_title FROM lca_records WHERE employer_name = ? AND soc_title IS NOT NULL ORDER BY soc_title",
                            (company_name,),
                        )["soc_title"].tolist()
                        role_options = [""] + soc_titles
                        role_idx = role_options.index(current_role) if current_role in role_options else 0
                        new_role = st.selectbox(
                            "Role",
                            role_options,
                            index=role_idx,
                            key=f"role_{company_name}",
                        )

                    if new_status != current_status or new_role != current_role:
                        conn_up = get_connection()
                        conn_up.execute(
                            "UPDATE saved_companies SET status = ?, role = ? WHERE employer_name = ?",
                            (new_status, new_role, company_name),
                        )
                        conn_up.commit()
                        conn_up.close()
                        st.rerun()

                    render_career_link(company_name)

                    if st.button("Unsave", key=f"unsave_saved_{company_name}"):
                        conn_op = get_connection()
                        conn_op.execute("DELETE FROM saved_companies WHERE employer_name = ?", (company_name,))
                        conn_op.commit()
                        conn_op.close()
                        st.rerun()

                    render_company_detail(company_name, "", [])

# ── Job Tracker Tab ──────────────────────────────────────────────────────────

JOB_STAGES = ["Interested", "To Apply", "Applied", "Interviewing", "Offer", "Rejected"]

with tab_tracker:
    st.subheader("Job Tracker")

    # ── Add Job Form ─────────────────────────────────────────────────
    with st.expander("➕ Add a Job", expanded=False):
        with st.form("add_job_form", clear_on_submit=True):
            col_co, col_title = st.columns(2)
            with col_co:
                # Populate with saved companies + allow typing custom
                conn_co = get_connection()
                saved_cos = [r[0] for r in conn_co.execute(
                    "SELECT employer_name FROM saved_companies ORDER BY employer_name"
                ).fetchall()]
                conn_co.close()
                new_company = st.selectbox(
                    "Company",
                    options=[""] + saved_cos,
                    index=0,
                    key="add_job_company",
                )
            with col_title:
                new_title = st.text_input("Job Title", key="add_job_title")

            new_urls = st.text_area(
                "Job Link(s)",
                placeholder="Paste one URL per line",
                height=68,
                key="add_job_urls",
            )

            col_stage, col_notes = st.columns(2)
            with col_stage:
                new_stage = st.selectbox("Stage", JOB_STAGES, key="add_job_stage")
            with col_notes:
                new_notes = st.text_input("Notes", key="add_job_notes")

            submitted = st.form_submit_button("Add Job")
            if submitted:
                if not new_company:
                    st.error("Company is required.")
                else:
                    now = datetime.now().isoformat()
                    conn_add = get_connection()
                    conn_add.execute(
                        "INSERT INTO job_applications (company, job_title, job_urls, stage, notes, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (new_company, new_title, new_urls.strip(), new_stage, new_notes, now, now),
                    )
                    conn_add.commit()
                    conn_add.close()
                    st.rerun()

    # ── Load existing jobs ───────────────────────────────────────────
    df_jobs = query_df(
        "SELECT id, company, job_title, job_urls, stage, notes, created_at, updated_at "
        "FROM job_applications ORDER BY updated_at DESC"
    )

    if df_jobs.empty:
        st.info("No jobs tracked yet. Use the form above to add your first application.")
    else:
        # ── Summary counts ───────────────────────────────────────────
        stage_counts = df_jobs["stage"].value_counts()
        summary_parts = []
        for s in JOB_STAGES:
            c = stage_counts.get(s, 0)
            if c > 0:
                summary_parts.append(f"**{s}**: {c}")
        st.caption(" · ".join(summary_parts))

        # ── Filter by stage ──────────────────────────────────────────
        filter_stage = st.multiselect(
            "Filter by stage", JOB_STAGES, default=[], key="tracker_filter_stage"
        )
        df_show = df_jobs if not filter_stage else df_jobs[df_jobs["stage"].isin(filter_stage)]

        # ── Editable spreadsheet ─────────────────────────────────────
        df_edit = df_show[["id", "company", "job_title", "job_urls", "stage", "notes"]].copy()
        df_edit.columns = ["ID", "Company", "Job Title", "Job Links", "Stage", "Notes"]

        edited = st.data_editor(
            df_edit,
            use_container_width=True,
            hide_index=True,
            disabled=["ID"],
            num_rows="fixed",
            column_config={
                "ID": st.column_config.NumberColumn("ID", width="small"),
                "Company": st.column_config.TextColumn("Company", width="medium"),
                "Job Title": st.column_config.TextColumn("Job Title", width="medium"),
                "Job Links": st.column_config.TextColumn("Job Links", width="large"),
                "Stage": st.column_config.SelectboxColumn(
                    "Stage", options=JOB_STAGES, width="small", required=True,
                ),
                "Notes": st.column_config.TextColumn("Notes", width="large"),
            },
            key="job_tracker_editor",
        )

        # ── Save edits back to DB ────────────────────────────────────
        # Compare edited df to original to find changes
        if not edited.equals(df_edit):
            now = datetime.now().isoformat()
            conn_edit = get_connection()
            for idx in range(len(edited)):
                row_new = edited.iloc[idx]
                row_old = df_edit.iloc[idx]
                if not row_new.equals(row_old):
                    conn_edit.execute(
                        "UPDATE job_applications SET company=?, job_title=?, job_urls=?, stage=?, notes=?, updated_at=? WHERE id=?",
                        (row_new["Company"], row_new["Job Title"], row_new["Job Links"],
                         row_new["Stage"], row_new["Notes"], now, int(row_new["ID"])),
                    )
            conn_edit.commit()
            conn_edit.close()
            st.rerun()

        # ── Delete job ───────────────────────────────────────────────
        with st.expander("🗑️ Delete a job"):
            job_labels = [
                f"#{r['ID']} — {r['Company']} — {r['Job Title']}" for _, r in df_edit.iterrows()
            ]
            delete_choice = st.selectbox("Select job to delete", [""] + job_labels, key="delete_job_select")
            if delete_choice and st.button("Delete", key="delete_job_btn", type="primary"):
                job_id = int(delete_choice.split("#")[1].split(" —")[0])
                conn_del = get_connection()
                conn_del.execute("DELETE FROM job_applications WHERE id = ?", (job_id,))
                conn_del.commit()
                conn_del.close()
                st.rerun()

        # ── Export ───────────────────────────────────────────────────
        df_export_jobs = df_show[["company", "job_title", "job_urls", "stage", "notes", "created_at"]].copy()
        df_export_jobs.columns = ["Company", "Job Title", "Job Links", "Stage", "Notes", "Added"]
        st.download_button(
            label="📥 Export Job Tracker (.xlsx)",
            data=to_xlsx_bytes(df_export_jobs),
            file_name="h1b_job_tracker.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ── Data Source Attribution ──────────────────────────────────────────────────
st.divider()
st.caption(
    "Data sourced from the [U.S. Department of Labor — Office of Foreign Labor Certification (OFLC)](https://flag.dol.gov/programs/lca) "
    "LCA disclosure files. This tool is not affiliated with or endorsed by the DOL."
)
