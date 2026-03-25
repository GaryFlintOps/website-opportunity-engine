import os
import csv
import json
import re
import unicodedata
from datetime import datetime
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
    leads, industry, location = load_latest_leads()
    for lead in leads:
        if lead.get("slug") == slug:
            return lead, industry, location
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
        "slug":          slug,
        "state":         existing.get("state", "generated"),
        "generated_at":  datetime.now().isoformat(),
        "approved_at":   existing.get("approved_at", ""),
        "business_data": business_data,
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
