import os
import json
import re
import unicodedata
import requests
from src.config import APIFY_API_TOKEN, APIFY_ACTOR_ID, CACHE_DIR

# ── Limits ────────────────────────────────────────────────────────────────────
MAX_PLACES  = 30   # max leads returned per search
MAX_REVIEWS = 5    # reviews kept per place
MAX_IMAGES  = 6    # images kept per place

SYNC_TIMEOUT = 300   # seconds

# Populated after every fetch so pipeline.py can persist the stats
_last_fetch_stats: dict = {}


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _query_slug(query: str) -> str:
    # Transliterate accented chars to ASCII before slugifying
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
            print(f"[Fetcher] Cache hit: {path}")
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


# ── Main fetcher ──────────────────────────────────────────────────────────────

def filter_by_location(results: list[dict], location: str) -> list[dict]:
    """
    Hard filter: keep only results whose address or city contains the primary
    location name, with postcode-range disambiguation when a province qualifier
    is provided (e.g. 'Hilton, KwaZulu-Natal' vs. Hilton suburb in Bloemfontein).

    SA postcode ranges (approximate):
      KwaZulu-Natal  : 3000–4999
      Western Cape   : 7000–8299
      Eastern Cape   : 5000–6999
      Gauteng        : 0001–1999 / 2000
      Free State / Northern Cape : 8300–9999
    """
    parts = [p.strip().lower() for p in location.split(",")]
    primary   = parts[0]
    qualifier = parts[1] if len(parts) > 1 else ""

    # Map qualifier keywords → valid postcode ranges
    PROVINCE_POSTCODES = {
        "kwazulu-natal":  (3000, 4999),
        "kwazulu natal":  (3000, 4999),
        "kzn":            (3000, 4999),
        "western cape":   (7000, 8299),
        "eastern cape":   (5000, 6999),
        "gauteng":        (1, 1999),
        "free state":     (9000, 9999),
        "northern cape":  (8300, 8999),
        "limpopo":        (700, 999),
        "mpumalanga":     (1200, 1399),
        "north west":     (2500, 2999),
    }

    postcode_range = None
    for kw, rng in PROVINCE_POSTCODES.items():
        if kw in qualifier:
            postcode_range = rng
            break

    filtered = []
    for r in results:
        address = (r.get("address") or "").lower()
        city    = (r.get("city")    or "").lower()

        # Must contain the primary location token
        if primary not in address and primary not in city:
            continue

        # If we have a province qualifier, validate by postcode range
        if postcode_range:
            codes = re.findall(r"\b(\d{4})\b", address)
            if codes:
                code = int(codes[0])
                lo, hi = postcode_range
                if not (lo <= code <= hi):
                    continue   # postcode is in a different province — skip

        filtered.append(r)

    return filtered


