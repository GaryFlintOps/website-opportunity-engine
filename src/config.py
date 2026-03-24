import os
from dotenv import load_dotenv

load_dotenv()

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
if not APIFY_API_TOKEN:
    raise Exception("APIFY_API_TOKEN not set — add it to your .env or Render environment variables")

APIFY_ACTOR_ID = "compass/crawler-google-places"

MAX_RESULTS = 40

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
CARDS_DIR = os.path.join(DATA_DIR, "cards")
REVIEWS_DIR = os.path.join(DATA_DIR, "reviews")
DEMOS_DIR = os.path.join(DATA_DIR, "demos")
CACHE_DIR = os.path.join(DATA_DIR, "cache")

# Public URL where Next.js demos are served (Vercel deployment)
SITE_URL = os.getenv("SITE_URL", "https://website-engine-alpha.vercel.app")

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
    "spa": "Relax. Restore. Rejuvenate.",
    "bakery": "Fresh baked. Made with love.",
    "florist": "Blooms that speak louder than words.",
    "lawyer": "Your rights. Our priority.",
    "accountant": "Numbers that work for you.",
    "mechanic": "Your car is in good hands.",
    "auto": "Expert care for every mile.",
}

DEFAULT_TAGLINE = "Built for people who expect more."
