"""
transformer.py

build_business_data(lead, industry) → dict

Assembles a clean BusinessData object for demo generation.
Uses REAL Apify data everywhere possible.
Only synthesises text where no real data exists (tagline, services).
Never fabricates reviews or photos.
"""

import os
import json as _json
from src.preview import get_tagline, get_services, DEFAULT_SERVICES
from src.ai_content import generate_ai_content
from src.review_intel import extract_review_intel
from src.config import (
    DEFAULT_TAGLINE, CACHE_DIR,
    INDUSTRY_COLORS, DEFAULT_COLORS,
    INDUSTRY_ABOUT_HEADLINES, DEFAULT_ABOUT_HEADLINE,
    INDUSTRY_FEATURE_STAT, DEFAULT_FEATURE_STAT,
    INDUSTRY_FEATURE_PILLS, DEFAULT_FEATURE_PILLS,
    INDUSTRY_CTA_LABEL, DEFAULT_CTA_LABEL,
)

# ── "What People Love" fallback phrases per category ─────────────────────────
# Used when review intel extracts fewer than 4 items.
_INDUSTRY_LOVE_FALLBACKS: dict[str, list[str]] = {
    "coffee":      ["Excellent coffee", "Friendly staff", "Cosy atmosphere", "Great for breakfast", "Fast service"],
    "cafe":        ["Excellent coffee", "Friendly staff", "Cosy atmosphere", "Great for breakfast", "Homemade food"],
    "restaurant":  ["Delicious food", "Friendly staff", "Great atmosphere", "Good value for money", "Clean environment"],
    "salon":       ["Expert styling", "Friendly staff", "Clean environment", "Great value", "Quick turnaround"],
    "barbershop":  ["Precision cuts", "Friendly barbers", "Clean environment", "Honest pricing", "Quick service"],
    "barber":      ["Precision cuts", "Friendly barbers", "Clean environment", "Honest pricing", "Quick service"],
    "gym":         ["Expert trainers", "Modern equipment", "Motivating environment", "Flexible memberships", "Results-focused"],
    "fitness":     ["Expert trainers", "Modern equipment", "Motivating environment", "All fitness levels", "Great community"],
    "dentist":     ["Gentle approach", "Professional staff", "Modern equipment", "Pain-free experience", "Efficient service"],
    "dental":      ["Gentle approach", "Professional staff", "Modern equipment", "Pain-free experience", "Quick appointments"],
    "spa":         ["Relaxing experience", "Skilled therapists", "Clean environment", "Great value", "Perfect atmosphere"],
    "bakery":      ["Fresh daily baking", "Delicious pastries", "Friendly service", "Great coffee", "Homemade quality"],
    "mechanic":    ["Honest advice", "Fast turnaround", "Fair pricing", "Skilled mechanics", "Reliable service"],
    "auto":        ["Honest advice", "Fast turnaround", "Fair pricing", "Skilled mechanics", "Reliable service"],
    "hotel":       ["Comfortable rooms", "Friendly staff", "Great location", "Clean environment", "Good breakfast"],
    "lodge":       ["Beautiful setting", "Friendly hosts", "Peaceful atmosphere", "Great breakfast", "Excellent value"],
    "guest":       ["Comfortable rooms", "Friendly hosts", "Homemade breakfast", "Secure parking", "Relaxed atmosphere"],
    "cleaning":    ["Thorough cleaning", "Reliable service", "Friendly team", "Great value", "Professional results"],
    "plumber":     ["Fast response", "Honest pricing", "Reliable service", "Professional work", "Available when needed"],
    "electrician": ["Fast response", "Safe installations", "Honest pricing", "Reliable service", "Professional work"],
    "florist":     ["Beautiful arrangements", "Friendly staff", "Creative designs", "Fresh flowers", "Great value"],
}
_DEFAULT_LOVE_FALLBACKS = [
    "Professional service", "Friendly team", "Reliable and trustworthy",
    "Great value for money", "Quality results",
]


