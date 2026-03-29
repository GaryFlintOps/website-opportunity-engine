import os
from dotenv import load_dotenv

load_dotenv()

# ── Data source: Outscraper (primary) ─────────────────────────────────────────
OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY")
if not OUTSCRAPER_API_KEY:
    print("⚠  OUTSCRAPER_API_KEY not set — search will be disabled. Dashboard works with existing data.")

# ── Apify (kept for reference — no longer called by default) ──────────────────
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
APIFY_ACTOR_ID  = "compass/crawler-google-places"

MAX_RESULTS = 40

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
CARDS_DIR = os.path.join(DATA_DIR, "cards")
REVIEWS_DIR = os.path.join(DATA_DIR, "reviews")
DEMOS_DIR = os.path.join(DATA_DIR, "demos")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
HERO_IMAGES_DIR = os.path.join(DATA_DIR, "hero-images")

# Public URL where demos are served — Render is the single deployment target
SITE_URL = os.getenv("SITE_URL", "https://website-opportunity-engine.onrender.com")

TAGLINES = {
    "coffee": "Your daily coffee, done right.",
    "cafe": "Your daily coffee, done right.",
    "salon": "Walk in confident. Walk out unstoppable.",
    "barbershop": "Sharp cuts. Clean lines. Great vibes.",
    "barber": "Sharp cuts. Clean lines. Great vibes.",
    "restaurant": "Food worth leaving home for.",
    "gym": "Push harder. Live better.",
    "fitness": "Your strongest self starts here.",
    "dentist": "Healthy smiles. Happy lives.",
    "dental": "Healthy smiles. Happy lives.",
    "plumber": "Fast fixes. Reliable results.",
    "electrician": "Powering your peace of mind.",
    "cleaning": "Spotless spaces. Stress-free living.",
    "hotel": "Where comfort meets convenience.",
    "guest": "Your home away from home.",
    "bed": "Wake up to something special.",
    "lodge": "Escape the ordinary. Stay extraordinary.",
    "accommodation": "Where every stay feels like home.",
    "spa": "Relax. Restore. Rejuvenate.",
    "bakery": "Fresh baked. Made with love.",
    "florist": "Blooms that speak louder than words.",
    "lawyer": "Your rights. Our priority.",
    "accountant": "Numbers that work for you.",
    "mechanic": "Your car is in good hands.",
    "auto": "Expert care for every mile.",
}

DEFAULT_TAGLINE = "Built for people who expect more."

