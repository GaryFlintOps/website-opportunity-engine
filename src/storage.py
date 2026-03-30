import os
import csv
import json
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from src.config import OUTPUT_DIR, DEMOS_DIR

DEMO_STATES = ("not_generated", "generated", "approved", "sent")


# ── Utilities ─────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """
    Convert a business name to a URL-safe ASCII slug.
    Accented characters are transliterated (é→e, ô→o, etc.) so slugs are
    consistent across platforms and safe to use in file names and URLs.
    """
    # Decompose unicode → transliterate to closest ASCII equivalent
    slug = unicodedata.normalize("NFKD", name.lower())
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


# ── Lead storage ──────────────────────────────────────────────────────────────

def save_leads(leads: list[dict], industry: str, location: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(OUTPUT_DIR, f"{slugify(industry)}-{slugify(location)}_{timestamp}.csv")
    if not leads:
        return filepath
    fieldnames = ["name", "slug", "city", "rating", "reviews_count",
                  "website", "phone", "address", "category", "score", "google_maps_url"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow({k: lead.get(k, "") for k in fieldnames})
    return filepath


def save_leads_json(
    leads: list[dict],
    industry: str,
    location: str,
    filter_stats: dict | None = None,
) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, "latest.json")
    payload: dict = {
        "industry":     industry,
        "location":     location,
        "timestamp":    datetime.now().isoformat(),
        "leads":        leads,
    }
    if filter_stats:
        payload["filter_stats"] = filter_stats
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filepath


def load_latest_leads() -> tuple[list[dict], str, str]:
    filepath = os.path.join(OUTPUT_DIR, "latest.json")
    if not os.path.exists(filepath):
        return [], "", ""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("leads", []), data.get("industry", ""), data.get("location", "")


def load_latest_filter_stats() -> dict:
    """Return the raw-vs-filtered stats from the most recent pipeline run, or {}."""
    filepath = os.path.join(OUTPUT_DIR, "latest.json")
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("filter_stats", {})


def get_lead_by_slug(slug: str) -> tuple[dict | None, str, str]:
    # Primary: look in the latest pipeline run
    leads, industry, location = load_latest_leads()
    for lead in leads:
        if lead.get("slug") == slug:
            return lead, industry, location

    # Fallback: reconstruct lead from the demo JSON if one exists
    raw = _load_raw(slug)
    if raw is not None:
        bd = raw.get("business_data") or {}
        # Build a lead-compatible dict from business_data fields
        lead = {
            "name":               bd.get("name", slug),
            "slug":               slug,
            "city":               bd.get("city", ""),
            "address":            bd.get("address", ""),
            "phone":              bd.get("phone", ""),
            "website":            bd.get("website", ""),
            "rating":             bd.get("rating", 0),
            "reviews_count":      bd.get("reviews_count", 0),
            "category":           bd.get("category", ""),
            "google_maps_url":    bd.get("google_maps_url", ""),
            "maps_url":           bd.get("google_maps_url", ""),
            "place_id":           bd.get("place_id", ""),
            "lat":                bd.get("lat", ""),
            "lng":                bd.get("lng", ""),
            "photos":             bd.get("gallery_images", bd.get("photos", [])),
            "reviews":            bd.get("reviews", []),
            "reviews_text":       [r.get("text", "") for r in bd.get("reviews", [])],
            "has_whatsapp":       bd.get("has_whatsapp", False),
            "whatsapp_confidence": bd.get("whatsapp_confidence", 0),
            "score":              bd.get("opportunity_score", 0),
        }
        ind = bd.get("category", "")
        loc = bd.get("city", "")
        return lead, ind, loc

    return None, "", ""


# ── Demo storage ──────────────────────────────────────────────────────────────

def _demo_path(slug: str) -> str:
    os.makedirs(DEMOS_DIR, exist_ok=True)
    return os.path.join(DEMOS_DIR, f"{slug}.json")


def save_demo(slug: str, business_data: dict) -> str:
    """
    Persist BusinessData + state to data/demos/{slug}.json.
    HTML rendering is handled by the /demo/{slug} route on this server.
    Preserves existing state + approved_at on rebuild.
    """
    path     = _demo_path(slug)
    existing = _load_raw(slug) or {}

    payload = {
        "slug":             slug,
        "state":            existing.get("state", "generated"),
        "generated_at":     datetime.now().isoformat(),
        "approved_at":      existing.get("approved_at", ""),
        # Preserve share token across regeneration
        "demo_token":       existing.get("demo_token", ""),
        "demo_expires_at":  existing.get("demo_expires_at", ""),
        "business_data":    business_data,
    }
    print(f"[STORAGE] Saving demo to: {path}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _load_raw(slug: str) -> dict | None:
    path = _demo_path(slug)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_demo_data(slug: str) -> dict | None:
    """Return the BusinessData dict for a demo, or None if not found."""
    raw = _load_raw(slug)
    if raw is None:
        return None
    return raw.get("business_data")


def load_demo_meta(slug: str) -> dict | None:
    """Return demo metadata (slug, state, timestamps) without business_data blob."""
    raw = _load_raw(slug)
    if raw is None:
        return None
    return {k: v for k, v in raw.items() if k != "business_data"}


def get_demo_state(slug: str) -> str:
    raw = _load_raw(slug)
    if raw is None:
        return "not_generated"
    return raw.get("state", "generated")


def set_demo_state(slug: str, state: str) -> bool:
    if state not in DEMO_STATES:
        raise ValueError(f"Invalid state '{state}'. Must be one of {DEMO_STATES}")
    raw = _load_raw(slug)
    if raw is None:
        return False
    raw["state"] = state
    if state == "approved" and not raw.get("approved_at"):
        raw["approved_at"] = datetime.now().isoformat()
    path = _demo_path(slug)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    return True


def demo_exists(slug: str) -> bool:
    return os.path.exists(_demo_path(slug))


def get_all_demo_states(slugs: list[str]) -> dict[str, str]:
    return {slug: get_demo_state(slug) for slug in slugs}


def ensure_demo_token(slug: str) -> str:
    """
    Generate and persist a share token for this demo if one doesn't exist yet.
    Tokens are 32 hex characters (128-bit entropy) and expire in 365 days.
    Returns the (existing or newly created) token, or '' if the demo doesn't exist.
    """
    raw = _load_raw(slug)
    if raw is None:
        return ""
    token = raw.get("demo_token") or ""
    if not token:
        token = secrets.token_hex(16)
        expires = (datetime.now() + timedelta(days=365)).isoformat()
        raw["demo_token"] = token
        raw["demo_expires_at"] = expires
        with open(_demo_path(slug), "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    return token


def get_demo_token(slug: str) -> str | None:
    """Return the share token for a demo, or None if not generated yet."""
    raw = _load_raw(slug)
    if raw is None:
        return None
    return raw.get("demo_token") or None


def validate_demo_token(slug: str, token: str) -> bool:
    """
    Return True if the supplied token matches the stored token and hasn't expired.
    Always returns True if no token is stored (backwards-compat for demos generated
    before token support was added — call ensure_demo_token() to fix them).
    """
    raw = _load_raw(slug)
    if raw is None:
        return False
    stored = raw.get("demo_token") or ""
    if not stored:
        # Pre-token demo: accept any access (no token was ever issued)
        return True
    if stored != token:
        return False
    expires_str = raw.get("demo_expires_at") or ""
    if expires_str:
        try:
            expires = datetime.fromisoformat(expires_str)
            if datetime.now() > expires:
                return False
        except ValueError:
            pass  # malformed date — treat as not expired
    return True
