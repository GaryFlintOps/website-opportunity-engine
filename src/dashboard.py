import os
import asyncio
import requests as _requests
from fastapi import FastAPI, Request, Form, BackgroundTasks, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
# CORSMiddleware intentionally not imported — all clients are same-origin

from src.pipeline import run_pipeline
from src.storage import (
    load_latest_leads, load_latest_filter_stats, get_lead_by_slug,
    save_demo, load_demo_data, load_demo_meta,
    get_demo_state, set_demo_state, demo_exists,
    get_all_demo_states,
)
from src.transformer import build_business_data
from src.cards import prepare_leads_for_display, filter_leads
from src.config import SITE_URL, DEMOS_DIR, OUTPUT_DIR, CACHE_DIR
from src.outreach import generate_message, generate_followup
from datetime import datetime as _dt
from src.tracking import (
    get_status, update_status, get_all_entries,
    followup_needed, OUTREACH_STATUSES, STATUS_LABELS,
)
import re
from urllib.parse import quote as _url_quote

def build_whatsapp_url(phone: str, message: str) -> str:
    """
    Build a wa.me link with a pre-filled message.
    Handles SA landline/mobile formatting:
      031 555 0000  →  27315550000
      +27 82 123 4567 →  27821234567
    Returns '' if phone is blank.
    """
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    # SA local format: leading 0 + 9 more digits → replace leading 0 with 27
    if digits.startswith("0") and len(digits) == 10:
        digits = "27" + digits[1:]
    # Already has country code without +
    elif not digits.startswith("27"):
        digits = "27" + digits  # best-effort fallback
    return f"https://wa.me/{digits}?text={_url_quote(message)}"


BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app       = FastAPI(title="Website Opportunity Engine")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ── CORS ──────────────────────────────────────────────────────────────────────
# All browser requests are same-origin (served from this Render instance).
# No cross-origin clients remain — CORSMiddleware is intentionally omitted.

# ── Startup: log resolved filesystem paths for Render log verification ────────
@app.on_event("startup")
async def startup_log():
    print("[Startup] Website Opportunity Engine is starting")
    print(f"[Startup] OUTPUT_DIR : {os.path.abspath(OUTPUT_DIR)}")
    print(f"[Startup] DEMOS_DIR  : {os.path.abspath(DEMOS_DIR)}")
    print(f"[Startup] CACHE_DIR  : {os.path.abspath(CACHE_DIR)}")
    print(f"[Startup] SITE_URL   : {SITE_URL}")
    on_render = bool(os.getenv("RENDER"))
    print(f"[Startup] Running on Render: {on_render}")
    if on_render:
        print("[Startup] ⚠  Render free tier — filesystem is EPHEMERAL. "
              "Demos are lost on redeploy unless a Render Disk is attached.")