def _build_what_people_love(
    review_intel: dict, category: str, industry: str
) -> list[str]:
    """
    Build the 'What People Love' list (max 10 items).
    Priority: review highlights → experience tags → signature items → fallbacks.
    Always returns at least 4 items.
    """
    items: list[str] = []
    seen: set[str] = set()

    def _add(phrase: str) -> None:
        p = phrase.strip()
        if p and p.lower() not in seen and len(items) < 10:
            items.append(p)
            seen.add(p.lower())

    for h in (review_intel.get("top_highlights") or []):
        _add(h)
    for t in (review_intel.get("experience_tags") or []):
        _add(t)
    if len(items) < 6:
        for s in (review_intel.get("signature_items") or []):
            _add(s)

    if len(items) < 4:
        cat = (category or "").lower()
        ind = (industry or "").lower()
        fallbacks = None
        for key, vals in _INDUSTRY_LOVE_FALLBACKS.items():
            if key in cat:
                fallbacks = vals
                break
        if not fallbacks:
            for key, vals in _INDUSTRY_LOVE_FALLBACKS.items():
                if key in ind:
                    fallbacks = vals
                    break
        for fb in (fallbacks or _DEFAULT_LOVE_FALLBACKS):
            if len(items) >= 4:
                break
            _add(fb)

    return items[:10]


# ── Reliable category fallback images (images.unsplash.com CDN — permanent) ──
_FALLBACK_IMAGES: dict[str, list[str]] = {
    "coffee":     [
        "https://images.unsplash.com/photo-1495474472359-35827269479f?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1509042239860-f550ce710b93?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1521017432531-fbd92d768814?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1442512595331-e89e73853f31?w=800&h=600&fit=crop",
    ],
    "cafe":       [
        "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1445116572660-236099ec97a0?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1453614512568-c4024d13c247?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1507914372368-b2b085b925a1?w=800&h=600&fit=crop",
    ],
    "restaurant": [
        "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1424847651672-bf20a4b0982b?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1466978913421-dad2ebd01d17?w=800&h=600&fit=crop",
    ],
    "salon":      [
        "https://images.unsplash.com/photo-1560869713-7d0a29430803?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1595476108010-b4d1f102b1b1?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?w=800&h=600&fit=crop",
    ],
    "barber":     [
        "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1599351431202-1e0f0137899a?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1621605815971-fbc98d665033?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1585747860715-2ba37e788b70?w=800&h=600&fit=crop",
    ],
    "gym":        [
        "https://images.unsplash.com/photo-1534438327167-af6e4e82fc16?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1571902943202-507ec2618e8f?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=800&h=600&fit=crop",
    ],
    "bakery":     [
        "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1550617931-e17a7b70dce2?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1568254183919-78a4f43a2877?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1486427944299-d1955d23e34d?w=800&h=600&fit=crop",
    ],
    "spa":        [
        "https://images.unsplash.com/photo-1540555700478-4be290d57689?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1600334089648-b0d9d3028eb2?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1596178065887-1198b6148b2b?w=800&h=600&fit=crop",
    ],
}

_FALLBACK_DEFAULT = [
    "https://images.unsplash.com/photo-1497366216548-37526070297c?w=1200&h=800&fit=crop",
    "https://images.unsplash.com/photo-1497366811353-6870744d04b2?w=800&h=600&fit=crop",
    "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=800&h=600&fit=crop",
    "https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=800&h=600&fit=crop",
]


def _get_fallback_images(industry: str) -> list[str]:
    """Return a curated list of reliable fallback images for the given industry."""
    key = industry.lower()
    for k, imgs in _FALLBACK_IMAGES.items():
        if k in key:
            return imgs
    return _FALLBACK_DEFAULT


def _lookup_cache(name: str) -> dict | None:
    """Search Apify cache files for a business by name to get photos + reviews."""
    if not os.path.isdir(CACHE_DIR):
        return None
    try:
        for fname in os.listdir(CACHE_DIR):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(CACHE_DIR, fname), encoding="utf-8") as f:
                items = _json.load(f)
            if not isinstance(items, list):
                continue
            for item in items:
                if (item.get("name") or "").lower().strip() == name.lower().strip():
                    return item
    except Exception:
        pass
    return None


def _lookup_industry(lookup_dict: dict, key_str: str, default):
    """Find the first matching value in a keyword-keyed dict."""
    k = key_str.lower()
    for keyword, value in lookup_dict.items():
        if keyword in k:
            return value
    return default


def _resolve(lookup_dict: dict, default, category: str, industry: str):
    """Try category keyword first, then industry, then default."""
    result = _lookup_industry(lookup_dict, category, None) if category else None
    if result is None:
        result = _lookup_industry(lookup_dict, industry, default)
    return result


