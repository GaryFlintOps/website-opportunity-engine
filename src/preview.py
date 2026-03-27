"""
preview.py

Data helpers only.
Demo HTML rendering is handled directly by the /demo/{slug} route in dashboard.py.

Exports:
  get_tagline(industry)               → str
  get_services(industry)              → list[str]
  detect_image_brightness(url)        → "light" | "dark" | "unknown"
  enforce_image_consistency(urls)     → list[str]
"""

from src.config import TAGLINES, DEFAULT_TAGLINE


# ── Taglines ──────────────────────────────────────────────────────────────────

def get_tagline(industry: str) -> str:
    for key, tagline in TAGLINES.items():
        if key in industry.lower():
            return tagline
    return DEFAULT_TAGLINE


# ── Services ──────────────────────────────────────────────────────────────────

INDUSTRY_SERVICES: dict[str, list[str]] = {
    "coffee":      ["Espresso & Pour Over", "Cold Brew & Iced Drinks", "Pastries & Light Bites", "Private Events"],
    "cafe":        ["Specialty Coffee", "Fresh Pastries", "Light Lunch Menu", "Takeaway & Delivery"],
    "bike":        ["Bike sales", "Servicing", "Repairs", "Accessories"],
    "bicycle":     ["Bike sales", "Servicing", "Repairs", "Accessories"],
    "cycle":       ["Bike sales", "Servicing", "Repairs", "Accessories"],
    "charcuterie": ["Artisan cheeses", "Baked goods", "Coffee", "Freshly squeezed juices"],
    "salon":       ["Haircut & Styling", "Colour & Highlights", "Keratin Treatments", "Bridal Packages"],
    "barbershop":  ["Classic Haircuts", "Beard Trimming & Shaping", "Hot Towel Shave", "Kids Cuts"],
    "barber":      ["Classic Haircuts", "Beard Trimming & Shaping", "Hot Towel Shave", "Kids Cuts"],
    "restaurant":  ["Dine-In Experience", "Takeaway & Delivery", "Private Dining", "Catering Services"],
    "gym":         ["Personal Training", "Group Classes", "Nutrition Coaching", "Membership Plans"],
    "fitness":     ["Personal Training", "Group Classes", "Nutrition Coaching", "Membership Plans"],
    "dentist":     ["General Check-ups", "Teeth Whitening", "Orthodontics", "Emergency Care"],
    "dental":      ["General Check-ups", "Teeth Whitening", "Orthodontics", "Emergency Care"],
    "plumber":     ["Emergency Repairs", "Pipe Installation", "Drain Cleaning", "Bathroom Fitting"],
    "electrician": ["Wiring & Rewiring", "Fault Finding", "Panel Upgrades", "Smart Home Install"],
    "cleaning":    ["Deep Cleaning", "Regular Maintenance", "Move-In/Out Cleaning", "Commercial Cleaning"],
    "hotel":       ["Deluxe Rooms", "Conference Facilities", "Restaurant & Bar", "Concierge Services"],
    "guest":       ["Comfortable Rooms", "Full Breakfast", "Garden & Lounge", "Easy Check-in"],
    "bed":         ["Comfortable Rooms", "Full Breakfast", "Garden & Lounge", "Easy Check-in"],
    "lodge":       ["Luxury Accommodation", "Scenic Views", "Breakfast Included", "Tour Packages"],
    "accommodation": ["Room Booking", "Breakfast & Meals", "Guided Experiences", "Concierge Services"],
    "spa":         ["Full Body Massage", "Facial Treatments", "Couple Packages", "Detox Wraps"],
    "bakery":      ["Fresh Bread Daily", "Custom Cakes", "Pastries & Croissants", "Corporate Orders"],
    "florist":     ["Wedding Flowers", "Event Decoration", "Same-Day Delivery", "Custom Arrangements"],
    "mechanic":    ["Full Service & MOT", "Brake & Tyre Service", "Diagnostics", "Air Con Service"],
    "auto":        ["Full Service & MOT", "Brake & Tyre Service", "Diagnostics", "Air Con Service"],
}

DEFAULT_SERVICES = ["Professional Consultation", "Premium Service", "Fast Turnaround", "Satisfaction Guaranteed"]


def get_services(industry: str) -> list[str]:
    for key, services in INDUSTRY_SERVICES.items():
        if key in industry.lower():
            return services
    return DEFAULT_SERVICES


# ── Image Consistency ──────────────────────────────────────────────────────────
# Rules:
#   - All images use object-fit: cover (enforced via CSS — noted here for docs)
#   - Do NOT mix dark studio shots with bright outdoor shots
#   - Detect dominant brightness (light vs dark) from URL signals
#   - Filter out images that break consistency
#   - Max images per site: 6
#   - No duplicates

_DARK_URL_SIGNALS = [
    "dark", "night", "studio", "shadow", "moody", "black",
    # Unsplash photo IDs known to be dark/studio toned
]

_LIGHT_URL_SIGNALS = [
    "light", "bright", "outdoor", "sunny", "white", "natural",
    # Unsplash photo IDs known to be light toned
]


def detect_image_brightness(url: str) -> str:
    """
    Heuristic brightness detection from URL signals.

    Returns:
      "dark"    — URL suggests a dark/studio/night image
      "light"   — URL suggests a bright/outdoor/natural image
      "unknown" — no signal found (treat as neutral)
    """
    if not url or not isinstance(url, str):
        return "unknown"

    url_lower = url.lower()

    dark_score  = sum(1 for s in _DARK_URL_SIGNALS  if s in url_lower)
    light_score = sum(1 for s in _LIGHT_URL_SIGNALS if s in url_lower)

    if dark_score > light_score:
        return "dark"
    if light_score > dark_score:
        return "light"
    return "unknown"


_MAX_IMAGES_PER_SITE = 6


def enforce_image_consistency(urls: list[str]) -> list[str]:
    """
    Apply consistency rules to a list of image URLs.

    Rules applied (in order):
      1. Deduplicate (preserve first occurrence)
      2. Detect dominant brightness across the set
      3. Remove images that break the dominant tone
         (unknown-tone images are always kept — they don't break consistency)
      4. Cap at _MAX_IMAGES_PER_SITE (6)

    Returns a filtered, deduplicated list of image URLs.
    """
    if not urls:
        return []

    # ── Step 1: Deduplicate ───────────────────────────────────────────────
    seen:    set[str] = set()
    unique:  list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)

    # ── Step 2: Detect dominant brightness ───────────────────────────────
    tones = [detect_image_brightness(u) for u in unique]
    dark_count  = tones.count("dark")
    light_count = tones.count("light")

    if dark_count > light_count:
        dominant = "dark"
    elif light_count > dark_count:
        dominant = "light"
    else:
        dominant = "unknown"  # balanced or all unknown → keep all

    # ── Step 3: Filter tone outliers ─────────────────────────────────────
    if dominant != "unknown":
        opposite = "light" if dominant == "dark" else "dark"
        filtered = [u for u, t in zip(unique, tones) if t != opposite]
    else:
        filtered = unique

    # ── Step 4: Cap at max ────────────────────────────────────────────────
    return filtered[:_MAX_IMAGES_PER_SITE]