_last_search: dict = {"industry": "", "location": "", "running": False, "error": ""}


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(
    request:       Request,
    min_score:     int  = 0,
    no_website:    bool = False,
    max_reviews:   int  = 0,
    filter_status: str  = "",    # "", "new", "contacted", "demo_sent", …
    has_phone:     bool = False,
    wc_zero:       bool = False,  # WhatsApp confidence == 0 only
):
    leads, industry, location = load_latest_leads()
    leads = prepare_leads_for_display(leads)

    # ── Merge tracking + outreach data into every lead ────────────────────
    tracking = get_all_entries()
    today    = _dt.utcnow().date().isoformat()

    for lead in leads:
        slug  = lead.get("slug", "")
        entry = tracking.get(slug, {})
        phone = lead.get("phone", "")

        lead["outreach_status"] = entry.get("status", "new")
        lead["followup_nudge"]  = followup_needed(entry) if entry else None
        lead["followup"]        = lead["followup_nudge"]   # alias used in template

        # WhatsApp confidence fallback for leads fetched before the field existed
        if "whatsapp_confidence" not in lead:
            lead["whatsapp_confidence"] = 1 if lead.get("has_whatsapp") else 0

        # Per-lead send URLs (populated only if a phone number exists)
        if phone:
            lead["whatsapp_send_url"]   = build_whatsapp_url(phone, generate_message(lead))
            lead["whatsapp_followup_url"] = build_whatsapp_url(phone, generate_followup(lead))
            lead["followup_message"]    = generate_followup(lead)
        else:
            lead["whatsapp_send_url"]     = ""
            lead["whatsapp_followup_url"] = ""
            lead["followup_message"]      = ""

    # ── Priority sort (before filtering so rank order is preserved) ───────
    # Bucket order: new → has phone → no WA (wc=0) → high score
    leads.sort(key=lambda l: (
        l.get("outreach_status") != "new",    # new leads first
        not l.get("phone"),                   # has phone first
        l.get("whatsapp_confidence", 2) > 0,  # no-WA leads first
        -l.get("score", 0),                   # highest score first
    ))

    # ── Apply filters ─────────────────────────────────────────────────────
    filtered = filter_leads(leads, min_score=min_score, no_website_only=no_website, max_reviews=max_reviews)

    if filter_status and filter_status in OUTREACH_STATUSES:
        filtered = [l for l in filtered if l.get("outreach_status") == filter_status]

    if has_phone:
        filtered = [l for l in filtered if l.get("phone")]

    if wc_zero:
        filtered = [l for l in filtered if l.get("whatsapp_confidence", 1) == 0]

    for lead in filtered:
        lead["demo_state"] = get_demo_state(lead.get("slug", ""))

    # ── Daily stats (computed over ALL leads, not just filtered view) ─────
    sent_today     = sum(
        1 for e in tracking.values()
        if e.get("status") == "contacted"
        and e.get("updated_at", "").startswith(today)
    )
    followups_due  = sum(1 for e in tracking.values() if followup_needed(e))
    followup_count = sum(1 for l in leads if l.get("followup_nudge"))

    # ── Ephemeral storage warning ─────────────────────────────────────────
    ephemeral_warning = bool(os.getenv("RENDER") and not os.getenv("PERSISTENT_DEMOS_DIR"))

    # ── Filter quality metrics ────────────────────────────────────────────
    filter_stats   = load_latest_filter_stats()
    raw_count      = filter_stats.get("raw", 0)
    filtered_total = filter_stats.get("filtered", 0)
    filter_pct     = round(filtered_total / raw_count * 100) if raw_count else None
    low_confidence = bool(
        filter_stats
        and (
            filtered_total < 5
            or (raw_count > 0 and filtered_total / raw_count < 0.30)
        )
    )

    return templates.TemplateResponse("index.html", {
        "request":           request,
        "leads":             filtered,
        "total":             len(leads),
        "filtered_count":    len(filtered),
        "industry":          industry,
        "location":          location,
        "min_score":         min_score,
        "no_website":        no_website,
        "max_reviews":       max_reviews,
        "filter_status":     filter_status,
        "has_phone":         has_phone,
        "wc_zero":           wc_zero,
        "running":           _last_search["running"],
        "error":             _last_search["error"],
        "site_url":          SITE_URL,
        "ephemeral_warning": ephemeral_warning,
        "raw_count":         raw_count,
        "filtered_total":    filtered_total,
        "filter_pct":        filter_pct,
        "low_confidence":    low_confidence,
        "followup_count":    followup_count,
        "sent_today":        sent_today,
        "followups_due":     followups_due,
        "outreach_statuses": list(OUTREACH_STATUSES),
        "status_labels":     STATUS_LABELS,
    })


# ── Search ────────────────────────────────────────────────────────────────────

@app.post("/search")
async def search(
    background_tasks: BackgroundTasks,
    industry: str = Form(...),
    location: str = Form(...),
):
    _last_search.update({"industry": industry, "location": location,
                          "running": True, "error": ""})
    background_tasks.add_task(_run_search, industry, location)
    return RedirectResponse(url="/", status_code=303)


