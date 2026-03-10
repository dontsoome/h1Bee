"""Batch career URL lookup via Claude Haiku for H1BEE employers."""

import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

sys.path.insert(0, os.path.dirname(__file__))

from db import get_connection, create_tables

BATCH_SIZE = 20


def get_unlookedup_employers() -> list[str]:
    """Return employer names from lca_records that are not yet in career_urls."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT employer_name FROM lca_records
        WHERE employer_name IS NOT NULL
        AND employer_name NOT IN (SELECT employer_name FROM career_urls)
        ORDER BY employer_name
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def lookup_batch(client, companies: list[str]) -> dict[str, str]:
    """Ask Haiku for career page URLs for a batch of companies."""
    company_list = "\n".join(f"- {c}" for c in companies)
    prompt = f"""For each company below, provide the most likely career/jobs page URL.
Consider common ATS platforms (Greenhouse, Lever, Ashby, Workday, iCIMS, SmartRecruiters, BambooHR) and direct /careers or /jobs pages.
If you are not confident about the URL for a company, use an empty string.

Companies:
{company_list}

Respond with ONLY a JSON object mapping company name (exactly as given) to career URL string. Example:
{{"ACME CORP": "https://acme.com/careers", "UNKNOWN LLC": ""}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Extract JSON from response (handle markdown code blocks)
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"  Warning: failed to parse response, skipping batch")
        return {}


def save_results(results: dict[str, str]):
    """Insert career URL results into the database."""
    if not results:
        return
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT INTO career_urls (employer_name, career_url, looked_up_at) VALUES (%s, %s, %s) ON CONFLICT (employer_name) DO UPDATE SET career_url=EXCLUDED.career_url, looked_up_at=EXCLUDED.looked_up_at",
        [(name, url, now) for name, url in results.items()],
    )
    conn.commit()
    conn.close()


def run_career_lookup():
    """Main entry point: look up career URLs for all employers missing from career_urls."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set, skipping career URL lookup.")
        return

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    create_tables()
    employers = get_unlookedup_employers()
    if not employers:
        print("All employers already have career URL lookups.")
        return

    total = len(employers)
    print(f"Looking up career URLs for {total:,} employers ({(total + BATCH_SIZE - 1) // BATCH_SIZE} batches)...")

    for i in range(0, total, BATCH_SIZE):
        batch = employers[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Batch {batch_num}: {len(batch)} companies...", end=" ", flush=True)

        results = lookup_batch(client, batch)
        save_results(results)

        found = sum(1 for v in results.values() if v)
        print(f"found {found}/{len(batch)} URLs")

    print("Career URL lookup complete.")


if __name__ == "__main__":
    run_career_lookup()
