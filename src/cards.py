"""
cards.py — Utility for rendering lead summary cards used by the dashboard.
(Thin module; most rendering is done via Jinja2 templates.)
"""

from src.storage import slugify


def prepare_leads_for_display(leads: list[dict]) -> list[dict]:
    """Add display helpers to each lead dict."""
    for lead in leads:
        if not lead.get("slug"):
            lead["slug"] = slugify(lead.get("name", "unknown"))

        lead["has_website"] = bool(lead.get("website"))
        lead["has_phone"] = bool(lead.get("phone"))

        # Thresholds tuned for 0-100 scale.
        # Hot  (>= 80): no website + no WhatsApp + at least one more gap
        # Warm (>= 50): strong single gap or two moderate ones
        # Cool (< 50):  minor gaps only — lower priority
        score = lead.get("score", 0)
        if score >= 80:
            lead["score_class"] = "score-high"
            lead["score_label"] = "Hot"
        elif score >= 50:
            lead["score_class"] = "score-mid"
            lead["score_label"] = "Warm"
        else:
            lead["score_class"] = "score-low"
            lead["score_label"] = "Cool"

    return leads


def filter_leads(
    leads: list[dict],
    min_score: int = 0,
    no_website_only: bool = False,
    max_reviews: int = 0,
) -> list[dict]:
    """Apply dashboard filters to lead list."""
    result = leads
    if min_score > 0:
        result = [l for l in result if l.get("score", 0) >= min_score]
    if no_website_only:
        result = [l for l in result if not l.get("website")]
    if max_reviews > 0:
        result = [l for l in result if (l.get("reviews_count") or 0) <= max_reviews]
    return result
