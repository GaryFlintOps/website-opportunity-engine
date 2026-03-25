import os
from fastapi import FastAPI, Request, Form, BackgroundTasks
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
    request: Request,
    min_score: int   = 0,
    no_website: bool = False,
    max_reviews: int = 0,
):
    leads, industry, location = load_latest_leads()
    leads    = prepare_leads_for_display(leads)
    filtered = filter_leads(leads, min_score=min_score, no_website_only=no_website, max_reviews=max_reviews)
    for lead in filtered:
        lead["demo_state"] = get_demo_state(lead.get("slug", ""))

    # Warn if running on Render without a persistent disk
    # (RENDER env var is injected automatically by Render's build system)
    ephemeral_warning = bool(os.getenv("RENDER") and not os.getenv("PERSISTENT_DEMOS_DIR"))

    # Filter quality metrics — carried from the last pipeline run
    filter_stats   = load_latest_filter_stats()
    raw_count      = filter_stats.get("raw", 0)
    filtered_total = filter_stats.get("filtered", 0)
    filter_pct     = round(filtered_total / raw_count * 100) if raw_count else None
    low_confidence = bool(
        filter_stats                                      # stats exist (search has run)
        and (
            filtered_total < 5                            # fewer than 5 results
            or (raw_count > 0 and filtered_total / raw_count < 0.30)  # <30% passed filter
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
        "running":           _last_search["running"],
        "error":             _last_search["error"],
        "site_url":          SITE_URL,
        "ephemeral_warning": ephemeral_warning,
        "raw_count":         raw_count,
        "filtered_total":    filtered_total,
        "filter_pct":        filter_pct,
        "low_confidence":    low_confidence,
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

    return templates.TemplateResponse("lead.html", {
        "request":    request,
        "lead":       lead,
        "industry":   industry,
        "location":   location,
        "demo_state": get_demo_state(slug),
        "demo_meta":  load_demo_meta(slug),
        "site_url":   SITE_URL,
    })


# ── Demo: render HTML page directly from Render ───────────────────────────────

@app.get("/demo/{slug}", response_class=HTMLResponse)
async def render_demo(slug: str):
    """
    Renders the demo page as a self-contained HTML response.
    Served directly from Render — no external frontend required.
    """
    data = load_demo_data(slug)
    if data is None:
        return HTMLResponse(
            f"<html><body style='font-family:Arial;padding:40px;background:#0f1117;color:#e4e6f0'>"
            f"<h1>Demo not found</h1>"
            f"<p>No demo has been generated for <code>{slug}</code> yet.</p>"
            f"<p><a href='/' style='color:#6c63ff'>← Back to dashboard</a></p>"
            f"</body></html>",
            status_code=404,
        )

    name        = data.get("name", "Business")
    tagline     = data.get("tagline", "")
    address     = data.get("address", "")
    phone       = data.get("phone", "")
    website     = data.get("website", "")
    rating      = data.get("rating", "")
    rev_count   = data.get("reviews_count", "")
    category    = data.get("category", "")
    hero_image  = data.get("hero_image", "")
    services    = data.get("services", [])
    reviews     = data.get("reviews", [])
    maps_url    = data.get("google_maps_url", "")
    map_embed   = data.get("map_embed", "")

    services_html = "".join(
        f'<li style="padding:0.5rem 0;border-bottom:1px solid #2d3148">{s}</li>'
        for s in services
    )
    reviews_html = "".join(
        f'<div style="background:#22263a;border:1px solid #2d3148;border-radius:8px;padding:1rem;margin-bottom:0.75rem">'
        f'<div style="color:#f0b429;margin-bottom:0.35rem">{"★" * int(r.get("rating",5))}</div>'
        f'<p style="color:#e4e6f0;font-size:0.9rem;line-height:1.6">{r.get("text","")}</p>'
        f'<p style="color:#8b8fa8;font-size:0.75rem;margin-top:0.5rem">— {r.get("author","")}</p>'
        f'</div>'
        for r in reviews[:4]
    )
    hero_section = (
        f'<img src="{hero_image}" alt="{name}" '
        f'style="width:100%;max-height:380px;object-fit:cover;border-radius:10px;margin-bottom:2rem" />'
        if hero_image else ""
    )
    map_section = (
        f'<div style="margin-top:2rem">'
        f'<iframe src="{map_embed}" width="100%" height="300" style="border:0;border-radius:8px" '
        f'allowfullscreen loading="lazy"></iframe></div>'
        if map_embed else ""
    )
    website_link = (
        f'<a href="{website}" target="_blank" rel="noopener" '
        f'style="color:#6c63ff">{website}</a>'
        if website else '<span style="color:#8b8fa8">No website yet</span>'
    )
    maps_link = (
        f' &nbsp;·&nbsp; <a href="{maps_url}" target="_blank" rel="noopener" '
        f'style="color:#6c63ff">View on Google Maps</a>'
        if maps_url else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{name}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0f1117; color: #e4e6f0;
      font-family: 'Inter', sans-serif; min-height: 100vh;
    }}
    .notice {{
      background: #1a1a2e; color: rgba(255,255,255,.72);
      padding: 0.65rem 1.5rem; font-size: 0.78rem;
      letter-spacing: 0.03em; text-align: center;
      border-bottom: 1px solid rgba(201,169,110,.2);
    }}
    .notice strong {{ color: #c9a96e; }}
    .container {{ max-width: 860px; margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }}
    h1 {{ font-size: clamp(1.9rem,4vw,2.8rem); font-weight: 800; letter-spacing: -0.02em; margin-bottom: 0.4rem; }}
    .tagline {{ color: #8b8fa8; font-size: 1.05rem; margin-bottom: 1.75rem; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:0.6rem; margin-bottom: 2rem; }}
    .chip {{
      background: #22263a; border: 1px solid #2d3148;
      border-radius: 5px; padding: 0.25rem 0.75rem;
      font-size: 0.78rem; color: #8b8fa8;
    }}
    .chip.rating {{ color: #f0b429; }}
    h2 {{ font-size: 1rem; font-weight: 700; color: #8b8fa8;
          letter-spacing: 0.08em; text-transform: uppercase;
          margin: 2rem 0 1rem; }}
    ul {{ list-style: none; padding: 0; color: #e4e6f0; }}
    .footer {{
      margin-top: 3rem; padding-top: 1.5rem;
      border-top: 1px solid #2d3148;
      font-size: 0.78rem; color: #8b8fa8; text-align: center;
    }}
    @media (max-width: 600px) {{ .container {{ padding: 1.5rem 1rem 3rem; }} }}
  </style>
</head>
<body>
  <div class="notice">
    ✦ <strong>This is a preview of how your business could look online</strong>
    &nbsp;—&nbsp; powered by Website Opportunity Engine
  </div>
  <div class="container">
    {hero_section}
    <h1>{name}</h1>
    <p class="tagline">{tagline}</p>
    <div class="meta">
      {f'<span class="chip">{category}</span>' if category else ''}
      {f'<span class="chip rating">★ {rating} ({rev_count} reviews)</span>' if rating else ''}
      {f'<span class="chip">📍 {address}</span>' if address else ''}
      {f'<span class="chip">📞 {phone}</span>' if phone else ''}
    </div>
    {'<h2>Our Services</h2><ul>' + services_html + '</ul>' if services else ''}
    {'<h2>What Customers Say</h2>' + reviews_html if reviews else ''}
    <h2>Find Us</h2>
    <p style="color:#e4e6f0;font-size:0.9rem">
      {address}{maps_link}
    </p>
    <p style="margin-top:0.75rem;font-size:0.9rem">
      🌐 {website_link}
    </p>
    {map_section}
    <div class="footer">
      Want a real website like this? Contact us today.
      &nbsp;·&nbsp; <a href="/" style="color:#6c63ff">← Dashboard</a>
    </div>
  </div>
</body>
</html>"""

    return HTMLResponse(html)


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