# ── Industry brand colour palettes ────────────────────────────────────────────
# primary: hero text / headings
# accent:  buttons / highlights / links
# bg:      page background (always light)
# surface: card / section background
INDUSTRY_COLORS: dict[str, dict] = {
    "coffee":     {"primary": "#3B1E0A", "accent": "#C8973A", "bg": "#FBF8F4", "surface": "#F2EDE5"},
    "cafe":       {"primary": "#3B1E0A", "accent": "#C8973A", "bg": "#FBF8F4", "surface": "#F2EDE5"},
    "restaurant": {"primary": "#3A0E0E", "accent": "#C0612B", "bg": "#FBF6F4", "surface": "#F2E8E5"},
    "salon":      {"primary": "#2A1A3E", "accent": "#9B72CF", "bg": "#F9F7FC", "surface": "#EDE8F5"},
    "barbershop": {"primary": "#0D1E35", "accent": "#C9A96E", "bg": "#F5F7FA", "surface": "#E8EDF5"},
    "barber":     {"primary": "#0D1E35", "accent": "#C9A96E", "bg": "#F5F7FA", "surface": "#E8EDF5"},
    "gym":        {"primary": "#0F1117", "accent": "#E5433B", "bg": "#F5F5F5", "surface": "#EBEBEB"},
    "fitness":    {"primary": "#0F1117", "accent": "#E5433B", "bg": "#F5F5F5", "surface": "#EBEBEB"},
    "dentist":    {"primary": "#0E2840", "accent": "#2A86C8", "bg": "#F5F9FC", "surface": "#E5F0F8"},
    "dental":     {"primary": "#0E2840", "accent": "#2A86C8", "bg": "#F5F9FC", "surface": "#E5F0F8"},
    "plumber":    {"primary": "#0A1E2E", "accent": "#2A7CB8", "bg": "#F5F8FB", "surface": "#E5EEF5"},
    "electrician":{"primary": "#1A1A0A", "accent": "#C8A020", "bg": "#FDFCF5", "surface": "#F2EDD8"},
    "cleaning":   {"primary": "#0E2A1E", "accent": "#2EB87A", "bg": "#F5FCF8", "surface": "#E5F5EE"},
    "hotel":      {"primary": "#0D1520", "accent": "#C9A96E", "bg": "#F8F6F2", "surface": "#EDE8DE"},
    "guest":      {"primary": "#1E2D1A", "accent": "#7DAA55", "bg": "#F5F8F2", "surface": "#E8EEE3"},
    "bed":        {"primary": "#1E2D1A", "accent": "#7DAA55", "bg": "#F5F8F2", "surface": "#E8EEE3"},
    "lodge":      {"primary": "#1A2A1A", "accent": "#5C9450", "bg": "#F5F8F3", "surface": "#E5EEE3"},
    "spa":        {"primary": "#2A3A2A", "accent": "#8DAA7A", "bg": "#F5F5F0", "surface": "#E8EDE3"},
    "bakery":     {"primary": "#3A1800", "accent": "#CC6B28", "bg": "#FDF8F2", "surface": "#F5EAD8"},
    "florist":    {"primary": "#2A1E3A", "accent": "#C85A8A", "bg": "#FAF5FC", "surface": "#F0E5F5"},
    "mechanic":   {"primary": "#151515", "accent": "#E87722", "bg": "#F8F5F2", "surface": "#EEE8E0"},
    "auto":       {"primary": "#151515", "accent": "#E87722", "bg": "#F8F5F2", "surface": "#EEE8E0"},
}
DEFAULT_COLORS = {"primary": "#0D1520", "accent": "#C9A96E", "bg": "#F8F7F4", "surface": "#EDE8DE"}

# ── Industry "about" headline ─────────────────────────────────────────────────
INDUSTRY_ABOUT_HEADLINES: dict[str, str] = {
    "coffee":     "Where Every Cup Tells a Story",
    "cafe":       "Where Every Cup Tells a Story",
    "restaurant": "Crafted with Passion, Served with Pride",
    "salon":      "Where Style Meets Craft",
    "barbershop": "Sharp Style. Expert Hands.",
    "barber":     "Sharp Style. Expert Hands.",
    "gym":        "Your Transformation Starts Here",
    "fitness":    "Your Transformation Starts Here",
    "dentist":    "Your Smile Is Our Priority",
    "dental":     "Your Smile Is Our Priority",
    "spa":        "Escape the Everyday",
    "bakery":     "Baked Fresh, Every Single Day",
    "hotel":      "More Than a Stay",
    "guest":      "Your Home Away from Home",
    "bed":        "Wake Up to Something Special",
    "lodge":      "Escape the Ordinary",
    "cleaning":   "Spotless Every Time",
    "florist":    "Blooms that Speak Louder than Words",
    "mechanic":   "Your Car Is in Good Hands",
    "auto":       "Expert Care for Every Mile",
}
DEFAULT_ABOUT_HEADLINE = "Built for People Who Expect More"