def _run_search(industry: str, location: str):
    try:
        run_pipeline(industry, location)
    except Exception as e:
        _last_search["error"] = str(e)
        print(f"[Dashboard] Pipeline error: {e}")
    finally:
        _last_search["running"] = False


@app.get("/status")
async def status():
    return {"running": _last_search["running"], "error": _last_search["error"]}


# ── Lead detail ───────────────────────────────────────────────────────────────

@app.get("/lead/{slug}", response_class=HTMLResponse)
async def lead_detail(request: Request, slug: str):
    lead, industry, location = get_lead_by_slug(slug)
    if not lead:
        return HTMLResponse("<h1>Lead not found</h1>", status_code=404)

    outreach_status  = get_status(slug)
    outreach_msg     = generate_message(lead)
    whatsapp_send_url = build_whatsapp_url(lead.get("phone", ""), outreach_msg)
    return templates.TemplateResponse("lead.html", {
        "request":           request,
        "lead":              lead,
        "industry":          industry,
        "location":          location,
        "demo_state":        get_demo_state(slug),
        "demo_meta":         load_demo_meta(slug),
        "site_url":          SITE_URL,
        "outreach_message":  outreach_msg,
        "whatsapp_send_url": whatsapp_send_url,
        "outreach_status":   outreach_status,
        "outreach_statuses": list(OUTREACH_STATUSES),
        "status_labels":     STATUS_LABELS,
    })


# ── Outreach tracking ─────────────────────────────────────────────────────────

@app.post("/track/{slug}")
async def track_lead(slug: str, status: str = Form(...)):
    """Update the outreach status for a lead and redirect back to lead detail."""
    try:
        update_status(slug, status)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return RedirectResponse(url=f"/lead/{slug}", status_code=303)


@app.post("/track-send/{slug}")
async def track_send(slug: str):
    """
    Mark lead as 'contacted' via WhatsApp (called by JS before opening wa.me).
    Returns JSON so the JS can proceed without a full page reload.
    """
    try:
        update_status(slug, "contacted", channel="whatsapp")
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True})


# ── Image proxy ───────────────────────────────────────────────────────────────
# Google's lh3.googleusercontent.com blocks direct browser requests.
# We fetch server-side (no referrer restrictions) and stream back to the browser.

_IMG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.google.com/",
}


def _proxy_url(img_url: str) -> str:
    """Wrap an external image URL with our server-side proxy endpoint."""
    if not img_url:
        return ""
    return f"/img-proxy?url={_url_quote(img_url, safe='')}"


