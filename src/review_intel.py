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

Extraction rules:
- Only uses reviews with rating >= 4
- Only surfaces phrases present in review text (no invention)
- Prioritises frequency (appears in more than 1 review)
- Keeps phrases short (2–4 words)
- Returns empty arrays when evidence is insufficient (prefer empty over fake)
"""

import re
from collections import defaultdict


# ── Quality nouns with preferred adjectives (ordered best → acceptable) ───────

_QUALITY_NOUNS: list[tuple[str, list[str], str]] = [
    # (noun_pattern, preferred_adjectives, display_label)
    ("coffee",      ["amazing", "great", "excellent", "best", "fantastic", "perfect", "good", "incredible"], "coffee"),
    ("flat white",  ["amazing", "great", "best", "perfect", "excellent"],                                    "flat white"),
    ("food",        ["amazing", "great", "excellent", "delicious", "incredible", "fantastic", "good", "lovely"], "food"),
    ("service",     ["great", "excellent", "amazing", "top-notch", "spot on", "perfect", "good", "quick"],   "service"),
    ("staff",       ["friendly", "amazing", "great", "lovely", "wonderful", "helpful", "welcoming", "inviting"], "staff"),
    ("atmosphere",  ["great", "amazing", "beautiful", "lovely", "wonderful", "vibey", "perfect"],            "atmosphere"),
    ("milkshakes",  ["best", "amazing", "great", "gourmet"],                                                 "milkshakes"),
    ("milkshake",   ["best", "amazing", "great", "gourmet"],                                                 "milkshake"),
    ("breakfast",   ["amazing", "great", "excellent", "best", "fantastic"],                                  "breakfast"),
    ("lunch",       ["great", "amazing", "excellent", "best"],                                               "lunch"),
    ("brunch",      ["great", "amazing", "excellent"],                                                       "brunch"),
    ("views",       ["beautiful", "amazing", "great", "stunning", "incredible"],                             "views"),
    ("vibes",       ["great", "good", "amazing", "fantastic", "wonderful"],                                  "vibes"),
    ("meals",       ["amazing", "great", "delicious", "excellent", "fresh"],                                 "meals"),
    ("burgers",     ["best", "great", "amazing", "incredible"],                                              "burgers"),
    ("burger",      ["best", "great", "amazing", "incredible"],                                              "burger"),
    ("cakes",       ["amazing", "great", "delicious", "best"],                                               "cakes"),
    ("cake",        ["amazing", "great", "delicious", "best"],                                               "cake"),
    ("coffee shop", ["best", "favourite", "amazing", "great"],                                               "coffee shop"),
    ("place",       ["best", "amazing", "great", "favourite", "incredible", "perfect"],                      "place"),
    ("spot",        ["best", "amazing", "great", "favourite", "perfect"],                                    "spot"),
]

# Adjectives that imply strong quality even without a paired noun
_STRONG_STANDALONE = [
    r'\bnever disappoint',         # "food never disappoints"
    r'\bhighly recommend',         # "highly recommend"
    r'\babsolutely top',           # "absolutely top-notch"
]


# ── Specific food/drink items to surface ──────────────────────────────────────

_ITEM_PATTERNS: list[tuple[str, str]] = [
    # (regex_pattern, display_label) — ordered most specific → generic
    (r'\bflat\s+white\b',          "Flat White"),
    (r'\bcappuccino\b',             "Cappuccino"),
    (r'\bcortado\b',                "Cortado"),
    (r'\bmacchiato\b',              "Macchiato"),
    (r'\bespresso\b',               "Espresso"),
    (r'\bcold\s+brew\b',            "Cold Brew"),
    (r'\biced\s+latte\b',           "Iced Latte"),
    (r'\blatte\b',                  "Latte"),
    (r'\bamericano\b',              "Americano"),
    (r'\bpour[\s-]?over\b',         "Pour Over"),
    (r'\bgourmet\s+milkshake',      "Gourmet Milkshakes"),
    (r'\bmilkshake\b',              "Milkshakes"),
    (r'\bsmoothie\b',               "Smoothies"),
    (r'\bhot\s+chocolate\b',        "Hot Chocolate"),
    (r'\beggs?\s+benedict\b',       "Eggs Benedict"),
    (r'\bfried\s+eggs?\b',          "Fried Eggs"),
    (r'\bscrambled\s+eggs?\b',      "Scrambled Eggs"),
    (r'\bavocado\s+toast\b|avo\s+toast\b', "Avo Toast"),
    (r'\bcroissant\b',              "Croissant"),
    (r'\bfrench\s+toast\b',         "French Toast"),
    (r'\bwaffle\b',                 "Waffles"),
    (r'\bpancake\b',                "Pancakes"),
    (r'\bscone\b',                  "Scones"),
    (r'\bmuffin\b',                 "Muffins"),
    (r'\bbrownie\b',                "Brownies"),
    (r'\bcheesecake\b',             "Cheesecake"),
    (r'\bcake\b',                   "Cake"),
    (r'\bpastry\b|\bpastries\b',    "Pastries"),
    (r'\bpie\b',                    "Pie"),
    (r'\bsoup\b',                   "Soup"),
    (r'\bsalad\b',                  "Salad"),
    (r'\bsandwich\b|\bsandwiches\b',"Sandwiches"),
    (r'\btoastie\b|\btoasted\s+sandwich\b', "Toasties"),
    (r'\bwrap\b',                   "Wraps"),
    (r'\bburger\b',                 "Burgers"),
    (r'\bsteak\b',                  "Steak"),
    (r'\bpasta\b',                  "Pasta"),
    (r'\bpizza\b',                  "Pizza"),
    (r'\bfish\b',                   "Fish"),
    (r'\bchicken\b',                "Chicken"),
    (r'\bbreakfast\s+special\b',    "Breakfast Special"),
]


# ── Experience / vibe tags ────────────────────────────────────────────────────

_EXPERIENCE_TAGS: list[tuple[str, str]] = [
    # (regex, display_label)
    (r'\bfamily[\s-]?friendly\b',                                                "Family friendly"),
    (r'\bdog[\s-]?friendly\b',                                                   "Dog friendly"),
    (r'\bpet[\s-]?friendly\b',                                                   "Pet friendly"),
    (r'\bkid[\s-]?friendly\b|\bchildren.{0,15}welcom',                          "Family friendly"),
    (r'\bhidden gem\b',                                                          "Hidden gem"),
    (r'\boutdoor\s+(seating|dining|area|terrace)\b',                             "Outdoor seating"),
    (r'\blive\s+music\b',                                                        "Live music"),
    (r'\bbeautiful\s+(views?|scenery|setting|surroundings)\b',                   "Beautiful views"),
    (r'\bamazing\s+(views?|scenery|setting)\b|\bstunning\s+views?\b',            "Beautiful views"),
    (r'\bgreat\s+for\s+breakfast\b|\bbreakfast\s+(spot|place|destination)\b',   "Great for breakfast"),
    (r'\bgreat\s+for\s+(lunch|brunch)\b|\b(lunch|brunch)\s+spot\b',             "Good for lunch"),
    (r'\bcosy\b|\bcozy\b',                                                       "Cosy atmosphere"),
    (r'\bvibey\b|\bgreat\s+vibes?\b|\bamazing\s+vibes?\b|\bgood\s+vibes?\b',    "Great vibes"),
    # broad atmosphere — catches "great atmosphere", "beautiful atmosphere", "lovely atmosphere"
    (r'\b(great|amazing|beautiful|lovely|wonderful|perfect)\s+atmosphere\b',    "Great atmosphere"),
    # friendly staff — catches "friendly staff", "welcoming staff", "amazing staff"
    (r'\b(friendly|welcoming|amazing|wonderful|inviting)\s+staff\b',            "Friendly staff"),
    # great service — catches "great service", "top-notch service", "service was spot on"
    (r'\b(great|excellent|amazing|top[\s-]?notch|spot\s+on)\s+service\b'
     r'|\bservice\s+(was\s+)?(top[\s-]?notch|excellent|amazing|spot\s+on|perfect)\b', "Great service"),
    (r'\bwarm\s+(welcome|service|atmosphere)\b|\bwarm\s+and\s+welcom',           "Warm welcome"),
    (r'\bperfect\s+(spot|place|setting|location)\b',                             "Perfect spot"),
    (r'\binstagram(mable)?\b|\bphoto[\s-]?worthy\b',                             "Instagram-worthy"),
    (r'\brelax(ing|ed)?\b|\bpeaceful\b|\bquiet\s+(spot|place|setting)\b',       "Relaxed vibe"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Normalise: lowercase, collapse whitespace."""
    return re.sub(r'\s+', ' ', (text or "").lower().strip())


