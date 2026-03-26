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
    Two-stage lead engine:

    Stage A — Qualification  (fetcher.py)
      • Multi-query Apify call (5 search variants, single API request)
      • Deduplicate by place_id / name+address
      • Relevance filter (reject hospitals, farms, wrong categories)
      • Rank by relevance score

    Stage B — Opportunity scoring  (scorer.py)
      • Score 0–100 on website/WA/review gaps
      • Sort by opportunity score descending

    Final: slugify → save CSV + latest.json → return
    """
    print(f"\n[Pipeline] ══ START ══ '{industry}' in '{location}'")

    # ── Stage A: Qualify (fetch + dedup + filter + relevance rank) ─────────
    leads = fetch_leads(industry, location)          # logs its own [Search] steps
    filter_stats = dict(_fetcher_mod._last_fetch_stats)

    print(f"[Pipeline] Qualified leads:   {len(leads)}")

    if not leads:
        print("[Pipeline] ✗ Fetcher returned no leads — aborting.")
        return []

    # ── Stage B: Opportunity score ─────────────────────────────────────────
    leads_before = len(leads)
    leads = score_leads(leads)
    print(f"[Pipeline] After opp-score:   {len(leads)}  (in: {leads_before})")

    if not leads:
        print("[Pipeline] ✗ Scorer returned empty list — check scorer.py.")
        return []

    # ── Slugify ────────────────────────────────────────────────────────────
    for lead in leads:
        lead["slug"] = slugify(lead["name"])

    # ── Save ───────────────────────────────────────────────────────────────
    from src.config import OUTPUT_DIR
    print(f"[Pipeline] Saving to:         {OUTPUT_DIR}")
    csv_path  = save_leads(leads, industry, location)
    json_path = save_leads_json(leads, industry, location, filter_stats=filter_stats)
    print(f"[Pipeline] Save complete:     {len(leads)} leads → {csv_path}")
    print(f"[Pipeline] Latest JSON:       {json_path}")
    print(f"[Pipeline] ══ DONE ══ {len(leads)} leads ready for display\n")
    return leads
