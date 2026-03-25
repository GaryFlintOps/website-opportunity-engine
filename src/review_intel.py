"""
review_intel.py

Extracts structured insights from raw Google review text.
No external NLP dependencies — pure regex + frequency counting.

Usage:
    from src.review_intel import extract_review_intel

    result = extract_review_intel(reviews)
    # result = {
    #   "top_highlights":   ["Great coffee", "Friendly staff"],
    #   "signature_items":  ["Flat White", "Eggs Benedict"],
    #   "experience_tags":  ["Cosy atmosphere", "Great for breakfast"],
    #   "top_review_quote": "The best flat white I've had in years...",
    # }

STRICT SEPARATION:
  highlights    = category-level quality signals (coffee, food, service, staff, atmosphere)
  signature_items = specific named items (flat white, eggs benedict, croissant)
  experience_tags = experiential / vibe descriptors (hidden gem, dog friendly, cosy atmosphere)

Rules:
  - Only uses reviews with rating >= 4 for extraction
  - Highlights and experience_tags never contain the same phrase
  - Specific items in highlights are moved to signature_items
  - Blacklisted generic phrases are excluded
  - max 4 words per phrase
  - Returns empty arrays when evidence is insufficient (prefer empty over fake)
"""

import re


# ── CATEGORY-LEVEL quality nouns for highlights ───────────────────────────────
# STRICT: only broad categories here.
# Specific items (flat white, burger, etc.) must go via _ITEM_PATTERNS.

_QUALITY_NOUNS: list[tuple[str, list[str], str]] = [
    # (noun_pattern, preferred_adjectives_ordered_best_first, display_label)
    ("coffee",      ["amazing", "great", "excellent", "best", "fantastic", "perfect", "incredible"],  "coffee"),
    ("food",        ["amazing", "great", "excellent", "delicious", "incredible", "fantastic", "lovely"], "food"),
    ("service",     ["great", "excellent", "amazing", "top-notch", "spot on", "perfect", "incredible"], "service"),
    ("staff",       ["friendly", "amazing", "great", "lovely", "wonderful", "helpful", "welcoming", "inviting"], "staff"),
    ("atmosphere",  ["great", "amazing", "beautiful", "lovely", "wonderful", "vibey", "perfect"],     "atmosphere"),
    ("breakfast",   ["amazing", "great", "excellent", "best", "fantastic"],                           "breakfast"),
    ("lunch",       ["great", "amazing", "excellent", "best"],                                        "lunch"),
    ("brunch",      ["great", "amazing", "excellent", "best"],                                        "brunch"),
    ("views",       ["beautiful", "amazing", "great", "stunning", "incredible"],                      "views"),
    ("vibes",       ["great", "good", "amazing", "fantastic"],                                        "vibes"),
    ("meals",       ["amazing", "great", "delicious", "excellent", "fresh"],                          "meals"),
]

# Blacklisted highlight phrases — too generic to be meaningful
_HIGHLIGHT_BLACKLIST: frozenset[str] = frozenset({
    "good food",
    "nice food",
    "nice place",
    "good place",
    "very nice",
    "good service",
    "nice coffee",
    "good coffee",
    "good atmosphere",
    "nice atmosphere",
    "good meals",
    "good views",
})


# ── Specific food/drink/product items ─────────────────────────────────────────
# Ordered most-specific → most-generic so earlier matches win.

