"""
pipeline.py

Responsibility: fetch + score + guardrail-filter + save leads ONLY.
Demo generation is intentionally excluded — demos are built on-demand per lead.
"""

import src.fetcher as _fetcher_mod
from src.fetcher import fetch_leads
from src.scorer import score_leads
from src.storage import slugify, save_leads, save_leads_json
from src.guardrails import validate_business, validate_image, compress_review
from src.utils.whatsapp import extract_whatsapp_data, fetch_website_html

# ── Debug flag ────────────────────────────────────────────────────────────────
# When True: bypasses all guardrail rejection and minimum thresholds.
# Always returns at least 1 lead, injecting a fallback demo object if needed.
# Flip to False to restore normal guardrail behaviour.
DEBUG_FORCE_BUILD = False

# Fallback demo object used when DEBUG_FORCE_BUILD is True and no real data exists
_FALLBACK_LEAD = {
    "name":          "Demo Bike Shop",
    "rating":        4.6,
    "reviews_count": 120,
    "category":      "Bicycle Shop",
    "city":          "Durban",
    "address":       "Durban, South Africa",
    "phone":         "",
    "website":       "",
    "google_maps_url": "",
    "slug":          "demo-bike-shop",
    "score":         80,
    "photos": [
        "https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1576435728678-68d0fbf94e91?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1571068316344-75bc76f77890?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1532298229144-0ec0c57515c7?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1604176354204-9268737828e4?w=800&h=600&fit=crop",
    ],
    "reviews": [
        {"text": "Knowledgeable staff who really understand cycling.",  "author": "James K.",  "rating": 5},
        {"text": "Quick turnaround on my service, really impressed.",   "author": "Sarah M.",  "rating": 5},
        {"text": "Friendly service every time — wouldn't go elsewhere.","author": "David T.",  "rating": 5},
    ],
    "guardrail_passed": True,
    "debug_fallback":   True,
}


def _guardrail_filter(leads: list[dict]) -> tuple[list[dict], dict]:
    """
    Stage C — Guardrail filtering.

    For each lead:
      1. Run validate_business() — skip if it fails (name / rating / image / review minimums)
      2. Filter images:     keep only valid image dicts (or all URL strings)
      3. Compress reviews:  keep only reviews that yield a phrase
      4. Enforce minimums:  skip if < 1 valid image (review check disabled — Outscraper returns no review text)

    Returns (passing_leads, stats_dict).
    """
    passed:  list[dict] = []
    skipped: list[dict] = []

    for lead in leads:
        name = lead.get("name", "<unknown>")

        # ── Step 1: Business-level check ─────────────────────────────────
        if not validate_business(lead):
            skipped.append({"name": name, "reason": "failed validate_business"})
            continue

        # ── Step 2: Image filtering ───────────────────────────────────────
        photos = lead.get("photos") or []
        if photos and isinstance(photos[0], dict):
            valid_images = [img for img in photos if validate_image(img)]
        else:
            # URL strings — no metadata to filter on; keep all
            valid_images = [p for p in photos if p and isinstance(p, str)]

        print(
            f"[Guardrail] '{name}': "
            f"{len(valid_images)}/{len(photos)} images passed"
        )

        # ── Step 3: Review compression ────────────────────────────────────
        reviews = lead.get("reviews") or []
        compressed_reviews: list[str] = []
        for r in reviews:
            raw_text = r.get("text", "") if isinstance(r, dict) else str(r)
            phrase = compress_review(raw_text)
            if phrase:
                compressed_reviews.append(phrase)

        print(
            f"[Guardrail] '{name}': "
            f"{len(compressed_reviews)}/{len(reviews)} reviews accepted"
        )

        # ── Step 4: Minimum enforcement ───────────────────────────────────
        # Thresholds match guardrails.py:
        #   images:  ≥ 1  — Outscraper maps/search-v3 returns only 1 photo per result
        #   reviews: ≥ 0  — endpoint returns review COUNT only; no review text to compress
        if len(valid_images) < 1:
            reason = f"not enough valid images ({len(valid_images)} < 1)"
            print(f"[Guardrail] SKIP '{name}': {reason}")
            skipped.append({"name": name, "reason": reason})
            continue

        # Review compression check intentionally omitted for Outscraper —
        # maps/search-v3 never returns review text, so compressed_reviews is
        # always empty and checking it would reject every business.

        # ── Step 5: Attach filtered data back onto lead ───────────────────
        lead = dict(lead)   # shallow copy — don't mutate original
        lead["photos"]              = valid_images
        lead["compressed_reviews"]  = compressed_reviews
        lead["guardrail_passed"]    = True

        passed.append(lead)

    stats = {
        "total":   len(leads),
        "passed":  len(passed),
        "skipped": len(skipped),
        "skip_reasons": skipped,
    }
    return passed, stats


