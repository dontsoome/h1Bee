# H1BEE — H-1B LCA Data Explorer

Local-first H-1B LCA data explorer. Ingests DOL OFLC disclosure `.xlsx` files into SQLite and provides a Streamlit UI with filtering, company aggregation, and drill-down.

## Quick Start

1. Download LCA disclosure `.xlsx` files from the [DOL OFLC Performance page](https://www.dol.gov/agencies/eta/foreign-labor/performance) and place them in the `data/` folder.

2. Run:
```bash
python run.py
```

That's it. `run.py` installs dependencies, ingests any new `.xlsx` files into `h1b.db`, and launches the Streamlit app.

Re-ingest happens automatically whenever new/updated `.xlsx` files are detected in `data/`.

## Features

- **Sidebar filters**: case status, fiscal year, state, city, employer, job title, SOC code, wage level, wage range
- **Company aggregation table**: total LCAs, unique roles, salary min/median/max, wage levels, worksite count
- **Drill-down**: select a company to view individual LCA records with full detail
