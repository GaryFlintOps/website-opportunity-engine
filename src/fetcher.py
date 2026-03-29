"""
fetcher.py

Fetches leads from Apify Google Maps scraper.

LOCAL_MODE:
  - Controlled entirely by the environment variable LOCAL_MODE.
  - Default: FALSE (live Apify mode).
  - Set LOCAL_MODE=true to use mock data (CI / offline dev only).

Apify actor: compass/crawler-google-places
"""

import os
import json
import re
import time
import unicodedata
import requests
from src.config import APIFY_API_TOKEN, APIFY_ACTOR_ID, CACHE_DIR

# ── Local mode flag ───────────────────────────────────────────────────────────
# Default is FALSE — live Apify calls unless explicitly overridden.
LOCAL_MODE = os.getenv("LOCAL_MODE", "false").lower() == "true"

# ── Limits ────────────────────────────────────────────────────────────────────
MAX_PLACES   = 30   # max leads returned per search
MAX_REVIEWS  = 5    # reviews kept per place
MAX_IMAGES   = 6    # images kept per place
SYNC_TIMEOUT = 300  # seconds to wait for Apify synchronous run

# Side-channel stats read by pipeline.py
_last_fetch_stats: dict = {"raw": 0, "filtered": 0}


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _query_slug(query: str) -> str:
    slug = unicodedata.normalize("NFKD", query.lower().strip())
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


def _cache_path(query: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{_query_slug(query)}.json")


def _load_cache(query: str) -> list[dict] | None:
    path = _cache_path(query)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"[Fetcher] Cache hit: {path} ({len(data)} items)")
            return data
        except Exception as e:
            print(f"[Fetcher] Cache read error ({path}): {e}")
    return None


def _save_cache(query: str, leads: list[dict]) -> None:
    path = _cache_path(query)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        print(f"[Fetcher] Cache saved: {path}")
    except Exception as e:
        print(f"[Fetcher] Cache write error: {e}")


# ── Industry keyword map ──────────────────────────────────────────────────────
# Maps an industry term to keywords that should appear in the business
# name or category for it to be considered a relevant result.
INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "bike":         ["bike", "bicycle", "cycling", "cycle", "velo"],
    "bicycle":      ["bike", "bicycle", "cycling", "cycle", "velo"],
    "cycling":      ["bike", "bicycle", "cycling", "cycle", "velo"],
    "cycle":        ["bike", "bicycle", "cycling", "cycle", "velo"],
    "dentist":      ["dentist", "dental", "orthodont", "smile"],
    "dental":       ["dentist", "dental", "orthodont", "smile"],
    "cafe":         ["cafe", "café", "coffee", "espresso", "bistro", "roastery"],
    "coffee":       ["cafe", "café", "coffee", "espresso", "roastery"],
    "restaurant":   ["restaurant", "dining", "kitchen", "eatery", "grill", "bistro", "diner"],
    "gym":          ["gym", "fitness", "crossfit", "training", "sport", "health club"],
    "fitness":      ["gym", "fitness", "crossfit", "training", "sport", "studio"],
    "salon":        ["salon", "hair", "beauty", "styling", "coiffeur"],
    "barber":       ["barber", "barbershop", "hair", "shave", "grooming", "cuts"],
    "barbershop":   ["barber", "barbershop", "hair", "shave", "grooming", "cuts"],
    "spa":          ["spa", "massage", "wellness", "therapy", "retreat"],
    "bakery":       ["bakery", "baker", "bread", "pastry", "cake", "bake"],
    "plumber":      ["plumb", "plumbing", "pipe", "drain", "water"],
    "electrician":  ["electric", "electrical", "wiring", "power"],
    "cleaning":     ["clean", "cleaning", "hygiene", "maid"],
    "mechanic":     ["mechanic", "auto", "vehicle", "car service", "garage", "workshop", "motor"],
    "hotel":        ["hotel", "accommodation", "lodge", "inn", "guesthouse", "guest house", "rooms"],
    "lodge":        ["lodge", "accommodation", "hotel", "inn", "guesthouse", "retreat", "resort"],
    "guest house":  ["guesthouse", "guest house", "accommodation", "hotel", "inn", "bnb", "b&b"],
    "florist":      ["florist", "flower", "floral", "bloom", "bouquet"],
    "lawyer":       ["law", "legal", "attorney", "advocate", "solicitor"],
    "accountant":   ["accountant", "accounting", "tax", "auditor", "bookkeep"],
    "pharmacy":     ["pharmacy", "chemist", "drug", "pharmaceutical"],
    "optometrist":  ["optom", "optician", "eye", "vision", "glasses"],
}

