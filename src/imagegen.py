"""imagegen.py  —  AI hero image generation via DALL-E 3

Generates a permanent, photorealistic hero image for each business demo.
Images are saved to disk and served via FastAPI's StaticFiles mount,
so they never expire (unlike Google Places photo URLs).

Usage:
    from src.imagegen import generate_hero_image
    local_url = generate_hero_image(slug, business_data)
    # Returns "/static/hero-images/{slug}.jpg" on success, None on failure.
"""

import os
import requests as _requests
from src.config import HERO_IMAGES_DIR

# ── Category-specific DALL-E 3 prompts ─────────────────────────────────────────
# Rules: no text/signs, no people, photorealistic, hero-appropriate lighting.
_PROMPTS: dict[str, str] = {
    "cafe": (
        "Warm artisan coffee shop interior, morning golden light filtering through large windows, "
        "wooden tables and chairs, steaming coffee cups and fresh pastries on the counter, "
        "hanging pendant lights, lush indoor plants, cosy and inviting atmosphere, "
        "photorealistic interior photography, no people, no visible text or lettering on any surface"
    ),
    "coffee": (
        "Specialty coffee bar interior, sleek and modern with warm earthy tones, "
        "professional espresso equipment on a timber counter, coffee beans in glass jars, "
        "warm pendant lighting, minimalist wooden shelving, no people, no text, photorealistic"
    ),
    "restaurant": (
        "Elegant restaurant interior at golden hour, warm ambient candlelight, "
        "white-linen set tables with wine glasses, rich wood tones, intimate atmosphere, "
        "photorealistic interior photography, no people, no text or menus visible"
    ),
    "bakery": (
        "Artisan bakery interior, rustic wooden shelves lined with golden loaves and colourful pastries, "
        "warm morning light, flour-dusted marble countertop, exposed brick walls, antique bread baskets, "
        "no people, no text, photorealistic"
    ),
    "salon": (
        "Modern hair salon interior, sleek and elegant, styling stations with large round mirrors, "
        "warm soft lighting, fresh white flowers, marble accents, no people, no text, photorealistic"
    ),
    "barber": (
        "Classic barbershop interior, vintage leather barber chairs, large antique mirrors, "
        "black-and-white tiled floor, wooden cabinets with grooming tools neatly arranged, "
        "warm tungsten lighting, premium masculine atmosphere, no people, no text, photorealistic"
    ),
    "barbershop": (
        "Classic barbershop interior, vintage leather barber chairs, large antique mirrors, "
        "black-and-white tiled floor, wooden cabinets with grooming tools neatly arranged, "
        "warm tungsten lighting, premium masculine atmosphere, no people, no text, photorealistic"
    ),
    "gym": (
        "Modern premium gym interior, floor-to-ceiling windows with natural light, "
        "clean polished floors, rows of professional fitness equipment, "
        "motivational atmosphere, no people, no text, photorealistic"
    ),
    "fitness": (
        "Modern premium gym interior, floor-to-ceiling windows with natural light, "
        "clean polished floors, rows of professional fitness equipment, "
        "motivational atmosphere, no people, no text, photorealistic"
    ),
    "spa": (
        "Luxury day spa treatment room, serene and calming, natural stone surfaces, "
        "soft ambient candlelight, lush tropical plants, white linen towels, "
        "tranquil and peaceful, no people, no text, photorealistic"
    ),
    "hotel": (
        "Boutique hotel lobby, elegant and luxurious, marble floors, large floral arrangements, "
        "warm ambient lighting, comfortable velvet seating areas, high ceilings, "
        "no people, no text, photorealistic"
    ),
    "guesthouse": (
        "Beautiful South African guesthouse exterior at sunrise, lush garden, "
        "whitewashed walls, terracotta roof tiles, wide veranda with garden furniture, "
        "bougainvillea in bloom, mountains in background, no people, no text, photorealistic"
    ),
    "guest": (
        "Beautiful South African guesthouse exterior at sunrise, lush garden, "
        "whitewashed walls, terracotta roof tiles, wide veranda with garden furniture, "
        "bougainvillea in bloom, no people, no text, photorealistic"
    ),
    "lodge": (
        "Luxury South African safari lodge exterior, thatched roof, infinity pool, "
        "African bush landscape, warm sunset light, wooden deck with lounge chairs, "
        "no people, no text, photorealistic"
    ),
    "bike": (
        "Well-organised bicycle shop interior, rows of high-end road and mountain bikes on display, "
        "workshop tools neatly hung on pegboard, timber and industrial steel shelving, "
        "clean well-lit space, no people, no text, photorealistic"
    ),
    "cycle": (
        "Well-organised bicycle shop interior, rows of high-end road and mountain bikes on display, "
        "workshop tools neatly hung on pegboard, timber and industrial steel shelving, "
        "clean well-lit space, no people, no text, photorealistic"
    ),
    "florist": (
        "Beautiful florist shop interior, buckets overflowing with fresh colourful flowers, "
        "warm soft lighting, wooden shelving with plants, earthy and botanical atmosphere, "
        "no people, no text, photorealistic"
    ),
    "mechanic": (
        "Clean modern automotive workshop, polished epoxy floor, professional car hoisted on a lift, "
        "neatly organised tool chest, bright overhead lighting, no people, no text, photorealistic"
    ),
    "auto": (
        "Clean modern automotive workshop, polished epoxy floor, professional car hoisted on a lift, "
        "neatly organised tool chest, bright overhead lighting, no people, no text, photorealistic"
    ),
    "dentist": (
        "Modern dental practice reception area, clean and welcoming, soft lighting, "
        "comfortable seating, plants, contemporary interior design, "
        "no people, no text, photorealistic"
    ),
    "dental": (
        "Modern dental practice reception area, clean and welcoming, soft lighting, "
        "comfortable seating, plants, contemporary interior design, "
        "no people, no text, photorealistic"
    ),
}

