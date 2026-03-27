"""
guardrails.py

Pure filtering and validation — ZERO AI generation.
No fallback fake data. If data is weak → reject.

Exposes:
  validate_image(image: dict) -> bool
  compress_review(text: str) -> str | None
  validate_business(business: dict) -> bool
  final_guardrail_check(data: dict) -> None   (raises ValueError on failure)
"""

# ── IMAGE VALIDATION ──────────────────────────────────────────────────────────

_MIN_IMAGE_WIDTH      = 800
_REJECTED_TAGS        = {"logo", "text-heavy", "text_heavy", "duplicate"}
_ACCEPTED_CATEGORIES  = {"bike", "interior", "workshop", "cycling"}


def validate_image(image: dict) -> bool:
    """
    Validate a single image dict.

    Rejects if:
      - width < 800
      - tagged as logo, text-heavy, or duplicate
      - not a real business image AND not in an approved category

    Returns True if the image passes all quality checks.
    """
    if not image or not isinstance(image, dict):
        return False

    # Width check — reject if explicitly below minimum
    width = image.get("width")
    if width is not None:
        try:
            if int(width) < _MIN_IMAGE_WIDTH:
                return False
        except (TypeError, ValueError):
            pass

    # Tag/flag rejection
    raw_tags = image.get("tags") or image.get("flags") or []
    tags = {str(t).lower().strip() for t in raw_tags}

    # Also check the "type" field for common rejection keywords
    image_type = str(image.get("type", "")).lower()
    if "logo" in image_type or "logo" in tags:
        return False
    if "text-heavy" in tags or "text_heavy" in tags:
        return False
    if "duplicate" in tags:
        return False

    # Source / category acceptance
    # If the image is explicitly flagged as a real business photo — accept it
    is_real = image.get("is_real_business_image")
    if is_real is True:
        return True

    # If a category is specified and it's in the approved set — accept it
    category = str(image.get("category", "")).lower().strip()
    if category in _ACCEPTED_CATEGORIES:
        return True

    # No explicit rejection and no category flag: assume real business image
    # (raw Apify photo URLs arrive without metadata flags — trust them by default)
    if is_real is None:
        return True

    return False


# ── REVIEW COMPRESSION ───────────────────────────────────────────────────────

# Ordered: first keyword match per review wins
_COMPRESSION_MAP: list[tuple[list[str], str]] = [
    (["knowledgeable", "know", "expertise", "expert"],       "Knowledgeable staff"),
    (["quick", "fast", "turnaround", "prompt", "efficient"], "Quick turnaround"),
    (["friendly", "warm", "welcoming", "great service",
      "excellent service", "good service"],                  "Friendly service"),
    (["selection", "range", "variety", "stock", "choice"],   "Great selection"),
    (["fit", "fitting", "bike fit", "sizing"],               "Excellent bike fit"),
]

_ALLOWED_OUTPUTS = {
    "Knowledgeable staff",
    "Quick turnaround",
    "Friendly service",
    "Great selection",
    "Excellent bike fit",
}


def compress_review(text: str) -> str | None:
    """
    Extract a short, human phrase (2–5 words) from a review.

    Rules:
      - DO NOT rewrite meaning
      - DO NOT generate new sentiment
      - Only returns phrases from the _ALLOWED_OUTPUTS set
      - Returns None if no strong match is found
    """
    if not text or not isinstance(text, str):
        return None

    text_lower = text.lower().strip()

    for keywords, phrase in _COMPRESSION_MAP:
        for kw in keywords:
            if kw in text_lower:
                return phrase   # always from _ALLOWED_OUTPUTS

    return None


# ── BUSINESS VALIDATION ───────────────────────────────────────────────────────

_MIN_RATING            = 4.0
_MIN_VALID_IMAGES      = 5
_MIN_COMPRESSED_REVIEWS = 2