_ITEM_PATTERNS: list[tuple[str, str]] = [
    (r'\bflat\s+white\b',                      "Flat White"),
    (r'\bcappuccino\b',                         "Cappuccino"),
    (r'\bcortado\b',                            "Cortado"),
    (r'\bmacchiato\b',                          "Macchiato"),
    (r'\bespresso\b',                           "Espresso"),
    (r'\bcold\s+brew\b',                        "Cold Brew"),
    (r'\biced\s+latte\b',                       "Iced Latte"),
    (r'\blatte\b',                              "Latte"),
    (r'\bamericano\b',                          "Americano"),
    (r'\bpour[\s-]?over\b',                     "Pour Over"),
    (r'\bgourmet\s+milkshakes?\b',              "Gourmet Milkshakes"),
    (r'\bmilkshakes?\b',                        "Milkshakes"),
    (r'\bsmoothies?\b',                         "Smoothies"),
    (r'\bhot\s+chocolate\b',                    "Hot Chocolate"),
    (r'\beggs?\s+benedict\b',                   "Eggs Benedict"),
    (r'\bfried\s+eggs?\b',                      "Fried Eggs"),
    (r'\bscrambled\s+eggs?\b',                  "Scrambled Eggs"),
    (r'\bavocado\s+toast\b|\bavo\s+toast\b',    "Avo Toast"),
    (r'\bcroissants?\b',                        "Croissant"),
    (r'\bfrench\s+toast\b',                     "French Toast"),
    (r'\bwaffles?\b',                           "Waffles"),
    (r'\bpancakes?\b',                          "Pancakes"),
    (r'\bscones?\b',                            "Scones"),
    (r'\bmuffins?\b',                           "Muffins"),
    (r'\bbrownies?\b',                          "Brownies"),
    (r'\bcheesecake\b',                         "Cheesecake"),
    (r'\bcakes?\b',                             "Cake"),
    (r'\bpastries\b|\bpastry\b',               "Pastries"),
    (r'\bpies?\b',                              "Pie"),
    (r'\bsoups?\b',                             "Soup"),
    (r'\bsalads?\b',                            "Salad"),
    (r'\bsandwiches?\b',                        "Sandwiches"),
    (r'\btoastie\b|\btoasted\s+sandwich\b',     "Toasties"),
    (r'\bwraps?\b',                             "Wraps"),
    (r'\bburgers?\b',                           "Burgers"),
    (r'\bsteaks?\b',                            "Steak"),
    (r'\bpastas?\b',                            "Pasta"),
    (r'\bpizzas?\b',                            "Pizza"),
    (r'\bsushis?\b',                            "Sushi"),
    (r'\bbreakfast\s+special\b',               "Breakfast Special"),
    (r'\bcharcuterie\b',                        "Charcuterie"),
]


# ── Experience / vibe tags ────────────────────────────────────────────────────
# STRICT: must NOT overlap with quality highlights.
# No "great service", "friendly staff", "great atmosphere" here —
# those are handled by _QUALITY_NOUNS.

_EXPERIENCE_TAGS: list[tuple[str, str]] = [
    (r'\bfamily[\s-]?friendly\b|\bkid[\s-]?friendly\b|\bchildren.{0,15}welcom', "Family friendly"),
    (r'\bdog[\s-]?friendly\b',                                                   "Dog friendly"),
    (r'\bpet[\s-]?friendly\b',                                                   "Pet friendly"),
    (r'\bhidden gem\b',                                                          "Hidden gem"),
    (r'\boutdoor\s+(seating|dining|area|terrace)\b',                             "Outdoor seating"),
    (r'\blive\s+music\b',                                                        "Live music"),
    (r'\bbeautiful\s+(views?|scenery|setting|surroundings)\b'
     r'|\bamazing\s+(views?|scenery|setting)\b|\bstunning\s+views?\b',           "Beautiful views"),
    (r'\bgreat\s+for\s+breakfast\b|\bbreakfast\s+(spot|place|destination)\b',   "Great for breakfast"),
    (r'\bgreat\s+for\s+(lunch|brunch)\b|\b(lunch|brunch)\s+(spot|place)\b',     "Good for lunch"),
    # Cosy — describes type/feel of atmosphere, not quality
    (r'\bcosy\b|\bcozy\b',                                                       "Cosy atmosphere"),
    # Vibey/vibes — distinct enough from "Great atmosphere" quality signal
    (r'\bvibey\b|\bgreat\s+vibes?\b|\bamazing\s+vibes?\b|\bgood\s+vibes?\b',    "Great vibes"),
    (r'\bwarm\s+(welcome|service|atmosphere)\b|\bwarm\s+and\s+welcom',           "Warm welcome"),
    (r'\bperfect\s+(spot|place|setting|location)\b',                             "Perfect spot"),
    (r'\binstagram(mable)?\b|\bphoto[\s-]?worthy\b',                             "Instagram-worthy"),
    (r'\brelax(ing|ed)?\b|\bpeaceful\b|\bquiet\s+(spot|place|setting)\b',       "Relaxed vibe"),
    (r'\bscenic\b',                                                              "Scenic location"),
    (r'\bmeander\b',                                                             "On the Midlands Meander"),
]

# Meaningful nouns that make a hero quote worth using
_QUOTE_SIGNAL_NOUNS = frozenset({
    "coffee", "food", "service", "staff", "atmosphere", "view", "views",
    "meal", "meals", "breakfast", "lunch", "brunch", "experience",
    "milkshake", "milkshakes", "burger", "burgers", "cake", "pastry",
    "flat white", "cappuccino", "espresso", "menu", "place", "spot",
    "recommend", "recommended",
})