_DEFAULT_PROMPT = (
    "Warm and inviting South African small business interior, natural light, "
    "clean and professional, tasteful decor, no people, no text, photorealistic"
)


def _build_prompt(category: str) -> str:
    """Return the best DALL-E prompt for a given business category."""
    cat = (category or "").lower()
    for key, prompt in _PROMPTS.items():
        if key in cat:
            return prompt
    return _DEFAULT_PROMPT


def generate_hero_image(slug: str, business_data: dict) -> str | None:
    """
    Generate a DALL-E 3 hero image for a business demo and save it to disk.

    Returns the static URL path "/static/hero-images/{slug}.jpg" on success,
    or None if generation fails (caller should keep the existing hero_image).

    Skips silently if OPENAI_API_KEY is not set.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(f"[ImageGen] OPENAI_API_KEY not set — skipping for {slug}")
        return None

    # Don't re-generate if the image already exists on disk
    os.makedirs(HERO_IMAGES_DIR, exist_ok=True)
    out_path = os.path.join(HERO_IMAGES_DIR, f"{slug}.jpg")
    if os.path.exists(out_path):
        print(f"[ImageGen] Image already exists for {slug} — skipping")
        return f"/static/hero-images/{slug}.jpg"

    category = (
        business_data.get("category")
        or business_data.get("industry")
        or ""
    )
    prompt = _build_prompt(category)

    try:
        # Import here so the module loads fine even without openai installed
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        print(f"[ImageGen] Generating for {slug} (category: {category or 'default'})…")
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",   # Wide landscape — ideal for full-bleed heroes
            quality="standard", # $0.08/image; upgrade to "hd" for $0.12 if needed
            n=1,
        )

        image_url = response.data[0].url

        # Download and persist to disk
        dl = _requests.get(image_url, timeout=60, allow_redirects=True)
        dl.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(dl.content)

        print(f"[ImageGen] ✓ Saved {out_path}")
        return f"/static/hero-images/{slug}.jpg"

    except Exception as exc:
        print(f"[ImageGen] ✗ Failed for {slug}: {exc}")
        return None
