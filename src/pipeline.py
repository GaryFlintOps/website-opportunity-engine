"""
pipeline.py

Responsibility: fetch + score + save leads ONLY.
Demo generation is intentionally excluded — demos are built on-demand per lead.
"""

from src.fetcher import fetch_leads
from src.scorer import score_leads
from src.storage import slugify, save_leads, save_leads_json


def run_pipeline(industry: str, location: str) -> list[dict]:
    """
    1. Fetch leads from Apify (Google Maps)
    2. Score leads (1–10)
    3. Add URL slugs
    4. Save to CSV + latest.json
    Returns scored lead list.
    """
    print(f"\n[Pipeline] Starting: '{industry}' in '{location}'")

    leads = fetch_leads(industry, location)
    if not leads:
        print("[Pipeline] No leads returned.")
        return []

    leads = score_leads(leads)

    for lead in leads:
        lead["slug"] = slugify(lead["name"])

    csv_path  = save_leads(leads, industry, location)
    json_path = save_leads_json(leads, industry, location)
    print(f"[Pipeline] Saved {len(leads)} leads → {csv_path}")
    print(f"[Pipeline] Latest JSON → {json_path}")
    print("[Pipeline] Done. Demos are generated on-demand per lead.\n")
    return leads
