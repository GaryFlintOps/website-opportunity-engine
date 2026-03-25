def filter_leads(leads: list[dict]) -> list[dict]:
    """
    Remove leads that don't meet minimum quality thresholds.
    Filters: rating < 4.2, reviews_count < 20, name contains 'closed'.
    """
    result = []
    for lead in leads:
        rating = lead.get("rating") or 0
        reviews_count = lead.get("reviews_count") or 0
        name = (lead.get("name") or "").lower()

        if rating < 4.2:
            continue
        if reviews_count < 20:
            continue
        if "closed" in name:
            continue

        result.append(lead)

    return result


def score_lead(lead: dict) -> int:
    """
    Score a lead 0–100 based on website opportunity signals.
    Higher score = stronger sales opportunity.

    Weights (total = 100):
      +40  no website          — primary sales hook
      +25  no WhatsApp         — direct-chat gap
      +15  low rating (< 4.2)  — credibility gap  [note: filtered leads have >= 4.2,
                                                    but kept here for ad-hoc use]
      +10  reviews < 50        — low visibility
      +10  photos < 5          — visual gap
    """
    score = 0

    # No website → strongest signal
    if not lead.get("website"):
        score += 40

    # No WhatsApp → direct-chat channel missing
    if not lead.get("has_whatsapp"):
        score += 25

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
