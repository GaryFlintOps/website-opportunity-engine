"""imagegen.py  —  Hero image sourcing for business demo pages.

Priority order for each demo:
  1. cache_hero_from_photos() — download & cache the real Google photo immediately
     (prevents expiry; free; shows the actual place)
  2. generate_hero_image()    — DALL-E 3 fallback if no real photo is available
     (costs ~$0.08/image; requires OPENAI_API_KEY)

Both functions save to HERO_IMAGES_DIR/{slug}.jpg and return the static URL
"/static/hero-images/{slug}.jpg" so the image never expires.
"""

import io
import os
import requests as _requests
from src.config import HERO_IMAGES_DIR

# ── Hero image enhancement ──────────────────────────────────────────────────
# Target aspect ratio for hero banners: 16:5 (wide cinematic crop)
_HERO_W = 1600
_HERO_H = 500


def _enhance_for_hero(raw_bytes: bytes) -> bytes:
    """
    Take raw image bytes downloaded from Google Maps and return hero-ready JPEG bytes.

    Edits applied (all on the real photo — nothing is fabricated):
      1. Convert to RGB (handles WEBP, PNG with alpha, CMYK)
      2. Smart centre-crop to 16:5 widescreen hero ratio
      3. Resize to 1600×500 px (retina-friendly)
      4. Sharpness  +40%  — Google thumbnails are often slightly soft
      5. Contrast   +15%  — lifts midtones without blowing highlights
      6. Colour     +20%  — makes the real colours pop on screen

    All adjustments are tasteful / non-destructive of factual content.
    """
    from PIL import Image, ImageEnhance, ImageFilter

    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    src_w, src_h = img.size

    # ── 1. Smart centre-crop to target aspect ratio ─────────────────────────
    target_ratio = _HERO_W / _HERO_H           # ≈ 3.2 : 1
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # Source is wider than needed — crop sides, keep full height
        new_w = int(src_h * target_ratio)
        left  = (src_w - new_w) // 2
        img   = img.crop((left, 0, left + new_w, src_h))
    else:
        # Source is taller than needed — crop top/bottom, prefer upper portion
        # (business interiors / exteriors usually have subject in the upper 2/3)
        new_h = int(src_w / target_ratio)
        top   = max(0, int((src_h - new_h) * 0.35))   # 35% from top
        img   = img.crop((0, top, src_w, top + new_h))

    # ── 2. Resize to output dimensions ──────────────────────────────────────
    img = img.resize((_HERO_W, _HERO_H), Image.LANCZOS)

    # ── 3. Sharpen — recovers detail lost in thumbnail compression ───────────
    img = ImageEnhance.Sharpness(img).enhance(1.4)

    # ── 4. Contrast boost — lifts the midtone presence ───────────────────────
    img = ImageEnhance.Contrast(img).enhance(1.15)

    # ── 5. Colour / saturation — makes real colours read well on screen ───────
    img = ImageEnhance.Color(img).enhance(1.2)

    # ── Output ───────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()

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


def cache_hero_from_photos(slug: str, photos: list) -> str | None:
    """
    Download the first usable real photo from the lead's photo list and
    cache it permanently to HERO_IMAGES_DIR/{slug}.jpg.

    This is the preferred hero image source — real business photos beat
    AI-generated ones.  Downloading immediately avoids Google URL expiry.

    Returns "/static/hero-images/{slug}.jpg" on success, None if all photos
    fail (caller should then try generate_hero_image as fallback).
    """
    if not photos:
        return None

    os.makedirs(HERO_IMAGES_DIR, exist_ok=True)
    out_path = os.path.join(HERO_IMAGES_DIR, f"{slug}.jpg")

    # Already cached from a previous run — return immediately
    if os.path.exists(out_path):
        print(f"[ImageGen] Cached photo already exists for {slug} — skipping download")
        return f"/static/hero-images/{slug}.jpg"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.google.com/",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    }

    for url in photos:
        if not url or not isinstance(url, str) or not url.startswith("http"):
            continue
        try:
            resp = _requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            # Reject tiny responses — likely error pages, not real images
            if resp.status_code != 200 or len(resp.content) < 5_000:
                print(f"[ImageGen] Photo unusable for {slug}: HTTP {resp.status_code} / {len(resp.content)} bytes")
                continue

            content_type = resp.headers.get("content-type", "")
            is_image = (
                "image" in content_type
                or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            )
            if not is_image:
                print(f"[ImageGen] Skipping non-image response for {slug}: {content_type}")
                continue

            # Save the real photo as-is — no enhancement, no fabrication
            with open(out_path, "wb") as f:
                f.write(resp.content)
            print(f"[ImageGen] ✓ Cached real photo for {slug} ({len(resp.content)//1024}KB)")
            return f"/static/hero-images/{slug}.jpg"

        except Exception as exc:
            print(f"[ImageGen] Photo fetch error for {slug}: {exc}")
            continue

    print(f"[ImageGen] No usable real photo found for {slug} — will try DALL-E fallback")
    return None


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