def _positive_reviews(reviews: list) -> list[str]:
    """Return normalised text from reviews with rating >= 4."""
    return [
        _norm(r.get("text", "") or "")
        for r in reviews
        if int(r.get("rating") or 0) >= 4
    ]


def _all_reviews_text(reviews: list) -> list[str]:
    """Return normalised text from all reviews."""
    return [_norm(r.get("text", "") or "") for r in reviews]


# ── Extraction functions ──────────────────────────────────────────────────────

def _extract_highlights(positive_texts: list[str]) -> list[str]:
    """
    Find top quality highlights from positive (4+ star) reviews.

    For each quality noun:
    1. Count how many reviews mention it
    2. Find the best adjacent adjective from the preferred list
    3. Build a 2-word highlight phrase, capitalised

    Returns max 5 highlights sorted by frequency descending.
    """
    combined = " ".join(positive_texts)
    highlights: list[tuple[int, str]] = []
    used_labels: set[str] = set()

    for noun_pattern, preferred_adjs, display_label in _QUALITY_NOUNS:
        # Skip if this label (or a near-duplicate) is already captured
        base_key = display_label.split()[0]
        if base_key in used_labels:
            continue

        # Count mentions across individual reviews
        count = sum(1 for t in positive_texts if re.search(r'\b' + re.escape(noun_pattern) + r'\b', t))
        if count == 0:
            continue

        # Find best adjective adjacent to noun
        chosen_adj = None
        for adj in preferred_adjs:
            # adj appears within 25 chars BEFORE the noun
            if re.search(r'\b' + re.escape(adj) + r'.{0,25}\b' + re.escape(noun_pattern) + r'\b', combined):
                chosen_adj = adj
                break
            # noun appears within 25 chars BEFORE the adj (reverse order)
            if re.search(r'\b' + re.escape(noun_pattern) + r'.{0,25}\b' + re.escape(adj) + r'\b', combined):
                chosen_adj = adj
                break

        if chosen_adj:
            phrase = f"{chosen_adj.capitalize()} {display_label}"
        elif count >= 2:
            # Noun mentioned multiple times but no adj found — still worth surfacing
            phrase = display_label.capitalize()
        else:
            # Single mention, no adjective — skip (too weak)
            continue

        highlights.append((count, phrase))
        used_labels.add(base_key)

    # Sort by frequency desc, deduplicate, return top 5
    highlights.sort(key=lambda x: -x[0])
    return [phrase for _, phrase in highlights[:5]]