def run_pipeline(industry: str, location: str) -> list[dict]:
    """
    Three-stage lead engine:

    Stage A — Qualification  (fetcher.py)
      • Multi-query Apify call (5 search variants, single API request)
      • Deduplicate by place_id / name+address
      • Relevance filter (reject hospitals, farms, wrong categories)
      • Rank by relevance score

    Stage B — Opportunity scoring  (scorer.py)
      • Score 0–100 on website/WA/review gaps
      • Sort by opportunity score descending

    Stage C — Guardrail filtering  (guardrails.py)
      • Validate business quality (name, rating, images, reviews)
      • Filter weak images and non-compressible reviews
      • Drop businesses that don't meet minimums
      • Log all skip reasons

    Final: slugify → save CSV + latest.json → return
    """
    print(f"\n[Pipeline] ══ START ══ '{industry}' in '{location}'")

    # ── Stage A: Qualify (fetch + dedup + filter + relevance rank) ─────────
    leads = fetch_leads(industry, location)          # logs its own [Search] steps
    filter_stats = dict(_fetcher_mod._last_fetch_stats)

    print(f"[Pipeline] Qualified leads:   {len(leads)}")

    if not leads:
        if DEBUG_FORCE_BUILD:
            print("[Pipeline] ⚡ Fetcher returned nothing — injecting fallback demo object")
            leads = [dict(_FALLBACK_LEAD)]
        else:
            print("[Pipeline] ✗ Fetcher returned no leads — aborting.")
            return []

    # ── Stage A.5: WhatsApp detection ─────────────────────────────────────────
    # Run before scoring so the scorer sees accurate has_whatsapp + whatsapp_source.
    # For each lead: try to fetch the website (4s timeout, silently skipped on error),
    # then classify into link / inferred / maps / none using extract_whatsapp_data().
    print(f"[Pipeline] WhatsApp detection: {len(leads)} leads …")
    _wa_counts = {"link": 0, "inferred": 0, "maps": 0, "none": 0}
    for lead in leads:
        website = lead.get("website", "")
        html    = fetch_website_html(website) if website else ""
        wa_data = extract_whatsapp_data(html=html, maps_phone=lead.get("phone"))
        lead.update(wa_data)
        # Maintain backward-compat whatsapp_confidence field (0=none,1=maps/inferred,2=link)
        src = wa_data.get("whatsapp_source")
        lead["whatsapp_confidence"] = 2 if src == "link" else (1 if src else 0)
        _wa_counts[src or "none"] += 1
    print(
        f"[Pipeline] WA detection done — "
        f"link:{_wa_counts['link']} | inferred:{_wa_counts['inferred']} | "
        f"maps:{_wa_counts['maps']} | none:{_wa_counts['none']}"
    )

    # ── Stage B: Opportunity score ─────────────────────────────────────────
    leads_before = len(leads)
    leads = score_leads(leads)
    print(f"[Pipeline] After opp-score:   {len(leads)}  (in: {leads_before})")

    if not leads:
        if DEBUG_FORCE_BUILD:
            print("[Pipeline] ⚡ Scorer returned nothing — injecting fallback demo object")
            leads = [dict(_FALLBACK_LEAD)]
        else:
            print("[Pipeline] ✗ Scorer returned empty list — check scorer.py.")
            return []

    # ── Stage C: Guardrail filtering (skipped in DEBUG_FORCE_BUILD mode) ──────
    if DEBUG_FORCE_BUILD:
        print("[Pipeline] ⚡ DEBUG_FORCE_BUILD=True — guardrails bypassed, all leads pass")
        for lead in leads:
            lead.setdefault("guardrail_passed", True)
        filter_stats["guardrail_passed"]  = len(leads)
        filter_stats["guardrail_skipped"] = 0
        filter_stats["guardrail_reasons"] = []
    else:
        leads_before_guardrail = len(leads)
        leads, guardrail_stats = _guardrail_filter(leads)

        print(
            f"[Pipeline] Guardrail results: "
            f"{guardrail_stats['passed']} passed / "
            f"{guardrail_stats['skipped']} skipped "
            f"(in: {leads_before_guardrail})"
        )
        if guardrail_stats["skip_reasons"]:
            for entry in guardrail_stats["skip_reasons"]:
                print(f"[Pipeline]   ✗ '{entry['name']}': {entry['reason']}")

        filter_stats["guardrail_passed"]  = guardrail_stats["passed"]
        filter_stats["guardrail_skipped"] = guardrail_stats["skipped"]
        filter_stats["guardrail_reasons"] = guardrail_stats["skip_reasons"]

        if not leads:
            if DEBUG_FORCE_BUILD:
                print("[Pipeline] ⚡ No leads — injecting fallback demo object")
                leads = [dict(_FALLBACK_LEAD)]
            else:
                print("[Pipeline] ✗ All leads failed guardrails — aborting.")
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
