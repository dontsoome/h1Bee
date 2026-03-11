"""Ingest DOL OFLC LCA .xlsx files into Supabase (PostgreSQL)."""

from __future__ import annotations
import os
import re
import sys
import glob
import pandas as pd
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
from db import create_tables, insert_records

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
BATCH_SIZE = 5000

# Map DOL column name variations to our schema columns.
# Keys are our column names, values are lists of possible DOL header names.
COLUMN_MAP = {
    "case_number": ["CASE_NUMBER"],
    "case_status": ["CASE_STATUS"],
    "received_date": ["RECEIVED_DATE"],
    "decision_date": ["DECISION_DATE"],
    "visa_class": ["VISA_CLASS"],
    "employer_name": ["EMPLOYER_NAME"],
    "trade_name_dba": ["TRADE_NAME_DBA"],
    "employer_city": ["EMPLOYER_CITY"],
    "employer_state": ["EMPLOYER_STATE"],
    "naics_code": ["NAICS_CODE"],
    "job_title": ["JOB_TITLE"],
    "soc_code": ["SOC_CODE"],
    "soc_title": ["SOC_TITLE"],
    "full_time_position": ["FULL_TIME_POSITION"],
    "begin_date": ["BEGIN_DATE"],
    "end_date": ["END_DATE"],
    "total_worker_positions": ["TOTAL_WORKER_POSITIONS", "TOTAL_WORKERS"],
    "worksite_city": ["WORKSITE_CITY"],
    "worksite_county": ["WORKSITE_COUNTY"],
    "worksite_state": ["WORKSITE_STATE"],
    "wage_from": ["WAGE_RATE_OF_PAY_FROM"],
    "wage_to": ["WAGE_RATE_OF_PAY_TO"],
    "wage_unit": ["WAGE_UNIT_OF_PAY"],
    "prevailing_wage": ["PREVAILING_WAGE"],
    "pw_unit": ["PW_UNIT_OF_PAY"],
    "pw_wage_level": ["PW_WAGE_LEVEL"],
    "h1b_dependent": ["H_1B_DEPENDENT", "H-1B_DEPENDENT"],
    "willful_violator": ["WILLFUL_VIOLATOR"],
}

WAGE_MULTIPLIERS = {
    "Year": 1,
    "Month": 12,
    "Bi-Weekly": 26,
    "Week": 52,
    "Hour": 2080,
}


def normalize_wage(value, unit):
    """Convert a wage value to annual based on unit."""
    if value is None or pd.isna(value):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    multiplier = WAGE_MULTIPLIERS.get(unit, 1)
    return round(value * multiplier, 2)


def guess_fiscal_year(filename: str) -> int | None:
    """Extract fiscal year from filename like 'LCA_Disclosure_Data_FY2023_Q4.xlsx'."""
    match = re.search(r"(?:FY|fy)?\s*(\d{4})", filename)
    if match:
        return int(match.group(1))
    return None


def resolve_column(df_columns: list[str], candidates: list[str]) -> str | None:
    """Find the first matching column from candidates in the DataFrame columns."""
    upper_cols = {c.upper().strip(): c for c in df_columns}
    for candidate in candidates:
        if candidate.upper() in upper_cols:
            return upper_cols[candidate.upper()]
    return None


def process_file(filepath: str):
    """Read an xlsx file and yield batches of record dicts."""
    filename = os.path.basename(filepath)
    fiscal_year = guess_fiscal_year(filename)
    print(f"  Reading {filename} (FY={fiscal_year})...")

    df = pd.read_excel(filepath, engine="openpyxl")
    print(f"  Loaded {len(df)} rows, {len(df.columns)} columns")

    # Build column mapping for this file
    col_remap = {}
    for our_col, candidates in COLUMN_MAP.items():
        source_col = resolve_column(df.columns.tolist(), candidates)
        if source_col:
            col_remap[source_col] = our_col

    df = df.rename(columns=col_remap)

    # Filter to H-1B only
    if "visa_class" in df.columns:
        df = df[df["visa_class"].astype(str).str.upper().str.contains("H-1B", na=False)]
        print(f"  {len(df)} H-1B records after filtering")

    # Normalize employer names to uppercase
    if "employer_name" in df.columns:
        df["employer_name"] = df["employer_name"].astype(str).str.upper().str.strip()

    # Normalize job titles to uppercase
    if "job_title" in df.columns:
        df["job_title"] = df["job_title"].astype(str).str.upper().str.strip()

    # Normalize worksite fields
    for col in ["worksite_city", "worksite_state"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.upper().str.strip()

    # Compute annual wages
    df["annual_wage_from"] = df.apply(
        lambda row: normalize_wage(
            row.get("wage_from"), row.get("wage_unit")
        ), axis=1
    )
    df["annual_wage_to"] = df.apply(
        lambda row: normalize_wage(
            row.get("wage_to"), row.get("wage_unit")
        ), axis=1
    )

    df["fiscal_year"] = fiscal_year
    df["source_file"] = filename

    # Convert date columns to strings
    for date_col in ["received_date", "decision_date", "begin_date", "end_date"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")

    # Yield batches
    all_cols = list(COLUMN_MAP.keys()) + ["annual_wage_from", "annual_wage_to", "fiscal_year", "source_file"]
    records = []
    for _, row in df.iterrows():
        record = {}
        for col in all_cols:
            val = row.get(col)
            if pd.isna(val) if isinstance(val, float) else val is None:
                record[col] = None
            else:
                record[col] = val
        records.append(record)
        if len(records) >= BATCH_SIZE:
            yield records
            records = []
    if records:
        yield records


def main():
    print("Initializing database...")
    create_tables()

    xlsx_files = glob.glob(os.path.join(DATA_DIR, "*.xlsx"))
    if not xlsx_files:
        print(f"No .xlsx files found in {DATA_DIR}")
        print("Download LCA disclosure data from https://www.dol.gov/agencies/eta/foreign-labor/performance")
        sys.exit(1)

    total_inserted = 0
    for filepath in sorted(xlsx_files):
        print(f"\nProcessing: {filepath}")
        for batch in process_file(filepath):
            insert_records(batch)
            total_inserted += len(batch)
            print(f"  Inserted batch ({len(batch)} records, total: {total_inserted})")

    print(f"\nDone! Total records ingested: {total_inserted}")


if __name__ == "__main__":
    main()
