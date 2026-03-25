# H1BEE — Claude Code Project Guide

## What is this?
H1BEE is a consumer-facing H-1B job board for international students. It combines:
- **Verified H-1B LCA sponsorship data** (590k+ DOL records) with
- **Live job listings** scraped from ATS platforms (Greenhouse, Lever, Ashby, Workday, iCIMS, JazzHR, SmartRecruiters)

Users can browse all jobs and filter by H-1B sponsors, location, salary, platform.

---

## Stack
- **Frontend**: React + Vite + Tailwind CSS (`frontend/`)
- **Backend**: FastAPI + psycopg2 (`backend/`)
- **Database**: Supabase PostgreSQL (Pro tier)
- **Deployment**: Vercel (frontend) + Railway (backend)
- **Repo**: https://github.com/dontsoome/h1Bee

---

## Local Development
```bash
# Backend (port 8001)
cd h1b-explorer/backend
uvicorn main:app --port 8001 --reload

# Frontend (port 5173, proxies /api/* to 8001)
cd h1b-explorer/frontend
npm run dev
```

## Environment
- `.env` lives at `h1b-explorer/.env` (one level above `backend/`)
- `backend/db.py` loads it via `Path(__file__).parent.parent / ".env"`
- Frontend uses `VITE_API_URL` env var (empty string locally, Railway URL in production)
- Vite proxy: `/api/*` → `http://localhost:8001` (vite.config.js)
- **axios baseURL must be `''` (empty string) locally** — never `http://localhost:8001` or CORS breaks

## Deployment
- **Railway**: root directory = `h1b-explorer/backend`, uses `railway.toml`, env vars set in dashboard
- **Vercel**: root directory = `h1b-explorer/frontend`, env var `VITE_API_URL` = Railway backend URL
- Both auto-deploy on push to `main`

---

## Database Key Tables
- `lca_records` — 590k+ DOL H-1B LCA disclosure records
- `job_listings` — scraped job postings (400k+ rows)
- `company_ats` — maps employer names/slugs to ATS platforms and URLs
- `lca_employer_stats` — **materialized view** pre-aggregating LCA stats per employer (lca_count, avg_wage_from, avg_wage_to, top_wage_level)
- `job_listings_enriched` — **materialized view** pre-joining job_listings + lca_employer_stats (main query target for /api/jobs)

## Critical DB Notes
- Always query `job_listings_enriched` MV, never live-join `job_listings` + `lca_employer_stats`
- After bulk scrapes, run: `REFRESH MATERIALIZED VIEW CONCURRENTLY job_listings_enriched`
- psycopg2: literal `%` in SQL strings must be `%%` or psycopg2 treats it as a parameter placeholder
- `company_ats` primary key is `employer_name` only
- Supabase connection pooler limit ~20-25 concurrent connections on Pro

---

## Data Pipeline
1. `match_ats.py` — matches H1B LCA companies to ATS platforms → writes to `company_ats`
2. `load_all_ats.py` — bulk loads all ATS slugs from `data/*.csv.csv` → `company_ats`
3. `scrape_all.py` — scrapes job listings from `company_ats` → `job_listings`
   - `--platform greenhouse` — single platform
   - `--workers 20` — recommended (single process, stable)
   - `--all` — re-scrape everything
4. Refresh MV after scrape

## Scraping Notes
- Greenhouse/Lever/Ashby are safe up to 30 workers (public APIs)
- Don't run multiple terminals simultaneously — connection pool overflows
- Single process at 20 workers is the sweet spot
- `upsert_job_listings` deduplicates by URL before insert

---

## API Routes
- `GET /api/jobs` — paginated job listings from `job_listings_enriched`
  - params: `search`, `states` (CSV), `city`, `ats_platform` (CSV), `min_wage`, `max_wage`, `wage_level` (CSV), `h1b_only` (bool)
  - Uses approximate count (`pg_class.reltuples`) when no filters, exact count when filtered
- `GET /api/lca/companies` — aggregated LCA company stats
- `GET /api/lca/records` — paginated raw LCA records
- `GET /api/filters/options` — distinct filter values

## Key Bug Fixes (don't revert)
- `case_status` in lca.py must be plain string default, NOT `Query(default="Certified")`
- US-only filter uses `%%remote%%` not `%remote%` (psycopg2 escaping)
- REMOTE state filter uses `location ILIKE '%remote%'` not state code matching

---

## Frontend Structure
- `App.jsx` — navbar with search, tab switcher (Jobs / LCA Explorer)
- `pages/Jobs.jsx` — job board with filter state management
- `pages/Explorer.jsx` — LCA data explorer
- `components/FilterPanel.jsx` — left sidebar filters (H-1B, Location, Salary, Platform)
- `components/JobCard.jsx` — job card with LCA badges, favorites
- `components/CompanyLogo.jsx` — Clearbit logo with initials fallback
- `components/Sidebar.jsx` — LCA explorer filters

## Design Principles
- Light theme throughout (bg-gray-50, white cards, gray-900 text)
- Purple as primary accent color
- No dark theme
- Tailwind only, no custom CSS files

---

## Known Issues / TODO
- Company logos not loading for slug-based employer names (e.g. "acumen" vs "Acumen Inc")
- Workday coverage limited (~4k companies vs ~2,800 active estimated)
- No job posted_at date captured yet (ATS APIs have it for Greenhouse/Lever/Ashby/JazzHR/SmartRecruiters)
- Daily scrape not automated yet (needs Railway cron)
- MV refresh not automated after scrape