def _extract_signature_items(positive_texts: list[str]) -> list[str]:
    """
    Find specific menu/product items mentioned in positive reviews.
    Returns max 5 items, ordered by how early they appear in the pattern list
    (most specific matches first).
    """
    combined = " ".join(positive_texts)
    found: list[str] = []
    seen_labels: set[str] = set()

    for pattern, label in _ITEM_PATTERNS:
        if label in seen_labels:
            continue
        if re.search(pattern, combined, re.IGNORECASE):
            # Avoid near-duplicates (e.g. "Milkshakes" after "Gourmet Milkshakes")
            base = label.lower().split()[-1]
            if base not in seen_labels:
                found.append(label)
                seen_labels.add(label)
                seen_labels.add(base)
        if len(found) >= 5:
            break

    return found


def _extract_experience_tags(positive_texts: list[str]) -> list[str]:
    """
    Match predefined experience / vibe phrases from positive reviews.
    Returns max 5 unique tags.
    """
    combined = " ".join(positive_texts)
    tags: list[str] = []
    seen_labels: set[str] = set()

    for pattern, label in _EXPERIENCE_TAGS:
        if label in seen_labels:
            continue
        if re.search(pattern, combined, re.IGNORECASE):
            tags.append(label)
            seen_labels.add(label)
        if len(tags) >= 5:
            break

    return tags


def _pick_quote(reviews: list) -> str:
    """
    Pick the best single review quote for the hero section.

    Priority:
    1. 5-star reviews with 40–180 chars of clean text
    2. 4-star reviews
    3. Any review

    Truncates to 120 chars at a word boundary.
    """
    def _clean_text(text: str) -> str:
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove leading emoji/symbol noise
        text = re.sub(r'^[^a-zA-Z"\']+', '', text).strip()
        return text

    # Sort: 5-star first, then by text length (prefer medium-length quotes)
    sorted_reviews = sorted(
        reviews,
        key=lambda r: (-int(r.get("rating") or 0), -min(len(r.get("text") or ""), 150)),
    )

    for r in sorted_reviews:
        text = _clean_text(r.get("text") or "")
        if len(text) < 30:
            continue
        # Skip reviews that are mostly negative signals
        negative_signals = ["not allowed", "no vegan", "wouldn't allow", "terrible", "awful", "worst"]
        if any(sig in text.lower() for sig in negative_signals):
            continue
        # Truncate at 120 chars, word boundary
        if len(text) <= 120:
            return text
        truncated = text[:120].rsplit(' ', 1)[0].rstrip(',.:;')
        return truncated + "…"

    return ""


# ── Public entry point ────────────────────────────────────────────────────────

def extract_review_intel(reviews: list) -> dict:
    """
    Extract structured insight from a list of review dicts.

    Each review dict should have:
        text   : str   — review body
        rating : int   — 1-5 star rating
        author : str   — reviewer name (optional, not used)

    Returns:
        {
            top_highlights  : list[str],  # max 5, e.g. "Great coffee"
            signature_items : list[str],  # max 5, e.g. "Flat White"
            experience_tags : list[str],  # max 5, e.g. "Cosy atmosphere"
            top_review_quote: str,        # max 120 chars, real review text
        }

    Returns empty arrays/string if reviews are absent or too weak to extract
    meaningful signals. Never fabricates content.
    """
    if not reviews:
        return {
            "top_highlights":    [],
            "signature_items":   [],
            "experience_tags":   [],
            "top_review_quote":  "",
        }

    positive_texts = _positive_reviews(reviews)

    # Failsafe: if fewer than 2 positive reviews, signals will be too sparse
    # Still attempt extraction but accept the result may be empty
    top_highlights   = _extract_highlights(positive_texts) if positive_texts else []
    signature_items  = _extract_signature_items(positive_texts) if positive_texts else []
    experience_tags  = _extract_experience_tags(positive_texts) if positive_texts else []
    top_review_quote = _pick_quote(reviews)

    return {
        "top_highlights":   top_highlights,
        "signature_items":  signature_items,
        "experience_tags":  experience_tags,
        "top_review_quote": top_review_quote,
    }