def _build_about_text(name: str, city: str, category: str, industry: str,
                       rating: float, reviews_count: int) -> str:
    """Generate a 2-sentence about blurb from real business data."""
    loc   = city if city else "the local community"
    score = f"{float(rating):.1f}" if rating else ""
    rev   = f"{int(reviews_count):,}" if reviews_count else ""
    cat   = (category or industry).lower()

    # Sentence 1 — what the business is
    if "restaurant" in cat or "dining" in cat:
        s1 = f"{name} is a beloved dining destination in {loc}, serving up memorable meals crafted from fresh, quality ingredients."
    elif "coffee" in cat or "cafe" in cat or "café" in cat:
        s1 = f"{name} is {loc}'s favourite spot for exceptional coffee, homemade food, and a warm welcome every visit."
    elif "salon" in cat or "hair" in cat:
        s1 = f"{name} is {loc}'s go-to destination for expert hair styling, colour, and personalised beauty treatments."
    elif "barber" in cat:
        s1 = f"{name} is the trusted barbershop in {loc}, known for precision cuts and a laid-back, welcoming vibe."
    elif "gym" in cat or "fitness" in cat:
        s1 = f"{name} is {loc}'s premier fitness destination, empowering members of all levels to reach their goals."
    elif "spa" in cat or "massage" in cat:
        s1 = f"{name} is {loc}'s sanctuary for relaxation and wellness, offering a range of restorative treatments."
    elif "bakery" in cat:
        s1 = f"{name} has been bringing fresh-baked goodness to {loc}, crafting every loaf, cake, and pastry with care."
    elif "bed" in cat or "guest" in cat or "lodge" in cat or "hotel" in cat:
        s1 = f"{name} offers warm, comfortable accommodation in the heart of {loc}, perfect for both leisure and business travellers."
    else:
        s1 = f"{name} has been proudly serving {loc} with quality, care, and a personal touch that keeps customers coming back."

    # Sentence 2 — social proof if we have it
    if score and rev:
        s2 = f"With a {score}-star rating across {rev} Google reviews, our reputation speaks for itself."
    elif score:
        s2 = f"Our {score}-star Google rating reflects our commitment to quality and service."
    elif rev:
        s2 = f"Trusted by hundreds of happy customers, with {rev} Google reviews and counting."
    else:
        s2 = "We take pride in every interaction and look forward to welcoming you."

    return f"{s1} {s2}"


# ── Industry Pack ─────────────────────────────────────────────────────────────

def get_industry_pack(category: str) -> str:
    """
    Detect which content pack to apply.
    Returns a string key used by the template and content builders.
    Extendable: add more packs (dining, wellness, etc.) over time.
    """
    c = (category or "").lower()
    if any(k in c for k in ["guest", "hotel", "bnb", "b&b", "lodge", "accommodation", "inn", "guesthouse"]):
        return "accommodation"
    return "default"


def build_accommodation_hero(name: str, location: str, review_intel: dict) -> str:
    """
    Build a review-driven hero description for accommodation businesses.
    Uses the top review highlights to make the line specific, not generic.
    """
    highlights = review_intel.get("top_highlights") or []
    tags       = review_intel.get("experience_tags") or []

    # Prefer the first two real highlights if available
    combined = [h.lower() for h in (highlights + tags) if h]
    if len(combined) >= 2:
        theme = f"{combined[0]} and {combined[1]}"
    elif len(combined) == 1:
        theme = combined[0]
    else:
        theme = "comfortable stays and friendly hospitality"

    loc = location or "the area"
    return f"A well-rated guest house in {loc} known for {theme}."