# Quotes with these phrases are too generic to surface
_QUOTE_BLACKLIST: frozenset[str] = frozenset({
    "nice place", "good place", "good food", "nice food",
    "very nice", "very good", "not bad",
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Lowercase, collapse whitespace."""
    return re.sub(r'\s+', ' ', (text or "").lower().strip())


def _format_phrase(phrase: str) -> str:
    """
    Final format for any extracted phrase:
    - Title-case the first word only
    - Strip trailing punctuation
    - Enforce max 4 words
    - Strip whitespace
    """
    phrase = phrase.strip().rstrip(".,;:!?")
    words = phrase.split()
    if len(words) > 4:
        words = words[:4]
    if not words:
        return ""
    words[0] = words[0].capitalize()
    return " ".join(words)


def _positive_texts(reviews: list) -> list[str]:
    """Normalised text from reviews with rating >= 4."""
    return [
        _norm(r.get("text", "") or "")
        for r in reviews
        if int(r.get("rating") or 0) >= 4
    ]


# ── Highlight extraction ──────────────────────────────────────────────────────

def _extract_highlights(pos_texts: list[str]) -> list[str]:
    """
    Extract category-level quality highlights from positive reviews.

    Algorithm:
    1. For each quality noun, count how many reviews mention it
    2. Find the best adjacent positive adjective
    3. Form a 2-word phrase and apply formatting + blacklist
    4. Sort by frequency, return top 5
    5. Deduplicate by noun root (no two phrases for the same noun)

    Returns max 5 highlights, each ≤ 4 words, not in blacklist.
    """
    if not pos_texts:
        return []

    combined = " ".join(pos_texts)
    scored: list[tuple[int, str]] = []
    used_noun_roots: set[str] = set()

    for noun, preferred_adjs, label in _QUALITY_NOUNS:
        root = label.split()[0]  # e.g. "coffee" from "coffee", "flat" from "flat white"
        if root in used_noun_roots:
            continue

        # How many reviews mention this noun?
        count = sum(1 for t in pos_texts if re.search(r'\b' + re.escape(noun) + r'\b', t))
        if count == 0:
            continue

        # Find the best adjective paired with this noun
        chosen_adj: str | None = None
        for adj in preferred_adjs:
            # adj … noun  (adj within 25 chars before noun)
            if re.search(r'\b' + re.escape(adj) + r'.{0,25}\b' + re.escape(noun) + r'\b', combined):
                chosen_adj = adj
                break
            # noun … adj  (adj within 25 chars after noun)
            if re.search(r'\b' + re.escape(noun) + r'.{0,25}\b' + re.escape(adj) + r'\b', combined):
                chosen_adj = adj
                break

        # Build phrase
        if chosen_adj:
            raw_phrase = f"{chosen_adj} {label}"
        elif count >= 2:
            # Mentioned multiple times, no adj found — noun alone is still a signal
            raw_phrase = label
        else:
            continue  # single mention, no adj: too weak

        phrase = _format_phrase(raw_phrase)
        if not phrase:
            continue

        # Blacklist check
        if phrase.lower() in _HIGHLIGHT_BLACKLIST:
            continue

        scored.append((count, phrase))
        used_noun_roots.add(root)

    # Sort by frequency descending, return top 5
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:5]]


# ── Signature item extraction ─────────────────────────────────────────────────

def _extract_signature_items(pos_texts: list[str]) -> list[str]:
    """
    Find specific named menu/product items mentioned in positive reviews.

    Ordered most-specific → most-generic so earlier matches win.
    Deduplicates by normalised last-word to avoid "Milkshakes" after "Gourmet Milkshakes".
    Returns max 5 items.
    """
    if not pos_texts:
        return []

    combined = " ".join(pos_texts)
    found: list[str] = []
    seen_roots: set[str] = set()

    for pattern, label in _ITEM_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            # Root = last word of label (lowercased) for near-dup detection
            root = label.lower().split()[-1]
            if root not in seen_roots:
                found.append(_format_phrase(label))
                seen_roots.add(label.lower())
                seen_roots.add(root)
        if len(found) >= 5:
            break

    return found


# ── Experience tag extraction ─────────────────────────────────────────────────

def _extract_experience_tags(pos_texts: list[str]) -> list[str]:
    """
    Match predefined experience / vibe phrases from positive reviews.
    These are STRICTLY experiential — no overlap with highlight quality nouns.
    Returns max 5 unique tags.
    """
    if not pos_texts:
        return []

    combined = " ".join(pos_texts)
    tags: list[str] = []
    seen: set[str] = set()

    for pattern, label in _EXPERIENCE_TAGS:
        if label in seen:
            continue
        if re.search(pattern, combined, re.IGNORECASE):
            formatted = _format_phrase(label)
            if formatted and formatted not in seen:
                tags.append(formatted)
                seen.add(formatted)
        if len(tags) >= 5:
            break

    return tags


# ── Hero quote selection ──────────────────────────────────────────────────────

def _pick_quote(reviews: list) -> str:
    """
    Select the best single hero quote.

    Requirements:
    - rating >= 4
    - cleaned length 40–120 chars
    - contains at least one meaningful noun
    - not in the generic-phrase blacklist

    Falls back progressively:
    1. 5-star reviews in ideal 40-120 char range with noun signal
    2. 4-star reviews same criteria
    3. Any 4+ star review with noun signal (truncated to 120 chars)
    4. Empty string — never force a bad quote
    """
    def _clean(text: str) -> str:
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'^[^a-zA-Z"\']+', '', text).strip()
        return text

    def _has_signal(text: str) -> bool:
        tl = text.lower()
        return any(re.search(r'\b' + re.escape(n) + r'\b', tl) for n in _QUOTE_SIGNAL_NOUNS)

    def _is_blacklisted(text: str) -> bool:
        tl = text.lower()
        return any(bl in tl for bl in _QUOTE_BLACKLIST)

    def _truncate(text: str) -> str:
        if len(text) <= 120:
            return text
        return text[:120].rsplit(' ', 1)[0].rstrip('.,;:') + "…"

    def _signal_count(text: str) -> int:
        """Count how many distinct signal nouns appear in the text."""
        tl = text.lower()
        return sum(1 for n in _QUOTE_SIGNAL_NOUNS
                   if re.search(r'\b' + re.escape(n) + r'\b', tl))

    # Sort: highest rating first, then most signal nouns, then longest (up to 120 chars)
    candidates = sorted(
        [r for r in reviews if int(r.get("rating") or 0) >= 4],
        key=lambda r: (
            -int(r.get("rating") or 0),
            -_signal_count(_clean(r.get("text") or "")),
            -min(len(_clean(r.get("text") or "")), 120),
        ),
    )

    # Pass 1: ideal range, has signal, not blacklisted
    for r in candidates:
        text = _clean(r.get("text") or "")
        if len(text) < 40:
            continue
        if _is_blacklisted(text):
            continue
        if not _has_signal(text):
            continue
        return _truncate(text)

    # Pass 2: relax length floor to 30, still need signal
    for r in candidates:
        text = _clean(r.get("text") or "")
        if len(text) < 30:
            continue
        if _is_blacklisted(text):
            continue
        if not _has_signal(text):
            continue
        return _truncate(text)

    # Pass 3: anything from a 4+ star review that isn't blacklisted
    for r in candidates:
        text = _clean(r.get("text") or "")
        if len(text) < 20:
            continue
        if _is_blacklisted(text):
            continue
        return _truncate(text)

    return ""  # No usable quote — omit rather than force a bad one


# ── None-safe normalisation ───────────────────────────────────────────────────

def _safe_list(val) -> list:
    """Ensure value is a non-None list."""
    if not val:
        return []
    return [item for item in val if item]


# ── Public entry point ────────────────────────────────────────────────────────

def extract_review_intel(reviews: list) -> dict:
    """
    Extract structured insight from a list of review dicts.

    Each dict should have:
        text   : str  — review body
        rating : int  — 1–5 star rating

    Returns:
        {
            top_highlights  : list[str],  # category phrases, e.g. "Great coffee"
            signature_items : list[str],  # named items, e.g. "Flat White"
            experience_tags : list[str],  # vibe/experience, e.g. "Cosy atmosphere"
            top_review_quote: str,        # real review quote ≤ 120 chars
        }

    All arrays default to []. Quote defaults to "".
    Never fabricates content.
    """
    _empty = {
        "top_highlights":   [],
        "signature_items":  [],
        "experience_tags":  [],
        "top_review_quote": "",
    }

    if not reviews:
        return _empty

    pos_texts = _positive_texts(reviews)

    top_highlights   = _safe_list(_extract_highlights(pos_texts))
    signature_items  = _safe_list(_extract_signature_items(pos_texts))
    experience_tags  = _safe_list(_extract_experience_tags(pos_texts))
    top_review_quote = _pick_quote(reviews)

    # ── Cross-deduplication: remove any experience_tag that exactly matches a highlight ──
    if top_highlights:
        hl_lower = {h.lower() for h in top_highlights}
        experience_tags = [t for t in experience_tags if t.lower() not in hl_lower]

    return {
        "top_highlights":   top_highlights,
        "signature_items":  signature_items,
        "experience_tags":  experience_tags,
        "top_review_quote": top_review_quote,
    }
