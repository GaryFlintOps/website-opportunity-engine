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


def _guardrail_filter(leads: list[dict]) -> tuple[list[dict], dict]:
    """
    Stage C — Guardrail filtering.

    For each lead:
      1. Run validate_business() — skip if it fails (name / rating / image / review minimums)
      2. Filter images:     keep only valid image dicts (or all URL strings)
      3. Compress reviews:  keep only reviews that yield a phrase
      4. Enforce minimums:  skip if < 3 valid images or < 2 compressed reviews

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
        if len(valid_images) < 3:
            reason = f"not enough valid images ({len(valid_images)} < 3)"
            print(f"[Guardrail] SKIP '{name}': {reason}")
            skipped.append({"name": name, "reason": reason})
            continue

        if len(compressed_reviews) < 2:
            reason = f"reviews too weak ({len(compressed_reviews)} < 2)"
            print(f"[Guardrail] SKIP '{name}': {reason}")
            skipped.append({"name": name, "reason": reason})
            continue

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
        print("[Pipeline] ✗ Fetcher returned no leads — aborting.")
        return []

    # ── Stage B: Opportunity score ─────────────────────────────────────────
    leads_before = len(leads)
    leads = score_leads(leads)
    print(f"[Pipeline] After opp-score:   {len(leads)}  (in: {leads_before})")

    if not leads:
        print("[Pipeline] ✗ Scorer returned empty list — check scorer.py.")
        return []

    # ── Stage C: Guardrail filtering ───────────────────────────────────────
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

    # Merge guardrail stats into filter_stats for dashboard display
    filter_stats["guardrail_passed"]  = guardrail_stats["passed"]
    filter_stats["guardrail_skipped"] = guardrail_stats["skipped"]
    filter_stats["guardrail_reasons"] = guardrail_stats["skip_reasons"]

    if not leads:
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