@app.get("/img-proxy")
async def img_proxy(url: str):
    """Fetch an external image server-side and return it to the browser."""
    def _fetch(u: str):
        return _requests.get(u, headers=_IMG_HEADERS, timeout=12, allow_redirects=True)

    try:
        loop = asyncio.get_running_loop()
        resp  = await loop.run_in_executor(None, _fetch, url)
        if resp.status_code != 200:
            print(f"[ImgProxy] HTTP {resp.status_code} for {url[:80]}")
            return Response(content=b"", status_code=resp.status_code)
        ctype = resp.headers.get("content-type", "image/jpeg")
        return Response(
            content=resp.content,
            media_type=ctype,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        print(f"[ImgProxy] Error fetching {url[:80]}: {e}")
        return Response(content=b"", status_code=502,
                        headers={"X-Proxy-Error": str(e)})


@app.get("/img-proxy-test")
async def img_proxy_test():
    """Quick check that the proxy can reach Google's image CDN."""
    test_url = "https://lh3.googleusercontent.com/p/AF1QipPafQif1aK9uZL3MnWg-eUe3J2LFqPLheSCINoT=w400-h300-k-no"
    def _fetch():
        return _requests.get(test_url, headers=_IMG_HEADERS, timeout=10)
    try:
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, _fetch)
        return JSONResponse({
            "ok": resp.status_code == 200,
            "status": resp.status_code,
            "content_type": resp.headers.get("content-type",""),
            "bytes": len(resp.content),
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)


# ── Demo: render HTML page via Jinja2 template ────────────────────────────────

def _extract_highlights(reviews: list[dict]) -> list[dict]:
    """
    Pull 3 stand-out highlights from 5-star reviews.
    Each highlight = {icon, title, quote} using keyword matching for
    meaningful titles rather than raw first-words.
    """
    # Ordered priority: first keyword match wins the title for that review
    KEYWORD_MAP = [
        (["breakfast", "brunch"],                                                          "☀️",  "Breakfast Favourite"),
        (["coffee", "espresso", "cappuccino", "latte", "flat white"],                     "☕",  "Perfect Coffee"),
        (["food", "meal", "dish", "menu", "cuisine", "delicious", "tasty"],               "🍽️", "Exceptional Food"),
        (["service", "staff", "waiter", "waitress", "attentive"],                         "🤝",  "Outstanding Service"),
        (["friendly", "welcoming", "warm", "hospitable"],                                  "😊",  "Friendly Team"),
        (["atmosphere", "ambiance", "vibe", "setting", "decor", "cosy", "cozy"],          "✨",  "Wonderful Atmosphere"),
        (["value", "price", "affordable", "worth", "reasonable", "half price"],           "💰",  "Great Value"),
        (["clean", "spotless", "hygienic", "tidy"],                                        "✨",  "Spotless & Clean"),
        (["recommend", "favourite", "favorite", "best in"],                                "⭐",  "Highly Recommended"),
        (["cut", "haircut", "hair", "style"],                                              "✂️",  "Expert Styling"),
        (["massage", "facial", "spa", "relax", "treatment"],                              "💆",  "Relaxing Experience"),
        (["workout", "gym", "training", "fitness", "classes"],                             "💪",  "Top-Class Training"),
        (["fast", "quick", "efficient", "prompt"],                                         "⚡",  "Fast & Efficient"),
        (["fresh", "quality", "organic", "homemade"],                                      "🌿",  "Premium Quality"),
        (["view", "beautiful", "stunning", "gorgeous", "amazing"],                        "🌟",  "Simply Amazing"),
    ]
    FALLBACK_TITLES = ["Amazing Experience", "Worth Every Visit", "Truly Outstanding"]

    five_star = [r for r in reviews if int(r.get("rating", 0)) >= 5]
    if not five_star:
        five_star = reviews

    highlights = []
    used_titles: set[str] = set()

    for r in five_star[:10]:
        text = r.get("text", "").strip()
        if not text:
            continue
        text_lower = text.lower()

        # First sentence, capped at 90 chars
        sentence = text.split(".")[0].split("!")[0].split("?")[0].strip()
        if len(sentence) > 90:
            sentence = sentence[:87] + "…"
        if len(sentence) < 10:
            continue  # skip trivially short quotes

        # Find best matching keyword group not yet used
        matched_icon, matched_title = "🌟", None
        for keywords, icon, title in KEYWORD_MAP:
            if title in used_titles:
                continue
            for kw in keywords:
                if kw in text_lower:
                    matched_icon  = icon
                    matched_title = title
                    break
            if matched_title:
                break

        # Fallback generic titles
        if not matched_title:
            for fb in FALLBACK_TITLES:
                if fb not in used_titles:
                    matched_title = fb
                    matched_icon  = "🌟"
                    break

        if not matched_title or matched_title in used_titles:
            continue

        used_titles.add(matched_title)
        highlights.append({"icon": matched_icon, "title": matched_title, "quote": sentence})

        if len(highlights) == 3:
            break

    return highlights


@app.get("/demo/{slug}", response_class=HTMLResponse)
async def render_demo(request: Request, slug: str):
    """Render the business demo page using the modern Jinja2 template."""
    data = load_demo_data(slug)
    if data is None:
        return HTMLResponse(
            "<html><body style='font-family:Arial;padding:40px;background:#0d0f14;color:#f0f0f0'>"
            f"<h1>Demo not found</h1>"
            f"<p>No demo has been generated for <code>{slug}</code> yet.</p>"
            f"<p><a href='/' style='color:#c9a96e'>← Back to dashboard</a></p>"
            "</body></html>",
            status_code=404,
        )

    phone    = data.get("phone", "")
    name     = data.get("name", "Business")
    reviews  = data.get("reviews", [])

    wa_url = build_whatsapp_url(
        phone,
        f"Hi {name}, I saw your listing and wanted to find out more!"
    ) if phone else ""

    colors = data.get("colors") or {}

    # Full gallery = all google images (hero excluded; already deduplicated in transformer)
    raw_gallery = data.get("gallery_images", [])
    all_gallery  = [_proxy_url(u) for u in raw_gallery if u]

    # Hero review snippet — shortest meaningful 5-star review, capped at ~10 words
    def _pick_hero_review(revs: list[dict]) -> str:
        five_star = [r for r in revs if int(r.get("rating", 0)) >= 5]
        pool = five_star if five_star else revs
        best = ""
        for r in pool:
            text = r.get("text", "").strip()
            if len(text) < 8:
                continue
            # First sentence only
            sentence = text.split(".")[0].split("!")[0].split("?")[0].strip()
            words = sentence.split()
            snippet = " ".join(words[:10]) + ("…" if len(words) > 10 else "")
            if not best or len(snippet) < len(best):
                best = snippet
        return best

    hero_review = _pick_hero_review(reviews)

    # Menu module — comes from demo JSON "menu" key; disabled by default
    menu_data    = data.get("menu")           # None or {sections:[{title,items:[{name,price?}]}]}
    modules_cfg  = data.get("modules", {})    # {menu: bool}
    menu_enabled = bool(modules_cfg.get("menu", False) and menu_data)

    return templates.TemplateResponse("demo.html", {
        "request":        request,
        "name":           name,
        "tagline":        data.get("tagline", ""),
        "category":       data.get("category", ""),
        "city":           data.get("city", ""),
        "address":        data.get("address", ""),
        "phone":          phone,
        "rating":         data.get("rating", ""),
        "reviews_count":  data.get("reviews_count", ""),
        "hero_image":     _proxy_url(data.get("hero_image", "")),
        "gallery_images": all_gallery,
        "services":       data.get("services", []),
        "reviews":        reviews,
        "google_maps_url": data.get("google_maps_url", ""),
        "map_embed":      data.get("map_embed", ""),
        "wa_url":         wa_url,
        "highlights":     _extract_highlights(reviews),
        # Branding
        "color_primary":  colors.get("primary", "#0D1520"),
        "color_accent":   colors.get("accent",  "#C9A96E"),
        "color_bg":       colors.get("bg",      "#F8F7F4"),
        "color_surface":  colors.get("surface", "#EDE8DE"),
        "about_text":     data.get("about_text", ""),
        "feature_stat":   data.get("feature_stat", "Locally Loved"),
        "feature_pills":  data.get("feature_pills", []),
        "cta_label":      data.get("cta_label", "Get in Touch"),
        "promo":          data.get("promo", ""),
        "cta_line":       data.get("cta_line", ""),
        "rating_badge":   data.get("rating_badge", ""),
        "hero_review":    hero_review,
        # Diagnostic intelligence
        "has_website":       data.get("has_website", False),
        "website_status":    data.get("website_status", "unknown"),
        "has_whatsapp":      data.get("has_whatsapp", False),
        "strong_reviews":    data.get("strong_reviews", False),
        "opportunity_score": data.get("opportunity_score", 0),
        "opportunity_label": data.get("opportunity_label", "Low"),
        # Menu module
        "menu_enabled":   menu_enabled,
        "menu":           menu_data or {},
    })


# ── API: serve BusinessData JSON ──────────────────────────────────────────────

@app.get("/api/demo/{slug}")
async def api_get_demo(slug: str):
    """
    Returns the BusinessData JSON for a demo slug.
    """
    print(f"[API] LOOKING FOR SLUG: {slug}")
    try:
        demo_files = os.listdir(DEMOS_DIR)
        print(f"[API] FILES: {demo_files}")
    except Exception as e:
        print(f"[API] Could not list demos dir: {e}")
    data = load_demo_data(slug)
    if data is None:
        print(f"[API] Demo not found: {slug}")
        return JSONResponse(
            {"error": f"Demo '{slug}' not found. Generate it first."},
            status_code=404,
        )
    print(f"[API] Demo found: {slug}")
    return JSONResponse(data)


# ── Demo: generate on-demand ──────────────────────────────────────────────────

@app.post("/generate-demo/{slug}")
async def generate_demo(slug: str, force: bool = False):
    """
    Build BusinessData and persist to data/demos/{slug}.json.
    The HTML page is served directly by the /demo/{slug} route on this server.
    Skips if already generated unless force=true.
    """
    if demo_exists(slug) and not force:
        return JSONResponse({"ok": True, "slug": slug,
                             "state": get_demo_state(slug), "skipped": True})

    lead, industry, _ = get_lead_by_slug(slug)
    if not lead:
        return JSONResponse({"ok": False, "error": "Lead not found"}, status_code=404)

    try:
        bd = build_business_data(lead, industry)
        save_demo(slug, bd)
        return JSONResponse({
            "ok":       True,
            "slug":     slug,
            "state":    "generated",
            "demo_url": f"{SITE_URL}/demo/{slug}",
        })
    except Exception as e:
        print(f"[Dashboard] generate_demo error ({slug}): {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── Demo: bulk generate ───────────────────────────────────────────────────────

@app.post("/bulk-generate")
async def bulk_generate(request: Request, background_tasks: BackgroundTasks):
    body  = await request.json()
    slugs = body.get("slugs", [])
    if not slugs:
        return JSONResponse({"ok": False, "error": "No slugs provided"}, status_code=400)

    all_leads, industry, _ = load_latest_leads()
    leads_map = {l.get("slug", ""): (l, industry) for l in all_leads}

    queued = 0
    for slug in slugs:
        if slug in leads_map and not demo_exists(slug):
            lead, ind = leads_map[slug]
            background_tasks.add_task(_generate_one, slug, lead, ind)
            queued += 1

    return JSONResponse({"ok": True, "queued": queued, "total": len(slugs)})


def _generate_one(slug: str, lead: dict, industry: str):
    try:
        bd = build_business_data(lead, industry)
        save_demo(slug, bd)
        print(f"[BulkGen] ✓ {slug}")
    except Exception as e:
        print(f"[BulkGen] ✗ {slug}: {e}")


# ── Demo: approve ─────────────────────────────────────────────────────────────

@app.post("/approve/{slug}")
async def approve_demo(slug: str):
    if not demo_exists(slug):
        return JSONResponse({"ok": False, "error": "Demo not generated yet"}, status_code=400)
    ok = set_demo_state(slug, "approved")
    return JSONResponse({"ok": ok, "slug": slug, "state": "approved",
                         "demo_url": f"{SITE_URL}/demo/{slug}"})


# ── Health / debug ────────────────────────────────────────────────────────────

@app.get("/debug/demos")
async def debug_demos():
    """List all demo JSON files currently stored on this server's filesystem."""
    try:
        return {"files": sorted(os.listdir(DEMOS_DIR))}
    except Exception as e:
        return {"error": str(e)}


@app.get("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/routes")
async def list_routes():
    return [route.path for route in app.routes]


@app.get("/health")
async def health():
    return {"status": "ok", "site_url": SITE_URL}
