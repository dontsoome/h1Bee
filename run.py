"""Single entry point: install deps, ingest data, launch Streamlit."""

import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))
SRC = os.path.join(ROOT, "src")
DATA = os.path.join(ROOT, "data")
DB = os.path.join(ROOT, "h1b.db")


def install_deps():
    print("-- Installing dependencies --")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "-r",
         os.path.join(ROOT, "requirements.txt")]
    )


def needs_ingest():
    """Return True if there are xlsx files newer than the DB, or no DB exists."""
    import glob
    xlsx_files = glob.glob(os.path.join(DATA, "*.xlsx"))
    if not xlsx_files:
        return False  # nothing to ingest
    if not os.path.exists(DB):
        return True
    db_mtime = os.path.getmtime(DB)
    return any(os.path.getmtime(f) > db_mtime for f in xlsx_files)


def run_ingest():
    print("\n-- Ingesting data --")
    subprocess.check_call([sys.executable, os.path.join(SRC, "ingest.py")])


def launch_app():
    print("\n-- Launching H1BEE --")
    subprocess.call(
        [sys.executable, "-m", "streamlit", "run",
         os.path.join(SRC, "app.py"),
         "--server.headless", "true"]
    )


def run_career_lookup():
    """Run career URL lookup if ANTHROPIC_API_KEY is set and there are unlookedup employers."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return
    print("\n-- Checking career URL lookups --")
    subprocess.check_call([sys.executable, os.path.join(SRC, "careers.py")])


def main():
    install_deps()
    if needs_ingest():
        run_ingest()
    elif not os.path.exists(DB):
        print(f"\nNo .xlsx files in {DATA}/")
        print("Download LCA data from https://www.dol.gov/agencies/eta/foreign-labor/performance")
        print("Place .xlsx files in the data/ folder, then re-run this script.")
        sys.exit(1)
    else:
        print("\n-- Database up to date, skipping ingest --")
    run_career_lookup()
    launch_app()


if __name__ == "__main__":
    main()