# ── Bad keywords — hard-reject in business name OR category ──────────────────
# These indicate the result is clearly unrelated to any typical SMB search.
BAD_KEYWORDS: list[str] = [
    "hospital",
    "school",
    "college",
    "university",
    "primary school",
    "high school",
    "farm",
    "shopping mall",
    "shopping centre",
    "shopping center",
    "game reserve",
    "nature reserve",
    "funeral",
    "cemetery",
    "municipality",
    "government",
    "police",
    "prison",
]

# ── Bad business types — reject B2B / non-consumer businesses ─────────────────
# Wholesalers, distributors etc. are not SMB website prospects.
# NOTE: "service centre/center" and "repair centre/center" were deliberately
# removed because they describe legitimate consumer-facing businesses
# (e.g. "Cycle Service Centre", "Phone Repair Center"). B2B trade businesses
# are rejected via the wholesale/distributor/supplier terms below.
BAD_BUSINESS_TYPES: list[str] = [
    "wholesale",
    "wholesaler",
    "supplier",
    "distribution",
    "distributor",
    "manufacturer",
    "manufacturing",
    "importer",
    "exporter",
    "parts supplier",
    "parts store",
    "equipment rental",
    "equipment hire",
    "trade centre",
    "trade center",
]


# ── Location expansion ────────────────────────────────────────────────────────
# Maps small/low-density towns → a list of nearby areas to search in addition.
# All expansions stay within a practical driving radius (~30–60 km).
# Extend this dict as new markets are added — no other code changes needed.

_NEARBY: dict[str, list[str]] = {
    # KZN Midlands cluster
    "hilton":             ["Hilton", "Pietermaritzburg", "Howick", "Midlands"],
    "howick":             ["Howick", "Hilton", "Pietermaritzburg", "Midlands"],
    "midlands":           ["Midlands", "Howick", "Hilton", "Pietermaritzburg"],
    "nottingham road":    ["Nottingham Road", "Howick", "Midlands"],
    "mooi river":         ["Mooi River", "Midlands", "Howick"],
    # KZN coastal / greater Durban
    "ballito":            ["Ballito", "Salt Rock", "Umhlanga", "Dolphin Coast"],
    "salt rock":          ["Salt Rock", "Ballito", "Dolphin Coast"],
    "umhlanga":           ["Umhlanga", "La Lucia", "Ballito"],
    "westville":          ["Westville", "Pinetown", "Durban North"],
    "pinetown":           ["Pinetown", "Westville", "Kloof"],
    "kloof":              ["Kloof", "Hillcrest", "Pinetown"],
    "hillcrest":          ["Hillcrest", "Kloof", "Waterfall"],
    # Western Cape
    "franschhoek":        ["Franschhoek", "Stellenbosch", "Paarl"],
    "stellenbosch":       ["Stellenbosch", "Franschhoek", "Paarl", "Somerset West"],
    "hermanus":           ["Hermanus", "Stanford", "Gansbaai", "Overberg"],
    "knysna":             ["Knysna", "Wilderness", "Plettenberg Bay"],
    "plettenberg bay":    ["Plettenberg Bay", "Knysna", "Plett"],
    "wilderness":         ["Wilderness", "Knysna", "George"],
    # Gauteng / Joburg surrounds
    "fourways":           ["Fourways", "Sandton", "Randburg"],
    "midrand":            ["Midrand", "Halfway House", "Fourways", "Centurion"],
    "centurion":          ["Centurion", "Midrand", "Pretoria"],
    "bedfordview":        ["Bedfordview", "Edenvale", "Germiston"],
    # Eastern Cape / Garden Route
    "grahamstown":        ["Grahamstown", "Makhanda", "Port Alfred"],
    "makhanda":           ["Makhanda", "Grahamstown", "Port Alfred"],
    # Small Limpopo / Mpumalanga
    "white river":        ["White River", "Nelspruit", "Mbombela"],
    "hazyview":           ["Hazyview", "White River", "Sabie"],
    "sabie":              ["Sabie", "Hazyview", "Graskop", "Pilgrim's Rest"],
}


def expand_location(location: str) -> list[str]:
    """
    Expand a small/low-density location into a list of nearby search areas.

    Returns the original location (always first) plus any configured nearby
    towns so that multi-query Apify calls cast a wider net while staying local.
    Falls back to [original] if no expansion is configured.

    All expansions are kept LOCAL (practical driving radius, ~30–60 km).
    Expansions are capped so total query count stays within limits.
    """
    raw = (location or "").strip()
    key = raw.lower().replace(",", " ").strip()

    # Check each known small-town key against the normalised input
    for town_key, nearby in _NEARBY.items():
        if town_key in key:
            return nearby   # first element is the canonical form of the town

    # No expansion configured → single-location search
    return [raw]


