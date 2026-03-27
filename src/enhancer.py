"""
enhancer.py

Controlled enhancement layer — enhances presentation WITHOUT faking reality.

Rules:
  - NO hallucinated data
  - NO AI-generated storefronts or interiors pretending to be the real business
  - Support images supplement only when real images are insufficient
  - Review cleaning is grammar-only — meaning is never changed

Exposes:
  generate_support_images(category: str, real_image_count: int) -> list[str]
  clean_review_phrase(text: str) -> str
  infer_services(category: str) -> list[str]
"""

import re as _re

# ── SUPPORT IMAGE GENERATION ─────────────────────────────────────────────────
# Curated Unsplash sets: lifestyle / product — NEVER storefronts or interiors
# that could be mistaken for the actual business premises.

_REAL_IMAGE_THRESHOLD = 4   # supplement only below this count
_MAX_SUPPORT_IMAGES   = 2   # hard cap on AI-augmented images

# Allowed support categories (safe, generic)
_ALLOWED_SUPPORT_CATEGORIES = {"cycling", "bike detail", "lifestyle"}

# Curated image sets per safe category
_SUPPORT_IMAGE_SETS: dict[str, list[str]] = {
    "cycling": [
        "https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=1200&h=800&fit=crop",
        "https://images.unsplash.com/photo-1571068316344-75bc76f77890?w=800&h=600&fit=crop",
    ],
    "bike detail": [
        "https://images.unsplash.com/photo-1576435728678-68d0fbf94e91?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&h=600&fit=crop",
    ],
    "lifestyle": [
        "https://images.unsplash.com/photo-1532298229144-0ec0c57515c7?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1604176354204-9268737828e4?w=800&h=600&fit=crop",
    ],
}


def generate_support_images(category: str, real_image_count: int = 0) -> list[str]:
    """
    Return a limited set of safe support images for a category.

    Rules:
      - Only generates if real_image_count < 4
      - Allowed categories: "cycling", "bike detail", "lifestyle"
      - Prompt style: premium, realistic, cinematic, photography
      - NEVER generates storefronts or interiors pretending to be the real business
      - Returns at most 2 URLs
    """
    if real_image_count >= _REAL_IMAGE_THRESHOLD:
        return []   # enough real images — no supplement needed

    cat = (category or "").lower().strip()

    # Direct match in allowed set
    for allowed_cat, urls in _SUPPORT_IMAGE_SETS.items():
        if allowed_cat in cat:
            return urls[:_MAX_SUPPORT_IMAGES]

    # Keyword fallback for bike-related categories
    if any(k in cat for k in ["bike", "bicycle", "cycle", "cycling"]):
        return _SUPPORT_IMAGE_SETS["cycling"][:_MAX_SUPPORT_IMAGES]

    # Generic fallback: lifestyle only
    return _SUPPORT_IMAGE_SETS["lifestyle"][:_MAX_SUPPORT_IMAGES]


# ── REVIEW PHRASE CLEANING ────────────────────────────────────────────────────

def clean_review_phrase(text: str) -> str:
    """
    Lightly clean a review phrase for grammar clarity only.

    Allowed fixes:
      - Strip leading/trailing whitespace
      - Normalise internal whitespace (collapse multiple spaces)
      - Capitalise the first character

    Forbidden:
      - Changing meaning
      - Adding new words
      - Rewriting phrasing
    """
    if not text or not isinstance(text, str):
        return text or ""

    cleaned = text.strip()
    cleaned = _re.sub(r"\s+", " ", cleaned)

    # Capitalise first letter only; leave everything else as-is
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    return cleaned


# ── SERVICE INFERENCE ─────────────────────────────────────────────────────────

_CATEGORY_SERVICES: dict[str, list[str]] = {
    "bike":         ["Bike Sales", "Servicing", "Repairs", "Accessories"],
    "bicycle":      ["Bike Sales", "Servicing", "Repairs", "Accessories"],
    "cycle":        ["Bike Sales", "Servicing", "Repairs", "Accessories"],
    "cycling":      ["Bike Sales", "Servicing", "Repairs", "Accessories"],
    "coffee":       ["Espresso & Filter", "Cold Brew", "Pastries", "Takeaway"],
    "cafe":         ["Specialty Coffee", "Light Meals", "Pastries", "Takeaway"],
    "charcuterie":  ["Artisan Cheeses", "Baked Goods", "Coffee", "Fresh Juices"],
    "restaurant":   ["Dine-In", "Takeaway", "Private Dining", "Catering"],
    "salon":        ["Haircut & Styling", "Colour", "Treatments", "Bridal"],
    "barber":       ["Haircuts", "Beard Trim", "Hot Towel Shave", "Kids Cuts"],
    "barbershop":   ["Haircuts", "Beard Trim", "Hot Towel Shave", "Kids Cuts"],
    "gym":          ["Personal Training", "Group Classes", "Nutrition", "Memberships"],
    "fitness":      ["Personal Training", "Group Classes", "Nutrition", "Memberships"],
    "spa":          ["Massage", "Facials", "Body Treatments", "Couples Packages"],
    "bakery":       ["Fresh Bread", "Custom Cakes", "Pastries", "Corporate Orders"],
    "dentist":      ["Check-ups", "Whitening", "Orthodontics", "Emergency Care"],
    "dental":       ["Check-ups", "Whitening", "Orthodontics", "Emergency Care"],
    "mechanic":     ["Servicing & MOT", "Brakes & Tyres", "Diagnostics", "Air Con"],
    "auto":         ["Servicing & MOT", "Brakes & Tyres", "Diagnostics", "Air Con"],
    "cleaning":     ["Deep Cleaning", "Regular Maintenance", "Move-In/Out", "Commercial"],
    "plumber":      ["Emergency Repairs", "Installation", "Drain Cleaning", "Fitting"],
    "electrician":  ["Wiring", "Fault Finding", "Panel Upgrades", "Smart Home"],
    "hotel":        ["Rooms", "Conference", "Restaurant & Bar", "Concierge"],
    "guest":        ["Accommodation", "Breakfast", "Garden Lounge", "Check-in"],
    "lodge":        ["Accommodation", "Breakfast", "Tours", "Concierge"],
    "florist":      ["Wedding Flowers", "Events", "Same-Day Delivery", "Custom Arrangements"],
}

_DEFAULT_SERVICES = ["Professional Service", "Quality Results", "Fast Turnaround", "Expert Team"]


def infer_services(category: str) -> list[str]:
    """
    Return safe default services based on business category.

    No hallucination — only returns curated, category-appropriate defaults.
    Returns _DEFAULT_SERVICES if category is unknown.
    """
    cat = (category or "").lower().strip()

    for key, services in _CATEGORY_SERVICES.items():
        if key in cat:
            return list(services)

    return list(_DEFAULT_SERVICES)