def validate_business(business: dict) -> bool:
    """
    Validate a business dict for demo-worthiness.

    Must have:
      - name
      - rating >= 4.0
      - at least 5 valid images after filtering
      - at least 2 compressible reviews

    Returns True on pass, False on fail (logs reason).
    """
    if not business or not isinstance(business, dict):
        print("[Guardrail] SKIP: empty or invalid business data")
        return False

    # ── Name ──────────────────────────────────────────────────────────────────
    name = (business.get("name") or "").strip()
    if not name:
        print("[Guardrail] SKIP: missing business name")
        return False

    # ── Rating ────────────────────────────────────────────────────────────────
    try:
        rating = float(business.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0

    if rating < _MIN_RATING:
        print(f"[Guardrail] SKIP '{name}': rating {rating:.1f} < {_MIN_RATING}")
        return False

    # ── Images ────────────────────────────────────────────────────────────────
    photos = business.get("photos") or []

    if photos and isinstance(photos[0], dict):
        # Full metadata dicts — apply full validation
        valid_images = sum(1 for img in photos if validate_image(img))
    else:
        # Plain URL strings — no metadata to reject on; count all
        valid_images = len([p for p in photos if p and isinstance(p, str)])

    if valid_images < _MIN_VALID_IMAGES:
        print(
            f"[Guardrail] SKIP '{name}': "
            f"{valid_images} valid image(s) — need {_MIN_VALID_IMAGES}"
        )
        return False

    # ── Reviews ───────────────────────────────────────────────────────────────
    reviews = business.get("reviews") or []
    compressed = []
    for r in reviews:
        raw_text = r.get("text", "") if isinstance(r, dict) else str(r)
        phrase = compress_review(raw_text)
        if phrase:
            compressed.append(phrase)

    if len(compressed) < _MIN_COMPRESSED_REVIEWS:
        print(
            f"[Guardrail] SKIP '{name}': "
            f"{len(compressed)} compressed review(s) — need {_MIN_COMPRESSED_REVIEWS}"
        )
        return False

    return True


# ── FINAL GUARDRAIL CHECK ─────────────────────────────────────────────────────

def final_guardrail_check(data: dict) -> None:
    """
    Run a final safety check before site generation.

    Raises ValueError('GUARDRAIL FAILURE: …') if any condition is violated:
      - missing required real fields (name, rating, location)
      - any review phrase longer than 8 words
      - any image dict that fails validate_image()
      - AI-generated image used as storefront / interior
    """
    if not data:
        raise ValueError("GUARDRAIL FAILURE: unsafe to generate demo — no data provided")

    # ── Required real fields ──────────────────────────────────────────────────
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("GUARDRAIL FAILURE: unsafe to generate demo — missing 'name'")

    if not data.get("rating"):
        raise ValueError(
            f"GUARDRAIL FAILURE: unsafe to generate demo — missing 'rating' for '{name}'"
        )

    if not data.get("city") and not data.get("address"):
        raise ValueError(
            f"GUARDRAIL FAILURE: unsafe to generate demo — missing location for '{name}'"
        )

    # ── Review phrase length (compressed only — must be ≤ 8 words) ───────────
    for phrase in data.get("review_phrases", []):
        words = str(phrase).split()
        if len(words) > 8:
            raise ValueError(
                f"GUARDRAIL FAILURE: unsafe to generate demo — "
                f"review phrase too long ({len(words)} words): '{phrase}'"
            )

    # ── Image validation ──────────────────────────────────────────────────────
    gallery = data.get("gallery_images", [])
    for item in gallery:
        if isinstance(item, dict) and not validate_image(item):
            raise ValueError(
                f"GUARDRAIL FAILURE: unsafe to generate demo — "
                f"invalid image in gallery for '{name}'"
            )
        # URL-only check: reject explicit AI storefront/interior markers
        if isinstance(item, str):
            lower = item.lower()
            if "ai_generated_storefront" in lower or "ai_generated_interior" in lower:
                raise ValueError(
                    f"GUARDRAIL FAILURE: unsafe to generate demo — "
                    f"AI-generated storefront/interior image detected for '{name}'"
                )

    # Passed all checks
    return