# ── Industry feature stats (4th stat strip item) ──────────────────────────────
INDUSTRY_FEATURE_STAT: dict[str, str] = {
    "coffee":     "Free WiFi",
    "cafe":       "Free WiFi",
    "restaurant": "Dine-In & Takeaway",
    "salon":      "Walk-ins Welcome",
    "barbershop": "Walk-ins Welcome",
    "barber":     "Walk-ins Welcome",
    "gym":        "Open 7 Days",
    "fitness":    "Open 7 Days",
    "dentist":    "Medical Aid Accepted",
    "dental":     "Medical Aid Accepted",
    "spa":        "Appointments Available",
    "bakery":     "Fresh Baked Daily",
    "hotel":      "Free Parking",
    "guest":      "Breakfast Included",
    "bed":        "Breakfast Included",
    "lodge":      "Scenic Views",
    "plumber":    "24/7 Emergency",
    "electrician":"Same-Day Service",
    "cleaning":   "Fully Insured",
    "florist":    "Same-Day Delivery",
    "mechanic":   "Free Diagnostics",
    "auto":       "Free Diagnostics",
}
DEFAULT_FEATURE_STAT = "Locally Loved"

# ── Industry feature pills (about section checkmarks) ────────────────────────
INDUSTRY_FEATURE_PILLS: dict[str, list[str]] = {
    "coffee":     ["100% Arabica Beans", "Fresh Daily Baking", "Local Ingredients"],
    "cafe":       ["Specialty Coffee", "Homemade Food", "Cosy Atmosphere"],
    "restaurant": ["Fresh Local Produce", "Chef's Specials Daily", "Private Dining Available"],
    "salon":      ["Certified Stylists", "Premium Products", "Personalised Service"],
    "barbershop": ["Master Barbers", "Classic & Modern Cuts", "Clean & Hygienic"],
    "barber":     ["Master Barbers", "Classic & Modern Cuts", "Clean & Hygienic"],
    "gym":        ["Expert Trainers", "Modern Equipment", "All Fitness Levels"],
    "fitness":    ["Expert Trainers", "Modern Equipment", "All Fitness Levels"],
    "dentist":    ["Gentle & Painless", "Modern Equipment", "Family Friendly"],
    "dental":     ["Gentle & Painless", "Modern Equipment", "Family Friendly"],
    "spa":        ["Trained Therapists", "Luxury Products", "Private Treatment Rooms"],
    "bakery":     ["Baked Fresh Daily", "No Preservatives", "Custom Orders Welcome"],
    "hotel":      ["En-Suite Rooms", "Free Parking", "Breakfast Served"],
    "guest":      ["Comfortable Rooms", "Home-Cooked Breakfast", "Secure Parking"],
    "bed":        ["Comfortable Rooms", "Home-Cooked Breakfast", "Secure Parking"],
    "lodge":      ["Scenic Location", "Guided Activities", "Full Board Available"],
    "spa":        ["Trained Therapists", "Luxury Products", "Couples Packages"],
    "florist":    ["Same-Day Delivery", "Custom Arrangements", "Event Specialists"],
    "mechanic":   ["Qualified Mechanics", "Genuine Parts", "Warranty on All Work"],
    "auto":       ["Qualified Mechanics", "Genuine Parts", "Warranty on All Work"],
}
DEFAULT_FEATURE_PILLS = ["Professional Service", "Quality Guaranteed", "Locally Trusted"]

# ── Industry secondary CTA label ──────────────────────────────────────────────
INDUSTRY_CTA_LABEL: dict[str, str] = {
    "coffee":     "View Our Menu",
    "cafe":       "View Our Menu",
    "restaurant": "View Our Menu",
    "bakery":     "View Our Menu",
    "salon":      "Book an Appointment",
    "barbershop": "Book an Appointment",
    "barber":     "Book an Appointment",
    "gym":        "View Classes",
    "fitness":    "View Classes",
    "spa":        "See Treatments",
    "dentist":    "Book a Consultation",
    "dental":     "Book a Consultation",
    "hotel":      "Check Availability",
    "guest":      "Check Availability",
    "bed":        "Check Availability",
    "lodge":      "Check Availability",
}
DEFAULT_CTA_LABEL = "Get in Touch"