# ── Multi-query builder ────────────────────────────────────────────────────────

def build_queries(industry: str, location: str) -> list[str]:
    """
    Build 3 search variants per location — enough coverage without
    pushing Apify run-time into timeout territory.
    Passed together as searchStringsArray in a single call.
    """
    return [
        f"{industry} {location}",
        f"{industry} near {location}",
        f"best {industry} {location}",
    ]


# ── Deduplication ──────────────────────────────────────────────────────────────

def deduplicate(places: list[dict]) -> list[dict]:
    """
    Remove duplicates across multi-query results.
    Key = Google Maps place_id (most reliable).
    Fallback key = normalised name + address.
    Also removes entries with no name or name == "Unknown".
    """
    seen: set[str] = set()
    unique: list[dict] = []
    for p in places:
        name = (p.get("name") or "").strip()
        if not name or name == "Unknown":
            continue
        place_id = (p.get("place_id") or "").strip()
        if place_id:
            key = place_id
        else:
            addr = (p.get("address") or "").lower().strip()
            key = f"{name.lower()}|{addr}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


# ── Relevance confidence helper ───────────────────────────────────────────────

def _relevance_confidence(place: dict, keywords: list[str]) -> int:
    """
    Return a confidence score (0–3) for how well the place matches keywords.
    0 = no match at all → caller should reject.
    """
    name     = (place.get("name")     or "").lower()
    category = (place.get("category") or "").lower()
    score = 0
    if any(k in name     for k in keywords): score += 2   # name match = strong
    if any(k in category for k in keywords): score += 1   # category = weaker
    return score


def _get_matched_keywords(place: dict, keywords: list[str]) -> list[str]:
    """Return the subset of keywords that appear in name or category."""
    name     = (place.get("name")     or "").lower()
    category = (place.get("category") or "").lower()
    return [k for k in keywords if k in name or k in category]


def _lookup_keywords(industry: str) -> list[str] | None:
    """Return the keyword list for an industry, or None if not mapped."""
    ind = industry.lower().strip()
    for key, kws in INDUSTRY_KEYWORDS.items():
        if key in ind or ind in key:
            return kws
    return None


# ── Relevance filter ──────────────────────────────────────────────────────────

def is_relevant(place: dict, industry: str) -> bool:
    """
    Return True if the place is relevant to the searched industry.

    Order matters — REJECT first, then ACCEPT:
    1. BAD_KEYWORDS in name OR category  → False  (hard reject, checked first)
    2. No keyword map for industry        → True   (unknown industry, be permissive)
    3. confidence == 0                    → False  (keyword map exists, zero match)
    4. confidence > 0                     → True
    """
    name     = (place.get("name")     or "").lower()
    category = (place.get("category") or "").lower()

    # ── 1. Hard reject — BAD_KEYWORDS in name OR category ────────────────
    if any(bad in name     for bad in BAD_KEYWORDS): return False
    if any(bad in category for bad in BAD_KEYWORDS): return False

    # ── 2. Hard reject — B2B / non-consumer business types ───────────────
    if any(bad in name     for bad in BAD_BUSINESS_TYPES): return False
    if any(bad in category for bad in BAD_BUSINESS_TYPES): return False

    # ── Find keyword list for this industry ────────────────────────────────
    keywords = _lookup_keywords(industry)

    # ── 3. No keyword map → permissive ────────────────────────────────────
    if keywords is None:
        return True

    # ── 4 & 5. Confidence gate ─────────────────────────────────────────────
    return _relevance_confidence(place, keywords) > 0


# ── Relevance scoring (for ranking qualified leads before opportunity score) ──

