"""
ai_content.py

Generates AI-powered website copy for local businesses using the Anthropic API.

Usage:
    from src.ai_content import generate_ai_content

    result = generate_ai_content(
        name="Full of Beans Cafe",
        category="Coffee store",
        rating=4.8,
        review_count=187,
        reviews=[{"text": "Best coffee in Paarl!", "rating": 5}],
        location="Paarl, South Africa",
    )
    # Returns:
    # {
    #   "hero_line":      "Local favourite for breakfast and great coffee",
    #   "trust_benefit":  "Fresh daily baked goods",
    #   "offers":         ["Breakfast & brunch", "Artisan coffee", ...],
    #   "promo":          "Try our breakfast special before 10am",
    # }
    # Returns None if API unavailable — caller falls back to static content.
"""

import os
import re
import json as _json


# ── Master prompt (exact spec) ────────────────────────────────────────────────

_MASTER_PROMPT = """You are generating website content for a real local business.

Your goal is to make the business owner feel:
"This was written specifically for my business."

INPUT:
- Business name: {business_name}
- Category: {category}
- Rating: {rating}/5
- Review count: {review_count}
- Top reviews:
{reviews}
- Location: {location}

RULES:
- Keep all outputs short and punchy
- No generic phrases like "welcome" or "we are passionate"
- No fluff
- Use natural, human language
- Make it sound like a real local business
- Focus on what customers care about (quality, speed, trust, results)
- Include location context naturally if possible
{rating_note}
OUTPUT FORMAT — use EXACTLY these headers, nothing else:

1. HERO LINE (max 12 words)
[your line here]

2. TRUST BENEFIT (max 6 words)
[your benefit here]

3. WHAT THEY OFFER (3–6 items, one per line, prefix each with -)
- [item]
- [item]
- [item]

4. OPTIONAL PROMO (1 line, or write None if not relevant)
[your promo line here]

Make outputs match the business category: {category}"""


# ── HTTP caller (uses requests — already a project dependency) ───────────────

def _call_claude(prompt: str) -> str | None:
    """POST to Anthropic Messages API; return assistant text or None."""
    import requests as _req

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        resp = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-haiku-4-5-20251001",   # fast + cheap
                "max_tokens": 450,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=18,
        )
        if resp.status_code == 200:
            return resp.json()["content"][0]["text"].strip()
        print(f"[AI Content] API returned {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        print(f"[AI Content] Request error: {exc}")
    return None


# ── Output parser ─────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Strip surrounding quotes, bullets, and whitespace from a line."""
    return re.sub(r'^[\s\-\*•·▸▪◦"\']+|[\s"\']+$', '', text).strip()


def _parse_output(raw: str) -> dict:
    """
    Parse the structured LLM response into a clean dict.
    Robust to minor formatting variations.
    """
    result: dict = {"hero_line": "", "trust_benefit": "", "offers": [], "promo": ""}

    lines = raw.splitlines()
    current_section = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Detect section headers  e.g. "1. HERO LINE" or "1. HERO LINE (max 12 words)"
        sec_match = re.match(r'^(\d)\.\s*(HERO|TRUST|WHAT|OPTIONAL)', stripped, re.IGNORECASE)
        if sec_match:
            current_section = int(sec_match.group(1))
            continue

        if current_section == 1 and not result["hero_line"]:
            hero = _clean(stripped)
            if hero and len(hero) > 4:
                result["hero_line"] = hero

        elif current_section == 2 and not result["trust_benefit"]:
            tb = _clean(stripped)
            if tb and len(tb) > 2:
                result["trust_benefit"] = tb

        elif current_section == 3:
            # Collect bullet items until we hit section 4
            item = _clean(stripped)
            if item and len(item) > 2 and not re.match(r'^\d+\.', stripped):
                result["offers"].append(item)
            if len(result["offers"]) >= 6:
                current_section = None  # stop collecting

        elif current_section == 4 and not result["promo"]:
            promo = _clean(stripped)
            if promo and promo.lower() not in {"none", "n/a", "-", "not applicable", "no", ""}:
                result["promo"] = promo

    return result


# ── Public entry point ────────────────────────────────────────────────────────

def generate_ai_content(
    name:         str,
    category:     str,
    rating:       float,
    review_count: int,
    reviews:      list[dict],
    location:     str,
) -> dict | None:
    """
    Generate AI-powered copy for a local business.

    Returns a dict with keys:
        hero_line, trust_benefit, offers (list), promo

    Returns None if:
    - ANTHROPIC_API_KEY is not set
    - API call fails
    - Output cannot be parsed reliably

    Callers should fall back to static lookup tables on None.
    """
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        return None

    # ── Format top reviews (max 3, max 130 chars each) ──────────────────────
    sorted_reviews = sorted(reviews, key=lambda r: -int(r.get("rating", 0)))
    review_lines = []
    for r in sorted_reviews[:3]:
        text = (r.get("text") or "").strip()[:130]
        if text:
            review_lines.append(f'  - "{text}"')
    reviews_str = "\n".join(review_lines) if review_lines else "  (no reviews available)"

    # ── Rating-aware instruction ─────────────────────────────────────────────
    try:
        score = float(rating)
    except (TypeError, ValueError):
        score = 0.0

    if score >= 4.5:
        rating_note = (
            f"IMPORTANT: This business has a {score:.1f}/5 rating "
            f"({review_count} reviews) — subtly highlight their strong reputation."
        )
    elif score > 0 and score < 4.0:
        rating_note = (
            f"IMPORTANT: Rating is {score:.1f}/5 — avoid emphasising quality; "
            f"focus on convenience, value, or unique offering instead."
        )
    else:
        rating_note = ""

    prompt = _MASTER_PROMPT.format(
        business_name = name,
        category      = category or "Local Business",
        rating        = f"{score:.1f}" if score else "N/A",
        review_count  = review_count or "Unknown",
        reviews       = reviews_str,
        location      = location or "South Africa",
        rating_note   = rating_note + "\n" if rating_note else "",
    )

    print(f"[AI Content] Generating copy for: {name}")
    raw = _call_claude(prompt)
    if not raw:
        return None

    parsed = _parse_output(raw)

    # Validate minimum viable output
    if not parsed["hero_line"]:
        print(f"[AI Content] Parse failed — no hero_line extracted. Raw: {raw[:300]}")
        return None
    if not parsed["offers"]:
        print(f"[AI Content] Parse failed — no offers extracted. Raw: {raw[:300]}")
        return None

    print(f"[AI Content] ✓ {name}: \"{parsed['hero_line']}\" | {len(parsed['offers'])} offers")
    return parsed