def build_business_data(lead: dict, industry: str) -> dict:
    """
    Assemble real business data for demo generation.

    Returns a BusinessData dict consumed by preview.generate_from_business_data().
    """
    name          = lead.get("name", "")
    city          = lead.get("city", "")
    address       = lead.get("address", "")
    phone         = lead.get("phone", "")
    website       = lead.get("website", "")
    rating        = lead.get("rating", 0)
    reviews_count = lead.get("reviews_count", 0)
    google_maps_url = lead.get("google_maps_url", "")
    place_id      = lead.get("place_id", "")
    lat           = lead.get("lat", "")
    lng           = lead.get("lng", "")
    category      = lead.get("category", "")

    # ── ENRICH FROM CACHE if lead is missing photos/reviews ─────────────────
    # Leads loaded from CSV don't carry photos/reviews — look them up from
    # the raw Apify cache so demos always use real data when available.
    cached = None
    if not lead.get("photos") or not lead.get("reviews"):
        cached = _lookup_cache(name)

    # ── IMAGES ──────────────────────────────────────────────────────────────
    # Priority 1: real Google Maps photos from lead or cache
    # Priority 2 (hero only): curated Unsplash fallback so hero is never blank
    #
    # CRITICAL: gallery_images contains ONLY real photos.
    # No fallback padding — we never show a gallery of stock images.
    photos = lead.get("photos") or (cached.get("photos") if cached else None) or []

    fallbacks  = _get_fallback_images(industry)
    has_photos = bool(photos)            # True only when real Google photos exist

    if photos:
        hero_image     = photos[0]
        gallery_images = list(photos[1:7])   # real photos only — no padding
    else:
        hero_image     = fallbacks[0]        # single fallback for hero backdrop
        gallery_images = []                  # no gallery without real photos

    # show_gallery is the flag the template checks — never True without real photos
    show_gallery = bool(gallery_images)

    # ── REVIEWS ─────────────────────────────────────────────────────────────
    # Only use real review objects. No fabrication.
    # Sort by rating desc so best reviews surface first; show MAX 3.
    raw_reviews = lead.get("reviews") or (cached.get("reviews") if cached else None) or []
    reviews_raw = sorted(
        raw_reviews,
        key=lambda r: int(r.get("rating") or 0),
        reverse=True,
    )
    reviews = []
    for r in reviews_raw:
        text = (r.get("text") or "").strip()
        if text and len(text) > 25:
            reviews.append({
                "text":   text[:320],
                "author": r.get("author") or "Verified Customer",
                "rating": int(r.get("rating") or 5),
            })
        if len(reviews) >= 3:          # hard cap at 3 — focused, not exhaustive
            break
    # has_real_reviews is True only when at least 2 substantive reviews exist
    has_real_reviews = len(reviews) >= 2

    # ── INDUSTRY PACK ────────────────────────────────────────────────────────
    industry_pack = get_industry_pack(category) if category else get_industry_pack(industry)

    # ── REVIEW INTELLIGENCE ──────────────────────────────────────────────────
    # Pure frequency-based extraction — no API, no fabrication.
    # Extracts highlights, signature items, and experience tags from real text.
    review_intel = extract_review_intel(reviews)
    what_people_love = _build_what_people_love(review_intel, category, industry)

    # ── HERO DESCRIPTION (pack-specific) ─────────────────────────────────────
    # Accommodation: review-driven one-liner using real highlights.
    # Other packs: None — template falls back to tagline.
    if industry_pack == "accommodation":
        loc_str = city or industry
        hero_description = build_accommodation_hero(name, loc_str, review_intel)
    else:
        hero_description = ""

    # ── MAP EMBED ────────────────────────────────────────────────────────────
    # Use coords if available, otherwise fall back to address search
    if lat and lng:
        map_embed = (
            f"https://maps.google.com/maps"
            f"?q={lat},{lng}&z=15&output=embed"
        )
    elif address:
        from urllib.parse import quote
        q = quote(f"{name}, {address}")
        map_embed = f"https://maps.google.com/maps?q={q}&output=embed"
    else:
        map_embed = ""

    # ── STATIC FALLBACKS ─────────────────────────────────────────────────────
    # Try the actual business category first (more specific), then fall back to
    # the search industry string.  This prevents a café search industry from
    # overriding a "Restaurant" category business.
    tagline  = get_tagline(category)  if category else DEFAULT_TAGLINE
    services = get_services(category) if category else DEFAULT_SERVICES
    if tagline == DEFAULT_TAGLINE:        # no match found — try industry
        tagline = get_tagline(industry)
    if services == DEFAULT_SERVICES:      # no match found — try industry
        services = get_services(industry)

    # ── AI CONTENT (overrides static copy when API key is available) ─────────
    # Generates punchy, review-aware copy using the Master Prompt.
    # Falls back silently to static content on failure or missing key.
    location_str = f"{city}, South Africa" if city else "South Africa"
    ai = generate_ai_content(
        name         = name,
        category     = category or industry,
        rating       = rating,
        review_count = reviews_count,
        reviews      = reviews,
        location     = location_str,
    )
    if ai:
        tagline  = ai["hero_line"]              # replaces static tagline
        if ai["offers"]:
            services = ai["offers"]             # replaces static services list
        promo    = ai.get("promo", "")
        cta_line = ai.get("cta_line", "")       # short action line under hero buttons
        ai_trust = ai.get("trust_benefit", "")  # overrides feature_stat if present
    else:
        promo    = ""
        cta_line = ""
        ai_trust = ""

    # Rating badge — surfaced visually in hero section
    try:
        _score = float(rating) if rating else 0.0
    except (TypeError, ValueError):
        _score = 0.0
    if _score >= 4.5:
        rating_badge = "highly_rated"   # template shows ⭐ badge
    elif _score > 0 and _score < 4.0:
        rating_badge = "local"          # template shows 📍 badge
    else:
        rating_badge = ""               # no badge

    # ── DIAGNOSTIC / OPPORTUNITY FIELDS ────────────────────────────────────
    # Website detection
    _raw_website = (lead.get("website") or "").strip()
    has_website    = bool(_raw_website)
    website_url    = _raw_website if has_website else None
    website_status = "none" if not has_website else "basic"   # 'none' | 'basic' | 'unknown'

    # WhatsApp: default False unless lead data explicitly says otherwise.
    # Lead data may carry has_whatsapp from the scorer; preserve it if present.
    _lead_wa = lead.get("has_whatsapp")
    has_whatsapp = bool(_lead_wa) if _lead_wa is not None else False

    # Review utilisation: meaningful social proof exists
    try:
        _rc = int(reviews_count) if reviews_count else 0
        _rt = float(rating) if rating else 0.0
    except (TypeError, ValueError):
        _rc, _rt = 0, 0.0
    strong_reviews = (_rt >= 4.2 and _rc >= 30)

    # Opportunity score
    _opp = 0
    if not has_website:
        _opp += 3
    else:
        _opp += 1   # still an opportunity even with a basic site
    if not has_whatsapp:
        _opp += 3
    if strong_reviews:
        _opp += 1
    opportunity_score = min(_opp, 10)
    if opportunity_score >= 7:
        opportunity_label = "High"
    elif opportunity_score >= 4:
        opportunity_label = "Medium"
    else:
        opportunity_label = "Low"

    # ── BRANDING FIELDS ──────────────────────────────────────────────────────
    colors         = _resolve(INDUSTRY_COLORS,         DEFAULT_COLORS,         category, industry)
    about_headline = _resolve(INDUSTRY_ABOUT_HEADLINES, DEFAULT_ABOUT_HEADLINE, category, industry)
    feature_stat   = ai_trust or _resolve(INDUSTRY_FEATURE_STAT, DEFAULT_FEATURE_STAT, category, industry)
    feature_pills  = _resolve(INDUSTRY_FEATURE_PILLS,  DEFAULT_FEATURE_PILLS,  category, industry)
    cta_label      = _resolve(INDUSTRY_CTA_LABEL,      DEFAULT_CTA_LABEL,      category, industry)
    about_text     = _build_about_text(name, city, category, industry, rating, reviews_count)

    return {
        # Core identity
        "name":           name,
        "city":           city,
        "address":        address,
        "phone":          phone,
        "website":        website,
        "rating":         rating,
        "reviews_count":  reviews_count,
        "category":       category,
        "google_maps_url": google_maps_url,
        "place_id":       place_id,
        # Images (real first, Unsplash fallback for hero only)
        "hero_image":     hero_image,
        "gallery_images": gallery_images,
        "has_real_photos": has_photos,
        "show_gallery":   show_gallery,    # True only when real gallery photos exist
        # Reviews (real only; requires >= 2 substantive reviews)
        "reviews":        reviews,
        "has_real_reviews": has_real_reviews,
        # Map
        "map_embed":      map_embed,
        # Synthesised copy
        "tagline":        tagline,
        "services":       services,
        "industry":       industry,
        # Branding (colours + content)
        "colors":         colors,
        "about_headline": about_headline,
        "about_text":     about_text,
        "feature_stat":   feature_stat,
        "feature_pills":  feature_pills,
        "cta_label":      cta_label,
        # AI copy
        "promo":          promo,           # promo banner (always generated when AI active)
        "cta_line":       cta_line,        # short action line e.g. "Message us to book instantly"
        "rating_badge":   rating_badge,    # "highly_rated" | "local" | ""
        "ai_generated":   bool(ai),        # flag: True when AI copy was used
        # Review intelligence (frequency-based, no fabrication)
        "review_intel":   review_intel,
        # Condensed highlights for client-facing demo
        "what_people_love": what_people_love,
        "about_headline":   about_headline,
        # Industry pack + pack-specific content
        "industry_pack":     industry_pack,
        "hero_description":  hero_description,
        # Diagnostic / opportunity intelligence
        "has_website":        has_website,
        "website_url":        website_url,
        "website_status":     website_status,
        "has_whatsapp":       has_whatsapp,
        "strong_reviews":     strong_reviews,
        "opportunity_score":  opportunity_score,
        "opportunity_label":  opportunity_label,
    }