def _relevance_score(place: dict, industry: str, location: str = "") -> int:
    """
    Rank qualified leads by business quality on a -5 … +6 scale.
    Higher = more established, better-rated, geographically proximate.

    NOTE: keyword match is intentionally NOT scored here — that is
    is_relevant()'s job. This function is purely about lead quality
    so the two concerns stay cleanly separated.

    Signals:
      Rating:   +2 (>=4.5), +1 (>=4.0)
      Reviews:  +2 (>=50),  +1 (>=20),  -2 (<5)
      Website:  -1 (has one — harder sell), +2 (none — prime target)
      Location: +1 (address contains search location token), -1 (does not)
    """
    score = 0
    address = (place.get("address") or "").lower()
    rating  = float(place.get("rating")      or 0)
    reviews = int(place.get("reviews_count") or 0)
    website = bool(place.get("website"))

    # ── Rating quality ─────────────────────────────────────────────────────
    if rating >= 4.5:
        score += 2
    elif rating >= 4.0:
        score += 1

    # ── Review count (establishment / trust signal) ────────────────────────
    if reviews >= 50:
        score += 2
    elif reviews >= 20:
        score += 1
    elif reviews < 5:
        score -= 2          # ghost / just-opened / closed — skip if possible

    # ── Website absence = OPPORTUNITY ─────────────────────────────────────
    # No website → strong lead (that's the whole product).
    # Has website → slight penalty (harder sell, but not disqualifying).
    if not website:
        score += 2
    else:
        score -= 1

    # ── Location proximity bias ────────────────────────────────────────────
    # +1 if any significant location token appears in the address,
    # -1 if a specific place was searched but doesn't show up at all.
    if location and address:
        loc_tokens = [
            t.strip().lower()
            for t in location.replace(",", " ").split()
            if len(t.strip()) > 3
        ]
        if loc_tokens:
            if any(tok in address for tok in loc_tokens):
                score += 1
            else:
                score -= 1

    return score


# ── Light filter (kept for backward compatibility) ────────────────────────────

def light_filter(results: list[dict]) -> list[dict]:
    """
    Legacy single-query dedup — kept so nothing breaks if called elsewhere.
    New code should use deduplicate() which handles multi-query merges.
    """
    seen_names: set[str] = set()
    out: list[dict] = []
    for r in results:
        name = (r.get("name") or "").strip()
        if not name or name == "Unknown":
            continue
        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        out.append(r)
    return out


# ── Location filter (kept for reference, no longer called) ────────────────────

def filter_by_location(results: list[dict], location: str) -> list[dict]:
    """
    DEPRECATED — no longer called. Kept for reference only.
    """
    return results


# ── Safe numeric helpers ──────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    """Parse a rating that may arrive as 4.8, '4.8', or '5/5'."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if "/" in s:
        parts = s.split("/")
        try:
            return float(parts[0])
        except ValueError:
            return default
    try:
        return float(s)
    except ValueError:
        return default


def _safe_int(val, default: int = 0) -> int:
    return int(_safe_float(val, default))


# ── Apify field normalizer ────────────────────────────────────────────────────

def _normalize(item: dict) -> dict:
    """Convert a raw Apify Google Maps item into a clean lead dict."""

    # Reviews
    reviews_raw = item.get("reviews", []) or []
    reviews: list[dict] = []
    for r in reviews_raw[:MAX_REVIEWS]:
        text = (r.get("text") or "").strip()
        if not text:
            continue
        reviews.append({
            "text":   text[:400],
            "author": (
                (r.get("name") or r.get("reviewerName") or "").strip()
                or "Verified Customer"
            ),
            "rating": _safe_int(r.get("stars") or r.get("rating"), default=5),
        })

    # Photos
    photos: list[str] = []
    for key in ("imageUrls", "images", "photos"):
        raw = item.get(key) or []
        if not isinstance(raw, list):
            continue
        for entry in raw:
            if isinstance(entry, str) and entry.startswith("http"):
                photos.append(entry)
            elif isinstance(entry, dict):
                img_url = entry.get("imageUrl") or entry.get("url") or ""
                if img_url.startswith("http"):
                    photos.append(img_url)
        if photos:
            break
    photos = photos[:MAX_IMAGES]

    # Coordinates
    location_data = item.get("location") or {}
    lat = str(location_data.get("lat") or item.get("lat") or "")
    lng = str(location_data.get("lng") or item.get("lng") or "")

    # Scalar fields — do NOT discard leads for missing optional fields
    name     = (item.get("title") or "Unknown").strip()
    rating   = _safe_float(item.get("totalScore") or item.get("stars"))
    rev_cnt  = _safe_int(item.get("reviewsCount") or item.get("reviews_count"))
    address  = (item.get("address") or "").strip()
    city     = (item.get("city") or "").strip()
    phone    = (item.get("phone") or item.get("phoneUnformatted") or "").strip()
    website  = (item.get("website") or "").strip()
    category = (item.get("categoryName") or item.get("category") or "").strip()
    maps_url = (item.get("url") or "").strip()
    place_id = (item.get("placeId") or "").strip()

    return {
        "name":               name,
        "city":               city,
        "address":            address,
        "phone":              phone,
        "website":            website,
        "rating":             rating,
        "reviews_count":      rev_cnt,
        "category":           category,
        "google_maps_url":    maps_url,
        "maps_url":           maps_url,
        "place_id":           place_id,
        "lat":                lat,
        "lng":                lng,
        "photos":             photos,
        "reviews":            reviews,
        "reviews_text":       [r["text"] for r in reviews],
        "has_whatsapp":       False,   # default; future upgrade improves detection
        "whatsapp_confidence": 0,
    }


