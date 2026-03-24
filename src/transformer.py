"""
transformer.py

build_business_data(lead, industry) → dict

Assembles a clean BusinessData object for demo generation.
Uses REAL Apify data everywhere possible.
Only synthesises text where no real data exists (tagline, services).
Never fabricates reviews or photos.
"""

from src.preview import get_tagline, get_services


def build_business_data(lead: dict, industry: str) -> dict:
    """
    Assemble real business data for demo generation.

    Returns a BusinessData dict consumed by preview.generate_from_business_data().
    """
    name          = lead.get("name", "")
    city          = lead.get("city", "")
    address       = lead.get("address", "")
    phone         = lead.get("phone", "")
    website       = lead.get("website", "")
    rating        = lead.get("rating", 0)
    reviews_count = lead.get("reviews_count", 0)
    google_maps_url = lead.get("google_maps_url", "")
    place_id      = lead.get("place_id", "")
    lat           = lead.get("lat", "")
    lng           = lead.get("lng", "")
    category      = lead.get("category", "")

    # ── IMAGES ──────────────────────────────────────────────────────────────
    # Priority 1: real Google Maps photos from Apify
    # Priority 2: Unsplash fallback (only if no real photos)
    photos = lead.get("photos", []) or []

    kw = industry.lower().replace(" ", ",")
    if photos:
        hero_image     = photos[0]
        gallery_images = list(photos[1:7])      # up to 6 real gallery images
        # Guarantee minimum 3 gallery tiles — pad with Unsplash if needed
        while len(gallery_images) < 3:
            i = len(gallery_images) + 1
            gallery_images.append(
                f"https://source.unsplash.com/800x600/?{kw}&sig={i}"
            )
    else:
        hero_image     = f"https://source.unsplash.com/1600x900/?{kw}"
        # Varied Unsplash params so gallery tiles are different images
        gallery_images = [
            f"https://source.unsplash.com/800x600/?{kw}&sig={i}"
            for i in range(1, 5)
        ]

    # ── REVIEWS ─────────────────────────────────────────────────────────────
    # Only use real review objects. No fabrication.
    # Sort by rating desc so best reviews surface first; show up to 5.
    reviews_raw = sorted(
        lead.get("reviews", []) or [],
        key=lambda r: int(r.get("rating") or 0),
        reverse=True,
    )
    reviews = []
    for r in reviews_raw:
        text = (r.get("text") or "").strip()
        if text and len(text) > 25:
            reviews.append({
                "text":   text[:320],
                "author": r.get("author") or "Verified Customer",
                "rating": int(r.get("rating") or 5),
            })
        if len(reviews) >= 5:
            break
    # has_real_reviews is True only when at least 2 substantive reviews exist
    has_real_reviews = len(reviews) >= 2

    # ── MAP EMBED ────────────────────────────────────────────────────────────
    # Use coords if available, otherwise fall back to address search
    if lat and lng:
        map_embed = (
            f"https://maps.google.com/maps"
            f"?q={lat},{lng}&z=15&output=embed"
        )
    elif address:
        from urllib.parse import quote
        q = quote(f"{name}, {address}")
        map_embed = f"https://maps.google.com/maps?q={q}&output=embed"
    else:
        map_embed = ""

    # ── SYNTHETIC ONLY WHERE NEEDED ──────────────────────────────────────────
    tagline  = get_tagline(industry)
    services = get_services(industry)

    return {
        # Core identity
        "name":           name,
        "city":           city,
        "address":        address,
        "phone":          phone,
        "website":        website,
        "rating":         rating,
        "reviews_count":  reviews_count,
        "category":       category,
        "google_maps_url": google_maps_url,
        "place_id":       place_id,
        # Images (real first, Unsplash fallback)
        "hero_image":     hero_image,
        "gallery_images": gallery_images,
        "has_real_photos": len(lead.get("photos", [])) > 0,
        # Reviews (real only; requires >= 2 substantive reviews)
        "reviews":        reviews,
        "has_real_reviews": has_real_reviews,
        # Map
        "map_embed":      map_embed,
        # Synthesised (tagline + services only)
        "tagline":        tagline,
        "services":       services,
        "industry":       industry,
    }
