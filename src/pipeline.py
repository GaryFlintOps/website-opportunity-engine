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
    print(f"\n[Pipeline] ── START ── '{industry}' in '{location}'")

    # ── Step 1: Fetch ──────────────────────────────────────────────────────
    leads = fetch_leads(industry, location)
    filter_stats = dict(_fetcher_mod._last_fetch_stats)

    raw_count = filter_stats.get("raw", len(leads))
    print(f"[Pipeline] Raw fetched:    {raw_count}")
    print(f"[Pipeline] After dedup:    {len(leads)}")

    if not leads:
        print("[Pipeline] ✗ No leads returned from fetcher — aborting.")
        return []

    # ── Step 2: Score (includes internal quality filter) ──────────────────
    leads_before_scoring = len(leads)
    leads = score_leads(leads)
    print(f"[Pipeline] After scoring:  {len(leads)}  (filtered from {leads_before_scoring})")

    if not leads:
        print("[Pipeline] ✗ All leads were removed by scorer filter — check scorer.py thresholds.")
        return []

    # ── Step 3: Slugify ───────────────────────────────────────────────────
    for lead in leads:
        lead["slug"] = slugify(lead["name"])

    # ── Step 4: Save ──────────────────────────────────────────────────────
    from src.config import OUTPUT_DIR
    print(f"[Pipeline] Saving to:      {OUTPUT_DIR}")
    csv_path  = save_leads(leads, industry, location)
    json_path = save_leads_json(leads, industry, location, filter_stats=filter_stats)
    print(f"[Pipeline] Save complete:  {len(leads)} leads → {csv_path}")
    print(f"[Pipeline] Latest JSON:    {json_path}")
    print(f"[Pipeline] ── DONE ── {len(leads)} leads ready for display\n")
    return leads