def fetch_leads(industry: str, location: str) -> list[dict]:
    """
    Fetch leads from Apify Google Maps scraper using the synchronous endpoint.
    Checks cache first — skips Apify call if cached results exist.

    Returns a list of normalised lead dicts capped at MAX_PLACES.
    Raises immediately on any HTTP error or empty result set.
    """
    global _last_fetch_stats   # populated at end of both code paths

    # APIFY_API_TOKEN is validated at import time in config.py

    # Build a precise localised search string
    search_query = f"{industry} in {location}"
    region_code  = _guess_region_code(location)
    print(f"[Fetcher] Final query: {search_query}")

    # ── Cache check ────────────────────────────────────────────────────────
    cached = _load_cache(search_query)
    if cached is not None:
        print(f"[Fetcher] Cache hit — applying location filter before returning")
        filtered = filter_by_location(cached, location)
        print(f"[Fetcher] RAW RESULTS (cached): {len(cached)}")
        print(f"[Fetcher] FILTERED RESULTS    : {len(filtered)}")
        print(f"[Fetcher] First 3 addresses   : {[r.get('address','') for r in filtered[:3]]}")
        _last_fetch_stats = {"raw": len(cached), "filtered": len(filtered), "source": "cache"}
        return filtered

    # ── Live Apify call ────────────────────────────────────────────────────
    # Apify REST API requires "~" as the owner/name separator (not "/")
    actor_api_id = APIFY_ACTOR_ID.replace("/", "~")
    url = f"https://api.apify.com/v2/acts/{actor_api_id}/run-sync-get-dataset-items"
    params = {"token": APIFY_API_TOKEN}

    payload = {
        "searchStringsArray":        [f"{industry} in {location}"],
        "locationQuery":             location,
        "maxCrawledPlacesPerSearch": MAX_PLACES,
        "maxReviews":                MAX_REVIEWS,
        "maxImages":                 MAX_IMAGES,
        "language":                  "en",
        "countryCode":               (region_code or "za").lower(),
    }

    print(f"[Fetcher] Using actor : {APIFY_ACTOR_ID}")
    print(f"[Fetcher] API Actor ID: {actor_api_id}")
    print(f"[Fetcher] Endpoint    : POST {url}")
    print(f"[Fetcher] Query       : '{search_query}'")
    print(f"[Fetcher] locationQuery: '{location}'")
    print(f"[Fetcher] Waiting for Apify to complete (up to {SYNC_TIMEOUT}s)...")

    resp = requests.post(url, json=payload, params=params, timeout=SYNC_TIMEOUT)

    print(f"[Fetcher] Status: {resp.status_code}")
    if resp.status_code not in (200, 201):
        print(resp.text[:500])
        raise Exception(
            f"Apify returned unexpected response "
            f"(HTTP {resp.status_code}: {resp.text[:200]})"
        )

    items = resp.json()

    if not items or not isinstance(items, list):
        raise Exception(f"No data returned for query: {search_query}")

    print(f"[Fetcher] Raw items received: {len(items)}")

    leads = [
        _normalize(item)
        for item in items[:MAX_PLACES]
        if item.get("title")
    ]

    # ── Hard location filter (BEFORE scoring / returning) ──────────────────
    filtered = filter_by_location(leads, location)
    print(f"[Fetcher] RAW RESULTS     : {len(leads)}")
    print(f"[Fetcher] FILTERED RESULTS: {len(filtered)}")
    print(f"[Fetcher] First 3 addresses: {[r.get('address','') for r in filtered[:3]]}")

    _last_fetch_stats = {"raw": len(leads), "filtered": len(filtered), "source": "live"}

    # ── Save to cache (raw leads — filter is re-applied on cache hit too) ──
    _save_cache(search_query, leads)

    return filtered


# ── Normalizer ────────────────────────────────────────────────────────────────

def _normalize(item: dict) -> dict:
    """
    Convert a raw Apify Google Maps item into a clean lead dict.
    All field access is safe — missing keys fall back to empty/zero values.
    """
    # ── Reviews ────────────────────────────────────────────────────────────
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
            "rating": int(r.get("stars") or r.get("rating") or 5),
        })

    # ── Photos ─────────────────────────────────────────────────────────────
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

    # ── Coordinates ────────────────────────────────────────────────────────
    location_data = item.get("location") or {}
    lat = str(location_data.get("lat") or item.get("lat") or "")
    lng = str(location_data.get("lng") or item.get("lng") or "")

    # ── Safe scalar fields ─────────────────────────────────────────────────
    name     = (item.get("title") or "Unknown").strip()
    rating   = float(item.get("totalScore") or item.get("stars") or 0)
    rev_cnt  = int(item.get("reviewsCount") or item.get("reviews_count") or 0)
    address  = (item.get("address") or "").strip()
    city     = (item.get("city") or "").strip()
    phone    = (item.get("phone") or item.get("phoneUnformatted") or "").strip()
    website  = (item.get("website") or "").strip()
    category = (item.get("categoryName") or item.get("category") or "").strip()
    maps_url = (item.get("url") or "").strip()
    place_id = (item.get("placeId") or "").strip()

    return {
        "name":            name,
        "city":            city,
        "address":         address,
        "phone":           phone,
        "website":         website,
        "rating":          rating,
        "reviews_count":   rev_cnt,
        "category":        category,
        "google_maps_url": maps_url,
        "maps_url":        maps_url,
        "place_id":        place_id,
        "lat":             lat,
        "lng":             lng,
        "photos":          photos,
        "reviews":         reviews,
        "reviews_text":    [r["text"] for r in reviews],
    }


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
        "kuwait": "kw",
        "bahrain": "bh",
        "cairo": "eg", "egypt": "eg",
        "mumbai": "in", "delhi": "in", "india": "in",
    }
    for key, code in region_map.items():
        if key in location_lower:
            return code
    return ""
