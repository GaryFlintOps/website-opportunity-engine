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
    Score a lead based on website opportunity signals.
    Higher score = stronger opportunity.

    Scoring:
      +5  no website
      +2  rating >= 4.3
      +2  reviews_count >= 50
      +1  photos < 5
    """
    score = 0

    # No website → strongest signal
    if not lead.get("website"):
        score += 5

    # High rating → credible, worth building for
    rating = lead.get("rating") or 0
    if rating >= 4.3:
        score += 2

    # Many reviews → established business, more to gain
    reviews_count = lead.get("reviews_count") or 0
    if reviews_count >= 50:
        score += 2

    # Few photos → visual gap we can fill
    photos = lead.get("photos") or []
    if len(photos) < 5:
        score += 1

    return score


def score_leads(leads: list[dict]) -> list[dict]:
    """Filter, score, and sort leads by score descending."""
    leads = filter_leads(leads)
    for lead in leads:
        lead["score"] = score_lead(lead)
    return sorted(leads, key=lambda x: x["score"], reverse=True)