# ── Region code helper ────────────────────────────────────────────────────────

def _guess_region_code(location: str) -> str:
    location_lower = location.lower()
    region_map = {
        "dubai": "ae", "uae": "ae", "abu dhabi": "ae", "sharjah": "ae",
        "london": "gb", "uk": "gb", "england": "gb",
        "new york": "us", "los angeles": "us", "chicago": "us",
        "usa": "us", "america": "us",
        "toronto": "ca", "canada": "ca",
        "sydney": "au", "melbourne": "au", "australia": "au",
        "singapore": "sg",
        "paris": "fr", "france": "fr",
        "berlin": "de", "germany": "de",
        "riyadh": "sa", "saudi": "sa",
        "doha": "qa", "qatar": "qa",
        "kuwait": "kw", "bahrain": "bh",
        "cairo": "eg", "egypt": "eg",
        "mumbai": "in", "delhi": "in", "india": "in",
    }
    for key, code in region_map.items():
        if key in location_lower:
            return code
    return ""


# ── Local mock (only when LOCAL_MODE=true) ────────────────────────────────────

def _mock_leads(industry: str, location: str) -> list[dict]:
    leads = []
    city = location.split(",")[0].strip()
    for i in range(15):
        leads.append({
            "name":               f"{industry.title()} {city.title()} #{i+1}",
            "city":               city,
            "address":            f"{i+1} Main Road, {location}",
            "phone":              f"03155500{str(i).zfill(2)}",
            "website":            "" if i % 2 == 0 else "https://example.com",
            "rating":             round(3.5 + (i % 4) * 0.3, 1),
            "reviews_count":      10 + i * 5,
            "category":           industry,
            "google_maps_url":    "",
            "maps_url":           "",
            "place_id":           f"mock-{i}",
            "lat":                "",
            "lng":                "",
            "photos":             [],
            "reviews":            [],
            "reviews_text":       [],
            "has_whatsapp":       i % 3 != 0,
            "whatsapp_confidence": 0 if i % 3 == 0 else 1,
        })
    return leads


# ── Outscraper normalizer ─────────────────────────────────────────────────────

def _normalize_outscraper(item: dict) -> dict:
    """
    Convert a raw Outscraper Google Maps item into the same clean lead dict
    format produced by _normalize() for Apify.  All downstream pipeline code
    (dedup, is_relevant, scoring, transformer, dashboard) stays untouched.
    """
    # Photos — Outscraper nests them under photos_data or as a flat list
    photos: list[str] = []
    for key in ("photos_data", "photos", "photo"):
        raw_photos = item.get(key) or []
        if not isinstance(raw_photos, list):
            continue
        for entry in raw_photos:
            if isinstance(entry, str) and entry.startswith("http"):
                photos.append(entry)
            elif isinstance(entry, dict):
                img_url = (
                    entry.get("photo_url")
                    or entry.get("url")
                    or entry.get("src")
                    or ""
                )
                if img_url.startswith("http"):
                    photos.append(img_url)
        if photos:
            break
    photos = photos[:MAX_IMAGES]

    # Reviews — Outscraper puts full review objects in reviews_data
    reviews: list[dict] = []
    for r in (item.get("reviews_data") or [])[:MAX_REVIEWS]:
        text = (r.get("review_text") or r.get("text") or "").strip()
        if not text:
            continue
        reviews.append({
            "text":   text[:400],
            "author": (
                r.get("author_title") or r.get("name") or "Verified Customer"
            ).strip(),
            "rating": _safe_int(
                r.get("review_rating") or r.get("stars") or r.get("rating"),
                default=5,
            ),
        })

    # Category — can be a string or list of subtypes
    category_raw = item.get("type") or item.get("subtypes") or item.get("category") or ""
    if isinstance(category_raw, list):
        category = ", ".join(str(c) for c in category_raw if c)
    else:
        category = str(category_raw).strip()

    name     = (item.get("name")     or "Unknown").strip()
    address  = (item.get("full_address") or item.get("address") or "").strip()
    city     = (item.get("city")     or "").strip()
    phone    = (item.get("phone")    or item.get("phone_international") or "").strip()
    website  = (item.get("site")     or item.get("website") or "").strip()
    rating   = _safe_float(item.get("rating") or item.get("stars"))
    rev_cnt  = _safe_int(item.get("reviews") or item.get("reviews_count"))
    maps_url = (item.get("url")      or item.get("google_maps_url") or "").strip()
    place_id = (item.get("place_id") or "").strip()
    lat      = str(item.get("latitude")  or item.get("lat") or "")
    lng      = str(item.get("longitude") or item.get("lng") or "")

    return {
        "name":               name,
        "city":               city,
        "address":            address,
        "phone":              phone,
        "website":            website,
        "rating":             rating,
        "reviews_count":      rev_cnt,
        "category":           category,
        "google_maps_url":    maps_url,
        "maps_url":           maps_url,
        "place_id":           place_id,
        "lat":                lat,
        "lng":                lng,
        "photos":             photos,
        "reviews":            reviews,
        "reviews_text":       [r["text"] for r in reviews],
        "has_whatsapp":       False,
        "whatsapp_confidence": 0,
    }


