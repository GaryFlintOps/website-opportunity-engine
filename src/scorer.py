def filter_leads(leads: list[dict]) -> list[dict]:
    """
    Minimal quality filter — only remove clearly junk entries.

    Previous thresholds (rating < 4.2, reviews_count < 20) were too aggressive:
    - Apify often returns rating=0.0 / reviews_count=0 when fields are missing,
      causing ALL leads to be dropped before scoring even runs.
    - The scoring function already rewards low-rating and low-review leads with
      bonus points, so removing them here was counterproductive.

    Kept: drop "permanently closed" businesses by name.
    """
    result = []
    for lead in leads:
        name = (lead.get("name") or "").lower()
        if "closed" in name:
            print(f"[Scorer] Filtered out (closed): {lead.get('name')}")
            continue
        result.append(lead)

    print(f"[Scorer] filter_leads: {len(leads)} in → {len(result)} out")
    return result


def score_lead(lead: dict) -> int:
    """
    Score a lead 0–100 based on website opportunity signals.
    Higher score = stronger sales opportunity.

    Weights (total = 100):
      +40  no website                        — primary sales hook
      +25  WhatsApp gap (graded, see below)  — direct-chat opportunity
      +15  low rating (< 4.2)                — credibility gap
      +10  reviews < 50                      — low visibility
      +10  photos < 5                        — visual gap

    WhatsApp gap scoring (graded by source, max = 25):
      +25  has_whatsapp=False                — no WA presence at all (biggest opportunity)
      +20  whatsapp_source="maps"            — WA number exists but invisible on site
      +12  whatsapp_source="inferred"        — mobile on site but no direct WA link
      + 0  whatsapp_source="link"            — fully set up, nothing to sell here
    """
    score = 0

    # No website → strongest signal
    if not lead.get("website"):
        score += 40

    # WhatsApp gap — graded by source quality
    wa_src = lead.get("whatsapp_source")
    if not lead.get("has_whatsapp"):
        score += 25   # no WA at all — biggest opportunity
    elif wa_src == "maps":
        score += 20   # mobile exists but not promoted on site
    elif wa_src == "inferred":
        score += 12   # mobile on site but no clickable WA link
    # wa_src == "link" → +0 (already optimised)

    # Low rating → credibility gap
    rating = lead.get("rating") or 5.0
    if rating < 4.2:
        score += 15

    # Few reviews → low visibility
    reviews_count = lead.get("reviews_count") or 0
    if reviews_count < 50:
        score += 10

    # Few photos → visual gap
    photos = lead.get("photos") or []
    if len(photos) < 5:
        score += 10

    return min(score, 100)


def score_leads(leads: list[dict]) -> list[dict]:
    """Filter, score, and sort leads by score descending."""
    leads = filter_leads(leads)
    for lead in leads:
        lead["score"] = score_lead(lead)
    return sorted(leads, key=lambda x: x["score"], reverse=True)
