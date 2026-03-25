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


# ── Location filter ───────────────────────────────────────────────────────────

def filter_by_location(results: list[dict], location: str) -> list[dict]:
    """
    Keep only results whose address or city contains the primary location name.
    Uses SA postcode ranges to disambiguate provinces when a qualifier is given
    (e.g. 'Hilton, KwaZulu-Natal' vs Hilton suburb in Bloemfontein).
    """
    parts     = [p.strip().lower() for p in location.split(",")]
    primary   = parts[0]
    qualifier = parts[1] if len(parts) > 1 else ""

    PROVINCE_POSTCODES = {
        "kwazulu-natal": (3000, 4999), "kwazulu natal": (3000, 4999), "kzn": (3000, 4999),
        "western cape":  (7000, 8299),
        "eastern cape":  (5000, 6999),
        "gauteng":       (1, 1999),
        "free state":    (9000, 9999),
        "northern cape": (8300, 8999),
        "limpopo":       (700, 999),
        "mpumalanga":    (1200, 1399),
        "north west":    (2500, 2999),
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

        if primary not in address and primary not in city:
            continue

        if postcode_range:
            codes = re.findall(r"\b(\d{4})\b", address)
            if codes:
                code = int(codes[0])
                lo, hi = postcode_range
                if not (lo <= code <= hi):
                    continue

        filtered.append(r)

    return filtered


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
            "rating": int(r.get("stars") or r.get("rating") or 5),
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


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_leads(industry: str, location: str) -> list[dict]:
    """
    Fetch leads for (industry, location).

    LOCAL_MODE=true  → returns mock data (offline/CI use only)
    LOCAL_MODE=false → calls Apify Google Maps actor (default)

    Raises on API key missing or Apify failure. Never returns empty silently.
    """

    # ── LOCAL MODE (explicit opt-in only) ──────────────────────────────────
    if LOCAL_MODE:
        print("[Fetcher] LOCAL MODE ACTIVE — returning mock data")
        leads = _mock_leads(industry, location)
        _last_fetch_stats["raw"]      = len(leads)
        _last_fetch_stats["filtered"] = len(leads)
        print(f"[Fetcher] Retrieved {len(leads)} leads (mock)")
        return leads

    # ── LIVE APIFY MODE ────────────────────────────────────────────────────
    if not APIFY_API_TOKEN:
        raise Exception(
            "APIFY_API_TOKEN not set — cannot run live search. "
            "Add it to your .env or Render environment variables."
        )

    search_query = f"{industry} in {location}"
    region_code  = _guess_region_code(location)

    print(f"[Fetcher] Running Apify actor (LIVE MODE)")
    print(f"[Fetcher] Query: '{search_query}'  |  Actor: {APIFY_ACTOR_ID}")

    # ── Cache check ────────────────────────────────────────────────────────
    cached = _load_cache(search_query)
    if cached is not None:
        filtered = filter_by_location(cached, location)
        _last_fetch_stats["raw"]      = len(cached)
        _last_fetch_stats["filtered"] = len(filtered)
        print(f"[Fetcher] Retrieved {len(filtered)} leads from cache (raw: {len(cached)})")
        if not filtered:
            raise Exception(
                f"Cache returned {len(cached)} raw results but 0 passed "
                f"location filter for '{location}'. Clear cache or broaden the query."
            )
        return filtered

    # ── Live Apify call ────────────────────────────────────────────────────
    actor_api_id = APIFY_ACTOR_ID.replace("/", "~")
    url = (
        f"https://api.apify.com/v2/acts/{actor_api_id}"
        f"/run-sync-get-dataset-items"
    )
    payload = {
        "searchStringsArray":        [f"{industry} in {location}"],
        "locationQuery":             location,
        "maxCrawledPlacesPerSearch": MAX_PLACES,
        "maxReviews":                MAX_REVIEWS,
        "maxImages":                 MAX_IMAGES,
        "language":                  "en",
        "countryCode":               (region_code or "za").lower(),
    }

    print(f"[Fetcher] POST {url}")
    print(f"[Fetcher] Waiting for Apify to complete (timeout: {SYNC_TIMEOUT}s)...")

    try:
        resp = requests.post(
            url,
            json=payload,
            params={"token": APIFY_API_TOKEN},
            timeout=SYNC_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise Exception(
            f"Fetcher failed: Apify request timed out after {SYNC_TIMEOUT}s."
        )
    except requests.exceptions.RequestException as e:
        raise Exception(f"Fetcher failed: HTTP error calling Apify: {e}")

    print(f"[Fetcher] Apify response status: {resp.status_code}")

    if resp.status_code not in (200, 201):
        raise Exception(
            f"Fetcher failed: Apify returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    try:
        items = resp.json()
    except Exception as e:
        raise Exception(f"Fetcher failed: Could not parse Apify JSON response: {e}")

    if not items or not isinstance(items, list):
        raise Exception(
            f"Fetcher failed: Apify returned no data for query '{search_query}'. "
            "Check actor ID, API token, and search terms."
        )

    print(f"[Fetcher] Retrieved {len(items)} raw items from Apify")

    leads = [
        _normalize(item)
        for item in items[:MAX_PLACES]
        if item.get("title")
    ]

    # Location filter
    filtered = filter_by_location(leads, location)
    _last_fetch_stats["raw"]      = len(leads)
    _last_fetch_stats["filtered"] = len(filtered)

    print(f"[Fetcher] Retrieved {len(filtered)} leads from Apify (raw: {len(leads)}, after location filter: {len(filtered)})")

    # Cache raw leads (re-filter applied on cache hit too)
    _save_cache(search_query, leads)

    if not filtered:
        raise Exception(
            f"Fetcher failed: Apify returned {len(leads)} results but 0 matched "
            f"location filter for '{location}'. Try a broader location string."
        )

    return filtered