# ── Outscraper polling (handles async task responses) ─────────────────────────

def _outscraper_poll(task_id: str, api_key: str, max_wait: int = 240) -> dict:
    """
    Poll Outscraper for a pending task until status == success/failed or
    max_wait seconds elapse.  Backs off gradually (5s → 10s → 20s → 30s).
    """
    url     = f"https://api.app.outscraper.com/requests/{task_id}"
    headers = {"X-API-KEY": api_key}
    deadline = time.time() + max_wait
    interval = 5.0

    print(f"[Search] Outscraper async task {task_id} — polling (max {max_wait}s)...")
    while time.time() < deadline:
        time.sleep(interval)
        try:
            resp = requests.get(url, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            print(f"[Search] Poll error: {e} — retrying")
            continue

        if resp.status_code != 200:
            print(f"[Search] Poll HTTP {resp.status_code} — retrying")
            continue

        data   = resp.json()
        status = (data.get("status") or "").lower()
        print(f"[Search] Outscraper status: {status}")

        if status in ("success", "completed", "done"):
            return data
        if status in ("failed", "error"):
            raise Exception(f"Outscraper task {task_id} failed: {data}")

        interval = min(interval * 1.5, 30.0)     # back off, cap at 30s

    raise Exception(
        f"Outscraper task {task_id} did not complete within {max_wait}s."
    )


# ── Outscraper HTTP call ───────────────────────────────────────────────────────

def _outscraper_fetch(queries: list[str], location: str) -> list[dict]:
    """
    Execute a Google Maps search via Outscraper.
    Accepts the same query list built by build_queries() so location expansion
    continues to work unchanged.  Returns raw Outscraper items (un-normalised).

    Handles both synchronous (immediate data) and asynchronous (task-ID)
    responses automatically.
    """
    api_key = os.getenv("OUTSCRAPER_API_KEY")
    if not api_key:
        raise Exception(
            "OUTSCRAPER_API_KEY not set — cannot run live search. "
            "Add it to your .env or Render environment variables."
        )

    # Pass query list directly; Outscraper accepts arrays in `query`.
    # radius=50000 (50 km) gives geographic proximity even when individual
    # query strings omit the city name.
    payload = {
        "query":    queries,      # list of search strings from build_queries()
        "limit":    20,           # max results per query string
        "language": "en",
        "region":   _guess_region_code(location) or "ZA",
    }

    headers = {
        "X-API-KEY":    api_key,
        "Content-Type": "application/json",
    }

    print(f"[Search] POST https://api.app.outscraper.com/maps/search-v3")
    print(f"[Search] Waiting for Outscraper ({len(queries)} queries, limit 20 each)...")

    t0 = time.time()
    try:
        resp = requests.post(
            "https://api.app.outscraper.com/maps/search-v3",
            json=payload,
            headers=headers,
            timeout=SYNC_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise Exception(f"Outscraper timed out after {SYNC_TIMEOUT}s.")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Outscraper HTTP error: {e}")

    print(f"[Search] Outscraper HTTP {resp.status_code}  ({time.time() - t0:.1f}s)")

    if resp.status_code not in (200, 201, 202):
        raise Exception(
            f"Outscraper returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()

    # Async path: Outscraper returned a task ID instead of immediate results
    task_id = data.get("id")
    status  = (data.get("status") or "").lower()
    if task_id and status in ("pending", "running", "in_progress", ""):
        data = _outscraper_poll(task_id, api_key)

    print(f"[Search] Outscraper completed in {time.time() - t0:.1f}s")

    # Flatten: results may be a list-of-lists (one list per query string)
    # or a flat list — handle both.
    raw = data.get("data", [])
    if raw and isinstance(raw[0], list):
        flat: list[dict] = []
        for group in raw:
            flat.extend(group)
        raw = flat

    if not raw:
        raise Exception(
            f"Outscraper returned no data for queries {queries}. "
            "Check your API key, quota, and search terms."
        )

    return raw


# ── Apify HTTP call (kept for reference / fallback — not called by default) ───

def _apify_fetch(queries: list[str], location: str) -> list[dict]:
    """
    Execute one Apify run with all search strings in searchStringsArray.
    Apify processes them in parallel — same cost/time as a single query
    but returns results from every variant.
    Returns raw Apify items (un-normalised).
    Raises on API/network errors.
    """
    if not APIFY_API_TOKEN:
        raise Exception(
            "APIFY_API_TOKEN not set — cannot run live search. "
            "Add it to your .env or Render environment variables."
        )

    region_code  = _guess_region_code(location)
    actor_api_id = APIFY_ACTOR_ID.replace("/", "~")
    url = (
        f"https://api.apify.com/v2/acts/{actor_api_id}"
        f"/run-sync-get-dataset-items"
    )
    payload = {
        "searchStringsArray":        queries,
        "locationQuery":             location,
        "maxCrawledPlacesPerSearch": 20,        # 20 per query string keeps runs fast
        "maxReviews":                MAX_REVIEWS,
        "maxImages":                 MAX_IMAGES,
        "language":                  "en",
        "countryCode":               (region_code or "za").lower(),
    }

    print(f"[Search] POST {url}")
    print(f"[Search] Waiting for Apify ({len(queries)} queries, max 20 places each)...")

    t0 = time.time()
    try:
        resp = requests.post(
            url,
            json=payload,
            params={"token": APIFY_API_TOKEN},
            timeout=SYNC_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise Exception(f"Fetcher failed: Apify timed out after {SYNC_TIMEOUT}s.")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Fetcher failed: HTTP error calling Apify: {e}")

    print(f"[Search] Apify completed in {time.time() - t0:.1f}s  (HTTP {resp.status_code})")

    if resp.status_code not in (200, 201):
        raise Exception(
            f"Fetcher failed: Apify returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    try:
        items = resp.json()
    except Exception as e:
        raise Exception(f"Fetcher failed: Could not parse Apify JSON: {e}")

    if not items or not isinstance(items, list):
        raise Exception(
            f"Fetcher failed: Apify returned no data for queries {queries}. "
            "Check actor ID, API token, and search terms."
        )

    return items


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_leads(industry: str, location: str) -> list[dict]:
    """
    Full qualification pipeline:

    1. Build multi-variant search queries
    2. Single Apify call with all queries in searchStringsArray
    3. Normalise + deduplicate (by place_id or name+address)
    4. Relevance filter (reject hospitals, farms, wrong categories, etc.)
    5. Rank by relevance score; cap at MAX_PLACES
    6. Return clean, qualified leads ready for opportunity scoring

    LOCAL_MODE=true  → returns mock data (offline/CI only)
    LOCAL_MODE=false → live Apify (default)
    """

    # ── LOCAL MODE ──────────────────────────────────────────────────────────
    if LOCAL_MODE:
        print("[Search] LOCAL MODE ACTIVE — returning mock data")
        leads = _mock_leads(industry, location)
        _last_fetch_stats["raw"]      = len(leads)
        _last_fetch_stats["filtered"] = len(leads)
        print(f"[Search] Retrieved {len(leads)} leads (mock)")
        return leads

    # ── STEP 1: Expand location + build queries ─────────────────────────────
    locations = expand_location(location)
    queries: list[str] = []
    for loc in locations:
        queries.extend(build_queries(industry, loc))
    # Deduplicate while preserving order (set() would scramble)
    seen_q: set[str] = set()
    queries = [q for q in queries if not (q in seen_q or seen_q.add(q))]  # type: ignore[func-returns-value]

    _pipeline_start = time.time()
    print(f"\n[Search] ── Qualification pipeline ──")
    print(f"[Search] Expanded locations: {locations}")
    print(f"[Search] Total queries:      {len(queries)}")
    print(f"[Search] Queries: {queries}")

    # ── STEP 2: Fetch all queries via Outscraper ────────────────────────────
    # Timeout fallback: if the full set times out, retry with the first 8
    # queries (covers the primary location) so users always get some results.
    FALLBACK_QUERY_LIMIT = 8
    try:
        raw_items = _outscraper_fetch(queries, location)
    except Exception as e:
        if "timed out" in str(e).lower() and len(queries) > FALLBACK_QUERY_LIMIT:
            trimmed = queries[:FALLBACK_QUERY_LIMIT]
            print(f"[Search] ⚠  Timeout — retrying with {len(trimmed)} queries (trimmed from {len(queries)})")
            raw_items = _outscraper_fetch(trimmed, location)
        else:
            raise
    print(f"[Search] Total fetched:    {len(raw_items)}")

    # ── STEP 3: Normalise + Deduplicate ────────────────────────────────────
    # _normalize_outscraper maps Outscraper fields → the same dict shape that
    # _normalize() produced for Apify.  All downstream code is unchanged.
    normalised = [
        _normalize_outscraper(item)
        for item in raw_items
        if item.get("name")     # Outscraper uses "name", Apify used "title"
    ]
    unique = deduplicate(normalised)
    print(f"[Search] After dedupe:     {len(unique)}")

    # ── STEP 4: Relevance filter ────────────────────────────────────────────
    filtered = [p for p in unique if is_relevant(p, industry)]
    print(f"[Search] After filter:     {len(filtered)}")

    # Fallback: relevance filter too aggressive → use top-rated deduped results
    # Require rating >= 4.0 to avoid ghost/closed businesses in fallback.
    if len(filtered) < 5:
        fallback_pool = [p for p in unique if float(p.get("rating") or 0) >= 4.0]
        fallback_n    = min(15, len(fallback_pool))
        print(f"[Search] ⚠  Relevance filter < 5 — fallback: top {fallback_n} rated >=4.0")
        filtered = sorted(fallback_pool, key=lambda x: float(x.get("rating") or 0), reverse=True)[:fallback_n]
        if not filtered:
            # Last resort: no rating gate if pool is completely empty
            print("[Search] ⚠  No rated fallback found — using all deduped results")
            filtered = sorted(unique, key=lambda x: float(x.get("rating") or 0), reverse=True)[:15]

    # ── STEP 5: Score + debug field ────────────────────────────────────────
    keywords = _lookup_keywords(industry)
    for p in filtered:
        qs    = _relevance_score(p, industry, location)
        conf  = _relevance_confidence(p, keywords) if keywords else 0
        matched = _get_matched_keywords(p, keywords) if keywords else []
        p["_relevance"] = qs
        p["_debug"] = {
            "confidence":       conf,
            "quality_score":    qs,
            "matched_keywords": matched,
        }

    # ── STEP 6: Hard quality cutoff — discard weak leads ──────────────────
    # Minimum quality score of 2 keeps legit businesses that just lack a website
    # (our primary target!) while still cutting ghosts / unrated / off-location.
    # e.g. rating 4.3 + 18 reviews + no website → score 1+0+2 = 3 → passes.
    QUALITY_CUTOFF = 2
    before_cutoff = len(filtered)
    filtered = [p for p in filtered if p.get("_relevance", 0) >= QUALITY_CUTOFF]
    print(f"[Search] After cutoff ≥{QUALITY_CUTOFF}: {len(filtered)}  (dropped {before_cutoff - len(filtered)})")

    # Safety net: if cutoff drops everything, keep the top 5 scored regardless
    if not filtered and before_cutoff > 0:
        all_scored = sorted(
            [p for p in unique],
            key=lambda x: x.get("_relevance", _relevance_score(x, industry, location)),
            reverse=True,
        )
        filtered = all_scored[:5]
        print(f"[Search] ⚠  Cutoff wiped all leads — keeping top 5 as safety net")

    filtered.sort(key=lambda x: x.get("_relevance", 0), reverse=True)

    top_leads = filtered[:MAX_PLACES]
    print(f"[Search] Final returned:   {len(top_leads)}")
    print(f"[Search] Pipeline total:   {time.time() - _pipeline_start:.1f}s")

    # ── Update side-channel stats for pipeline.py ──────────────────────────
    _last_fetch_stats["raw"]               = len(normalised)
    _last_fetch_stats["filtered"]          = len(top_leads)
    _last_fetch_stats["expanded_locations"] = locations
    _last_fetch_stats["expanded"]          = len(locations) > 1

    # Cache normalised (pre-dedup) results for transformer enrichment
    cache_key = f"{industry} in {location}"
    _save_cache(cache_key, normalised)

    return top_leads
