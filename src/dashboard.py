import os
from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from src.pipeline import run_pipeline
from src.storage import (
    load_latest_leads, get_lead_by_slug,
    save_demo, load_demo_data, load_demo_meta,
    get_demo_state, set_demo_state, demo_exists,
    get_all_demo_states,
)
from src.transformer import build_business_data
from src.cards import prepare_leads_for_display, filter_leads
from src.config import SITE_URL, DEMOS_DIR

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app       = FastAPI(title="Website Opportunity Engine")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

    return templates.TemplateResponse("index.html", {
        "request":        request,
        "leads":          filtered,
        "total":          len(leads),
        "filtered_count": len(filtered),
        "industry":       industry,
        "location":       location,
        "min_score":      min_score,
        "no_website":     no_website,
        "max_reviews":    max_reviews,
        "running":        _last_search["running"],
        "error":          _last_search["error"],
        "site_url":       SITE_URL,
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


# ── API: serve BusinessData JSON (consumed by Next.js) ───────────────────────

@app.get("/api/demo/{slug}")
async def api_get_demo(slug: str):
    """
    Returns the BusinessData JSON for a demo.
    Called by Next.js SSR at build/request time to render demo pages.
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
    No HTML is generated — Next.js handles rendering.
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

@app.get("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/routes")
async def list_routes():
    return [route.path for route in app.routes]


@app.get("/health")
async def health():
    return {"status": "ok", "site_url": SITE_URL}
