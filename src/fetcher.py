# Side-channel stats read by pipeline.py
_last_fetch_stats: dict = {"raw": 0, "filtered": 0}


def fetch_leads(industry: str, location: str):
    print("[Fetcher] LOCAL MODE ACTIVE")

    leads = []

    for i in range(15):
        leads.append({
            "name": f"{industry.title()} {location.title()} #{i+1}",
            "city": location,
            "address": f"{i+1} Main Road, {location}",
            "phone": f"03155500{str(i).zfill(2)}",
            "website": "" if i % 2 == 0 else "https://example.com",
            "rating": 4.0,
            "reviews_count": 10 + i,
            "category": industry,
            "google_maps_url": "",
            "maps_url": "",
            "place_id": f"demo-{i}",
            "lat": "",
            "lng": "",
            "photos": [],
            "reviews": [],
            "reviews_text": [],
            "has_whatsapp": False if i % 3 == 0 else True,
            "whatsapp_confidence": 0 if i % 3 == 0 else 1,
        })

    _last_fetch_stats["raw"] = len(leads)
    _last_fetch_stats["filtered"] = len(leads)
    return leads