"""
pipeline.py

Responsibility: fetch + score + save leads ONLY.
Demo generation is intentionally excluded — demos are built on-demand per lead.
"""

import src.fetcher as _fetcher_mod
from src.fetcher import fetch_leads
from src.scorer import score_leads
from src.storage import slugify, save_leads, save_leads_json


def run_pipeline(industry: str, location: str) -> list[dict]:
    """
    1. Fetch leads from Apify (Google Maps)
    2. Score leads (1–10)
    3. Add URL slugs
    4. Save to CSV + latest.json (including raw-vs-filtered stats)
    Returns scored lead list.
    """
    print(f"\n[Pipeline] Starting: '{industry}' in '{location}'")

    leads = fetch_leads(industry, location)
    # Capture filter stats set by the fetcher (raw count before location filter)
    filter_stats = dict(_fetcher_mod._last_fetch_stats)

    if not leads:
        print("[Pipeline] No leads returned.")
        return []

    print(f"[Pipeline] After fetch+filter: {len(leads)} leads")

    leads = score_leads(leads)
    print(f"[Pipeline] After scoring: {len(leads)} leads")

    for lead in leads:
        lead["slug"] = slugify(lead["name"])

    csv_path  = save_leads(leads, industry, location)
    json_path = save_leads_json(leads, industry, location, filter_stats=filter_stats)
    print(f"[Pipeline] Saved {len(leads)} leads → {csv_path}")
    print(f"[Pipeline] Latest JSON → {json_path}")
    print(f"[Pipeline] Filter stats: {filter_stats}")
    print("[Pipeline] Done. Demos are generated on-demand per lead.\n")
    return leads
