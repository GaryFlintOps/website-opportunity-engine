"""
preview.py

Data helpers only. HTML generation has been removed.
Demo rendering is now handled by the Next.js app (web/).

Exports:
  get_tagline(industry)  → str
  get_services(industry) → list[str]
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
