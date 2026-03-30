import os
import asyncio
import requests as _requests
from fastapi import FastAPI, Request, Form, BackgroundTasks, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
# CORSMiddleware intentionally not imported — all clients are same-origin

from src.pipeline import run_pipeline
from src.storage import (
    load_latest_leads, load_latest_filter_stats, get_lead_by_slug,
    save_demo, load_demo_data, load_demo_meta,
    get_demo_state, set_demo_state, demo_exists,
    get_all_demo_states,
    ensure_demo_token, get_demo_token, validate_demo_token,
)
from src.transformer import build_business_data
from src.cards import prepare_leads_for_display, filter_leads
from src.config import SITE_URL, DEMOS_DIR, OUTPUT_DIR, CACHE_DIR, HERO_IMAGES_DIR
from src.imagegen import generate_hero_image, cache_hero_from_photos
from src.outreach import generate_message, generate_followup
from datetime import datetime as _dt
from src.tracking import (
    get_status, update_status, get_all_entries,
    followup_needed, OUTREACH_STATUSES, STATUS_LABELS,
    update_lead_action, get_lead_activities, get_days_since_last_action,
)
import re
from urllib.parse import quote as _url_quote
from src.auth import require_auth, auth_enabled, ADMIN_PASSWORD, AuthRequired

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

# Serve AI-generated hero images from disk as permanent static assets
os.makedirs(HERO_IMAGES_DIR, exist_ok=True)
app.mount("/static/hero-images", StaticFiles(directory=HERO_IMAGES_DIR), name="hero-images")

# ── Auth: global exception handler ────────────────────────────────────────────
# When any route calls require_auth(request) and the cookie is missing/wrong,
# AuthRequired is raised here and converted to a 302 → /login.
@app.exception_handler(AuthRequired)
async def _auth_required_handler(request: Request, exc: AuthRequired):
    return RedirectResponse(url="/login", status_code=302)

# ── Auth: HTTP middleware (defence-in-depth) ──────────────────────────────────
# Lets /demo/, /login, /logout, and /static/ through without checking the
# session cookie so that client-facing demo pages remain publicly accessible
# while everything else is blocked at the network layer.
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Always-public paths: demo pages, login/logout, static assets
    if (
        path.startswith("/demo/")
        or path in ("/login", "/logout")
        or path.startswith("/static/")
    ):
        return await call_next(request)
    # For all other paths, enforce session cookie when auth is enabled
    if auth_enabled():
        session = request.cookies.get("session")
        if session != ADMIN_PASSWORD:
            return RedirectResponse(url="/login", status_code=302)
    return await call_next(request)


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
    if auth_enabled():
        print("[Startup] 🔒 Auth ENABLED — ADMIN_PASSWORD is set.")
    else:
        print("[Startup] ⚠  Auth DISABLED — set ADMIN_PASSWORD env var to protect the app.")

_last_search: dict = {"industry": "", "location": "", "running": False, "error": ""}


# ── Auth: login page ───────────────────────────────────────────────────────────

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Login — Opportunity Engine</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0f1117; color: #e4e6f0;
    font-family: 'Inter', system-ui, sans-serif;
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
  }
  .card {
    background: #1a1d27; border: 1px solid #2d3148;
    border-radius: 14px; padding: 2.5rem 2rem; width: 100%; max-width: 360px;
  }
  .brand { font-size: 1.1rem; font-weight: 800; margin-bottom: 0.3rem; }
  .brand span { color: #6c63ff; }
  .sub { font-size: 0.8rem; color: #8b8fa8; margin-bottom: 2rem; }
  label { display: block; font-size: 0.75rem; font-weight: 600; color: #8b8fa8;
          text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 0.4rem; }
  input[type="password"] {
    width: 100%; background: #0f1117; border: 1px solid #2d3148;
    border-radius: 7px; padding: 0.72rem 1rem; color: #e4e6f0;
    font-size: 0.9rem; font-family: inherit; outline: none;
    transition: border-color 0.2s; margin-bottom: 1.1rem;
  }
  input[type="password"]:focus { border-color: #6c63ff; }
  button {
    width: 100%; background: #6c63ff; color: #fff;
    border: none; border-radius: 7px; padding: 0.75rem;
    font-size: 0.9rem; font-weight: 700; font-family: inherit;
    cursor: pointer; transition: opacity 0.18s;
  }
  button:hover { opacity: 0.85; }
  .err { color: #ff6b6b; font-size: 0.8rem; margin-bottom: 1rem; }
</style>
</head>
<body>
<div class="card">
  <div class="brand">🎯 Opportunity <span>Engine</span></div>
  <div class="sub">Private dashboard — sign in to continue</div>
  {error_block}
  <form method="POST" action="/login">
    <label for="password">Password</label>
    <input type="password" id="password" name="password"
           placeholder="Enter admin password" autofocus required />
    <button type="submit">Sign in →</button>
  </form>
</div>
</body>
</html>"""


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login form. Already-logged-in users are bounced to /."""
    if auth_enabled():
        session = request.cookies.get("session")
        if session == ADMIN_PASSWORD:
            return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(_LOGIN_HTML.format(error_block=""))


@app.post("/login")
async def login(password: str = Form(...)):
    """Validate password, set session cookie, redirect to dashboard."""
    if not auth_enabled() or password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="session",
            value=password,
            httponly=True,
            samesite="lax",
        )
        return response
    error_block = '<p class="err">⚠ Incorrect password — try again.</p>'
    return HTMLResponse(
        _LOGIN_HTML.format(error_block=error_block),
        status_code=401,
    )


@app.get("/logout")
async def logout():
    """Clear the session cookie and redirect to the login page."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response


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
    followup_only: bool = False,  # show only leads with 2+ days since last action
):
    require_auth(request)
    leads, industry, location = load_latest_leads()
    leads = prepare_leads_for_display(leads)

    # ── Merge tracking + outreach data into every lead ────────────────────
    tracking = get_all_entries()
    today    = _dt.utcnow().date().isoformat()

    for lead in leads:
        slug  = lead.get("slug", "")
        entry = tracking.get(slug, {})
        phone = lead.get("phone", "")

        lead["outreach_status"]        = entry.get("status", "new")
        lead["followup_nudge"]         = followup_needed(entry) if entry else None
        lead["followup"]               = lead["followup_nudge"]   # alias used in template
        lead["last_action_at"]         = entry.get("last_action_at")
        lead["stage"]                  = entry.get("stage", "NEW")
        lead["days_since_last_action"] = get_days_since_last_action(entry)

        # WhatsApp confidence fallback for leads fetched before the field existed
        if "whatsapp_confidence" not in lead:
            lead["whatsapp_confidence"] = 1 if lead.get("has_whatsapp") else 0

        # Ensure new WA fields exist even on old cached leads (safe defaults)
        lead.setdefault("whatsapp_number",    None)
        lead.setdefault("whatsapp_source",    None)
        lead.setdefault("whatsapp_clickable", False)

        # Prefer the detected whatsapp_number for send URLs; fall back to maps phone
        wa_phone = lead.get("whatsapp_number") or phone
        if wa_phone:
            lead["whatsapp_send_url"]     = build_whatsapp_url(wa_phone, generate_message(lead))
            lead["whatsapp_followup_url"] = build_whatsapp_url(wa_phone, generate_followup(lead))
            lead["followup_message"]      = generate_followup(lead)
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

    if followup_only:
        filtered = [
            l for l in filtered
            if l.get("stage") != "CLOSED"
            and l.get("days_since_last_action") is not None
            and l["days_since_last_action"] >= 2
        ]
        # Sort oldest-first (highest days first)
        filtered.sort(key=lambda l: -(l.get("days_since_last_action") or 0))

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

    # ── Activity-based follow-up counts (new tracker) ─────────────────────
    count_due = sum(
        1 for e in tracking.values()
        if e.get("stage", "NEW") != "CLOSED"
        and get_days_since_last_action(e) in (2, 3)
    )
    count_overdue = sum(
        1 for e in tracking.values()
        if e.get("stage", "NEW") != "CLOSED"
        and (get_days_since_last_action(e) or -1) >= 4
    )

    # ── Ephemeral storage warning ─────────────────────────────────────────
    ephemeral_warning = bool(os.getenv("RENDER") and not os.getenv("PERSISTENT_DEMOS_DIR"))

    # ── Filter quality metrics ────────────────────────────────────────────
    filter_stats       = load_latest_filter_stats()
    raw_count          = filter_stats.get("raw", 0)
    filtered_total     = filter_stats.get("filtered", 0)
    filter_pct         = round(filtered_total / raw_count * 100) if raw_count else None
    expanded_search    = bool(filter_stats.get("expanded", False))
    expanded_locations = filter_stats.get("expanded_locations", [])
    low_confidence     = bool(
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
        "followup_only":     followup_only,
        "running":           _last_search["running"],
        "error":             _last_search["error"],
        "site_url":          SITE_URL,
        "ephemeral_warning": ephemeral_warning,
        "raw_count":         raw_count,
        "filtered_total":    filtered_total,
        "filter_pct":        filter_pct,
        "low_confidence":       low_confidence,
        "expanded_search":      expanded_search,
        "expanded_locations":   expanded_locations,
        "followup_count":    followup_count,
        "sent_today":        sent_today,
        "followups_due":     followups_due,
        "count_due":         count_due,
        "count_overdue":     count_overdue,
        "outreach_statuses": list(OUTREACH_STATUSES),
        "status_labels":     STATUS_LABELS,
    })


# ── Search ────────────────────────────────────────────────────────────────────

@app.get("/search")
async def search_page(request: Request):
    """
    GET /search — browser-safe redirect back to the dashboard home.
    Prevents a 405 when someone navigates directly to /search in the address bar.
    """
    require_auth(request)
    return RedirectResponse(url="/", status_code=302)


@app.post("/search")
async def search(
    request: Request,
    background_tasks: BackgroundTasks,
    industry: str = Form(...),
    location: str = Form(...),
):
    require_auth(request)
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
async def status(request: Request):
    require_auth(request)
    return {"running": _last_search["running"], "error": _last_search["error"]}


# ── Lead detail ───────────────────────────────────────────────────────────────

@app.get("/lead/{slug}", response_class=HTMLResponse)
async def lead_detail(request: Request, slug: str):
    require_auth(request)
    lead, industry, location = get_lead_by_slug(slug)
    if not lead:
        return HTMLResponse("<h1>Lead not found</h1>", status_code=404)

    outreach_status   = get_status(slug)
    tracking_entry    = get_all_entries().get(slug, {})
    outreach_msg      = generate_message(lead)
    whatsapp_send_url = build_whatsapp_url(lead.get("phone", ""), outreach_msg)
    return templates.TemplateResponse("lead.html", {
        "request":                request,
        "lead":                   lead,
        "industry":               industry,
        "location":               location,
        "demo_state":             get_demo_state(slug),
        "demo_meta":              load_demo_meta(slug),
        "site_url":               SITE_URL,
        "outreach_message":       outreach_msg,
        "whatsapp_send_url":      whatsapp_send_url,
        "outreach_status":        outreach_status,
        "outreach_statuses":      list(OUTREACH_STATUSES),
        "status_labels":          STATUS_LABELS,
        "activity_log":           get_lead_activities(slug),
        "days_since_last_action": get_days_since_last_action(tracking_entry),
        "last_action_at":         tracking_entry.get("last_action_at"),
        "stage":                  tracking_entry.get("stage", "NEW"),
        "demo_token":             get_demo_token(slug) or "",
    })


# ── Outreach tracking ─────────────────────────────────────────────────────────

@app.post("/track/{slug}")
async def track_lead(request: Request, slug: str, status: str = Form(...)):
    """Update the outreach status for a lead and redirect back to lead detail."""
    require_auth(request)
    try:
        update_status(slug, status)
        if status == "closed":
            update_lead_action(slug, "CLOSED")
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return RedirectResponse(url=f"/lead/{slug}", status_code=303)


@app.post("/track-send/{slug}")
async def track_send(request: Request, slug: str):
    """
    Mark lead as 'contacted' via WhatsApp (called by JS before opening wa.me).
    Returns JSON so the JS can proceed without a full page reload.
    """
    require_auth(request)
    try:
        update_status(slug, "contacted", channel="whatsapp")
        update_lead_action(slug, "SENT")
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True})


# ── Activity tracking endpoints ───────────────────────────────────────────────

@app.post("/add-note/{slug}")
async def add_note(request: Request, slug: str, note: str = Form(...)):
    """Add a freetext note to a lead's activity log and redirect back to lead detail."""
    require_auth(request)
    update_lead_action(slug, "NOTE", note=note)
    return RedirectResponse(url=f"/lead/{slug}", status_code=303)


@app.post("/track-followup/{slug}")
async def track_followup(request: Request, slug: str):
    """Record a manual follow-up action (JSON response for JS callers)."""
    require_auth(request)
    update_lead_action(slug, "FOLLOW_UP")
    return JSONResponse({"ok": True})


@app.post("/close-lead/{slug}")
async def close_lead(request: Request, slug: str):
    """Close a lead: update outreach status to 'closed' and record a CLOSED activity."""
    require_auth(request)
    try:
        update_status(slug, "closed")
        update_lead_action(slug, "CLOSED")
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True})


@app.get("/api/leads/followups")
async def leads_followups_api(request: Request):
    """
    Return counts of active (non-CLOSED) leads due for follow-up.
      count_due     — leads where lastActionAt is 2–3 days ago
      count_overdue — leads where lastActionAt is 4+ days ago
    """
    require_auth(request)
    entries = get_all_entries()
    count_due = sum(
        1 for e in entries.values()
        if e.get("stage", "NEW") != "CLOSED"
        and get_days_since_last_action(e) in (2, 3)
    )
    count_overdue = sum(
        1 for e in entries.values()
        if e.get("stage", "NEW") != "CLOSED"
        and (get_days_since_last_action(e) or -1) >= 4
    )
    return JSONResponse({"count_due": count_due, "count_overdue": count_overdue})


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
    """Wrap an external image URL with our server-side proxy endpoint.
    Local/static paths (AI-generated images) are returned as-is — no proxy needed.
    """
    if not img_url:
        return ""
    if img_url.startswith("/"):   # already a local static path
        return img_url
    return f"/img-proxy?url={_url_quote(img_url, safe='')}"


# Category-keyed Unsplash hero fallbacks (permanent CDN URLs — never expire)
_HERO_FALLBACKS: dict[str, str] = {
    "cafe":       "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=1920&q=80",
    "coffee":     "https://images.unsplash.com/photo-1495474472359-35827269479f?w=1920&q=80",
    "restaurant": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=1920&q=80",
    "bike":       "https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=1920&q=80",
    "cycle":      "https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=1920&q=80",
    "salon":      "https://images.unsplash.com/photo-1560869713-7d0a29430803?w=1920&q=80",
    "barber":     "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=1920&q=80",
    "gym":        "https://images.unsplash.com/photo-1534438327167-af6e4e82fc16?w=1920&q=80",
    "bakery":     "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=1920&q=80",
    "spa":        "https://images.unsplash.com/photo-1540555700478-4be290d57689?w=1920&q=80",
    "guesthouse": "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=1920&q=80",
    "hotel":      "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=1920&q=80",
}
_HERO_FALLBACK_DEFAULT = "https://images.unsplash.com/photo-1497366216548-37526070297c?w=1920&q=80"


def _hero_fallback_url(category: str, industry: str = "") -> str:
    """Return a permanent Unsplash hero image URL for a given category/industry."""
    search = (f"{category} {industry}").lower()
    for key, url in _HERO_FALLBACKS.items():
        if key in search:
            return url
    return _HERO_FALLBACK_DEFAULT


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
async def render_demo(request: Request, slug: str, token: str = ""):
    """
    Render the public-facing business demo page.

    Access rules:
      • Authenticated admin (valid session cookie) → always allowed.
      • Unauthenticated visitor → must supply ?token=<valid_token>.
      • Invalid / expired token → 404 (don't leak that the demo exists).
    """
    # Check whether the caller is an authenticated admin
    is_admin = (not auth_enabled()) or (
        request.cookies.get("session") == ADMIN_PASSWORD
    )

    if not is_admin:
        # Public access — validate the share token
        if not validate_demo_token(slug, token):
            return HTMLResponse(
                "<html><body style='font-family:Arial;padding:40px;"
                "background:#0d0f14;color:#f0f0f0'>"
                "<h1>Not found</h1>"
                "<p>This demo link is invalid or has expired.</p>"
                "</body></html>",
                status_code=404,
            )

    data = load_demo_data(slug)
    if data is None:
        return HTMLResponse(
            "<html><body style='font-family:Arial;padding:40px;background:#0d0f14;color:#f0f0f0'>"
            f"<h1>Demo not found</h1>"
            f"<p>No demo has been generated for <code>{slug}</code> yet.</p>"
            + (f"<p><a href='/' style='color:#c9a96e'>← Back to dashboard</a></p>" if is_admin else "")
            + "</body></html>",
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

    # Best hero quote: prefer structured review_intel pick, fall back to short snippet
    _ri = data.get("review_intel") or {}
    hero_quote = _ri.get("top_review_quote", "") or hero_review

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
        # Branding
        "color_primary":  colors.get("primary", "#0D1520"),
        "color_accent":   colors.get("accent",  "#C9A96E"),
        "color_bg":       colors.get("bg",      "#F8F7F4"),
        "color_surface":  colors.get("surface", "#EDE8DE"),
        "about_headline": data.get("about_headline", ""),
        "about_text":     data.get("about_text", ""),
        "opening_hours":  data.get("opening_hours", []),
        "feature_stat":   data.get("feature_stat", "Locally Loved"),
        "feature_pills":  data.get("feature_pills", []),
        "cta_label":      data.get("cta_label", "Get in Touch"),
        "promo":          data.get("promo", ""),
        "cta_line":       data.get("cta_line", ""),
        "hero_review":    hero_review,
        "hero_quote":     hero_quote,
        # Client-facing highlights
        "what_people_love": data.get("what_people_love", []),
        # Industry pack + pack-specific content
        "industry_pack":    data.get("industry_pack", "default"),
        "hero_description": data.get("hero_description", ""),
        "show_gallery":     data.get("show_gallery", False),
        # Signal-based fields (real review text extraction)
        "hero_line":        data.get("hero_line") or data.get("hero_description", ""),
        "review_phrases":   data.get("review_phrases", []),
        # Image mode: "real" | "mixed" | "fallback" (template uses to mute fallbacks)
        "image_mode":       data.get("image_mode", "real"),
        # Permanent Unsplash fallback shown if the proxied hero image fails to load
        "hero_image_fallback": _hero_fallback_url(
            data.get("category", ""), data.get("industry", "")
        ),
        # Menu module
        "menu_enabled":   menu_enabled,
        "menu":           menu_data or {},
    })


# ── API: serve BusinessData JSON ──────────────────────────────────────────────

@app.get("/api/demo/{slug}")
async def api_get_demo(request: Request, slug: str):
    """
    Returns the BusinessData JSON for a demo slug.
    """
    require_auth(request)
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
async def generate_demo(request: Request, slug: str, force: bool = False):
    require_auth(request)
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

        # Hero image: try real photo first (downloads + caches to avoid URL expiry),
        # then fall back to DALL-E 3 if no real photo is available.
        hero_img = (
            cache_hero_from_photos(slug, lead.get("photos") or [])
            or generate_hero_image(slug, bd)
        )
        if hero_img:
            bd["hero_image"] = hero_img

        save_demo(slug, bd)
        update_lead_action(slug, "GENERATED")
        share_token = ensure_demo_token(slug)
        return JSONResponse({
            "ok":        True,
            "slug":      slug,
            "state":     "generated",
            "demo_url":  f"{SITE_URL}/demo/{slug}",
            "share_url": f"{SITE_URL}/demo/{slug}?token={share_token}",
            "token":     share_token,
        })
    except Exception as e:
        print(f"[Dashboard] generate_demo error ({slug}): {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── Demo: bulk generate ───────────────────────────────────────────────────────

@app.post("/bulk-generate")
async def bulk_generate(request: Request, background_tasks: BackgroundTasks):
    require_auth(request)
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
        # Hero image: try real photo first, fall back to DALL-E 3
        hero_img = (
            cache_hero_from_photos(slug, lead.get("photos") or [])
            or generate_hero_image(slug, bd)
        )
        if hero_img:
            bd["hero_image"] = hero_img
        save_demo(slug, bd)
        update_lead_action(slug, "GENERATED")
        ensure_demo_token(slug)
        print(f"[BulkGen] ✓ {slug}")
    except Exception as e:
        print(f"[BulkGen] ✗ {slug}: {e}")


# ── Demo: approve ─────────────────────────────────────────────────────────────

@app.post("/approve/{slug}")
async def approve_demo(request: Request, slug: str):
    require_auth(request)
    if not demo_exists(slug):
        return JSONResponse({"ok": False, "error": "Demo not generated yet"}, status_code=400)
    ok = set_demo_state(slug, "approved")
    share_token = ensure_demo_token(slug)
    return JSONResponse({
        "ok":        ok,
        "slug":      slug,
        "state":     "approved",
        "demo_url":  f"{SITE_URL}/demo/{slug}",
        "share_url": f"{SITE_URL}/demo/{slug}?token={share_token}",
        "token":     share_token,
    })


# ── Health / debug ────────────────────────────────────────────────────────────

@app.get("/debug/demos")
async def debug_demos(request: Request):
    """List all demo JSON files currently stored on this server's filesystem."""
    require_auth(request)
    try:
        return {"files": sorted(os.listdir(DEMOS_DIR))}
    except Exception as e:
        return {"error": str(e)}


@app.get("/demo-direct", response_class=HTMLResponse)
async def demo_direct(request: Request):
    require_auth(request)
    """
    GET /demo-direct

    Bypasses the search → lead → generate flow entirely.
    Builds and renders ONE demo immediately using:
      1. The first already-generated demo (if any exist)
      2. The best scored lead from the latest search (built on the fly)
      3. The hardcoded fallback demo object (no data needed at all)

    No filtering. No validation. Always produces a visible page.
    """
    from src.pipeline import _FALLBACK_LEAD
    from src.transformer import build_business_data
    from urllib.parse import quote as _q

    # ── Try existing generated demos first ──────────────────────────────────
    try:
        demo_files = [f for f in os.listdir(DEMOS_DIR) if f.endswith(".json")]
    except Exception:
        demo_files = []

    data = None

    if demo_files:
        slug = demo_files[0].replace(".json", "")
        data = load_demo_data(slug)
        print(f"[DemoDirect] Using existing demo: {slug}")

    # ── Try building from latest leads ──────────────────────────────────────
    if data is None:
        try:
            leads, industry, _ = load_latest_leads()
            if leads:
                lead    = leads[0]
                data    = build_business_data(lead, industry)
                print(f"[DemoDirect] Built from lead: {lead.get('name', '?')}")
        except Exception as e:
            print(f"[DemoDirect] Could not build from leads: {e}")

    # ── Fall back to hardcoded demo object ───────────────────────────────────
    if data is None:
        print("[DemoDirect] Using hardcoded fallback demo object")
        fb       = dict(_FALLBACK_LEAD)
        photos   = fb.get("photos", [])
        reviews  = fb.get("reviews", [])
        data = {
            "name":           fb["name"],
            "city":           fb.get("city", ""),
            "address":        fb.get("address", ""),
            "phone":          fb.get("phone", ""),
            "rating":         fb["rating"],
            "reviews_count":  fb["reviews_count"],
            "category":       fb.get("category", ""),
            "google_maps_url": "",
            "hero_image":     photos[0] if photos else "",
            "gallery_images": photos[1:5],
            "show_gallery":   True,
            "image_mode":     "real",
            "reviews":        reviews,
            "has_real_reviews": True,
            "map_embed":      "",
            "tagline":        "Your local bike experts",
            "services":       ["Bike Sales", "Servicing", "Repairs", "Accessories"],
            "colors":         {"primary": "#0D1520", "accent": "#C9A96E",
                               "bg": "#F8F7F4", "surface": "#EDE8DE"},
            "about_headline": "Trusted by local riders",
            "about_text":     f"{fb['name']} is a trusted local bike shop in {fb.get('city', 'Durban')}, known for knowledgeable staff and fast turnaround.",
            "feature_stat":   "Locally Loved",
            "feature_pills":  [],
            "cta_label":      "Get in Touch",
            "promo":          "",
            "cta_line":       "",
            "review_intel":   {},
            "what_people_love": ["Knowledgeable staff", "Quick turnaround",
                                 "Friendly service", "Great selection"],
            "industry_pack":  "default",
            "hero_description": f"Trusted local bike shop in {fb.get('city', 'Durban')}",
            "hero_line":      f"Trusted local bike shop in {fb.get('city', 'Durban')}",
            "review_phrases": ["Knowledgeable staff who really understand cycling",
                               "Quick turnaround on every service"],
            "has_website":    False,
            "has_whatsapp":   False,
            "place_id":       "",
        }

    # ── Render using the standard demo template ──────────────────────────────
    phone = data.get("phone", "")
    name  = data.get("name", "Demo")
    wa_url = ""
    if phone:
        import re as _re
        digits = _re.sub(r"\D", "", phone)
        if digits.startswith("0") and len(digits) == 10:
            digits = "27" + digits[1:]
        wa_url = f"https://wa.me/{digits}?text={_q(f'Hi {name}, I saw your listing!')}"

    colors          = data.get("colors") or {}
    raw_gallery     = data.get("gallery_images", [])
    all_gallery     = [_proxy_url(u) for u in raw_gallery if u]
    reviews         = data.get("reviews", [])

    _ri         = data.get("review_intel") or {}
    hero_quote  = _ri.get("top_review_quote", "") or ""

    def _hero_review(revs):
        pool = [r for r in revs if int(r.get("rating", 0)) >= 5] or revs
        for r in pool:
            text = r.get("text", "").strip()
            if len(text) >= 8:
                words = text.split(".")[0].split()
                return " ".join(words[:10]) + ("…" if len(words) > 10 else "")
        return ""

    return templates.TemplateResponse("demo.html", {
        "request":          request,
        "name":             name,
        "tagline":          data.get("tagline", ""),
        "category":         data.get("category", ""),
        "city":             data.get("city", ""),
        "address":          data.get("address", ""),
        "phone":            phone,
        "rating":           data.get("rating", ""),
        "reviews_count":    data.get("reviews_count", ""),
        "hero_image":       _proxy_url(data.get("hero_image", "")),
        "gallery_images":   all_gallery,
        "services":         data.get("services", []),
        "reviews":          reviews,
        "google_maps_url":  data.get("google_maps_url", ""),
        "map_embed":        data.get("map_embed", ""),
        "wa_url":           wa_url,
        "color_primary":    colors.get("primary", "#0D1520"),
        "color_accent":     colors.get("accent",  "#C9A96E"),
        "color_bg":         colors.get("bg",      "#F8F7F4"),
        "color_surface":    colors.get("surface", "#EDE8DE"),
        "about_headline":   data.get("about_headline", ""),
        "about_text":       data.get("about_text", ""),
        "opening_hours":    data.get("opening_hours", []),
        "feature_stat":     data.get("feature_stat", "Locally Loved"),
        "feature_pills":    data.get("feature_pills", []),
        "cta_label":        data.get("cta_label", "Get in Touch"),
        "promo":            data.get("promo", ""),
        "cta_line":         data.get("cta_line", ""),
        "hero_review":      _hero_review(reviews),
        "hero_quote":       hero_quote,
        "what_people_love": data.get("what_people_love", []),
        "industry_pack":    data.get("industry_pack", "default"),
        "hero_description": data.get("hero_description", ""),
        "show_gallery":     data.get("show_gallery", True),
        "hero_line":        data.get("hero_line") or data.get("hero_description", ""),
        "review_phrases":   data.get("review_phrases", []),
        "image_mode":       data.get("image_mode", "real"),
        "hero_image_fallback": _hero_fallback_url(
            data.get("category", ""), data.get("industry", "")
        ),
        "menu_enabled":     False,
        "menu":             {},
    })


@app.get("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/routes")
async def list_routes():
    return [route.path for route in app.routes]


@app.get("/health")
async def health():
    return {"status": "ok", "site_url": SITE_URL}


# ── Guardrail Debug Dashboard ──────────────────────────────────────────────────

@app.get("/debug/guardrails", response_class=HTMLResponse)
async def debug_guardrails(request: Request):
    """
    Per-business guardrail report.

    Shows for each lead:
      - images:  total / valid / AI-added
      - reviews: total / accepted
      - status:  PASSED / FAILED
      - reason:  why it failed (if applicable)
    """
    require_auth(request)
    from src.guardrails import validate_image, compress_review, validate_business
    from src.enhancer  import generate_support_images

    leads, industry, location = load_latest_leads()
    filter_stats = load_latest_filter_stats()

    rows = []
    for lead in leads:
        name   = lead.get("name", "<unknown>")
        photos = lead.get("photos") or []
        reviews = lead.get("reviews") or []

        # Image counts
        if photos and isinstance(photos[0], dict):
            valid_images = sum(1 for img in photos if validate_image(img))
        else:
            valid_images = len([p for p in photos if p])
        total_images = len(photos)

        # AI support images (how many would be added)
        ai_images = len(generate_support_images(
            lead.get("category", industry),
            real_image_count=valid_images,
        ))

        # Review counts
        total_reviews = len(reviews)
        accepted_reviews = sum(
            1 for r in reviews
            if compress_review(r.get("text", "") if isinstance(r, dict) else str(r))
        )

        # Pass/fail
        passed = validate_business(lead)
        if passed:
            status = "PASSED"
            reason = ""
        else:
            status = "FAILED"
            # Determine primary reason
            try:
                rating = float(lead.get("rating") or 0)
            except (TypeError, ValueError):
                rating = 0.0

            if not name.strip():
                reason = "data incomplete — missing name"
            elif rating < 4.0:
                reason = f"data incomplete — rating {rating:.1f} < 4.0"
            elif valid_images < 5:
                reason = f"not enough valid images ({valid_images}/5)"
            elif accepted_reviews < 2:
                reason = f"reviews too weak ({accepted_reviews}/2)"
            else:
                reason = "failed validation"

        rows.append({
            "name":             name,
            "total_images":     total_images,
            "valid_images":     valid_images,
            "ai_images":        ai_images,
            "total_reviews":    total_reviews,
            "accepted_reviews": accepted_reviews,
            "status":           status,
            "reason":           reason,
            "rating":           lead.get("rating", "—"),
        })

    passed_count  = sum(1 for r in rows if r["status"] == "PASSED")
    failed_count  = sum(1 for r in rows if r["status"] == "FAILED")

    # ── Build simple HTML table ───────────────────────────────────────────
    def _row_html(r: dict) -> str:
        colour = "#2a6e3f" if r["status"] == "PASSED" else "#8b1a1a"
        border = "2px solid #3a9e5f" if r["status"] == "PASSED" else "2px solid #c0392b"
        reason_cell = f'<span style="color:#c0392b">{r["reason"]}</span>' if r["reason"] else "—"
        return (
            f'<tr style="border-left:{border}">'
            f'<td>{r["name"]}</td>'
            f'<td>{r["total_images"]} / <strong>{r["valid_images"]}</strong> / +{r["ai_images"]}</td>'
            f'<td>{r["total_reviews"]} / <strong>{r["accepted_reviews"]}</strong></td>'
            f'<td>{r["rating"]}</td>'
            f'<td style="color:{colour};font-weight:bold">{r["status"]}</td>'
            f'<td>{reason_cell}</td>'
            f'</tr>'
        )

    rows_html = "\n".join(_row_html(r) for r in rows)
    guardrail_passed  = filter_stats.get("guardrail_passed", "—")
    guardrail_skipped = filter_stats.get("guardrail_skipped", "—")

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Guardrail Debug — {industry} / {location}</title>
  <style>
    body  {{ font-family: Arial, sans-serif; background: #0d0f14; color: #e0e0e0; padding: 24px; }}
    h1    {{ color: #c9a96e; margin-bottom: 4px; }}
    p     {{ color: #888; margin: 0 0 16px; }}
    .summary {{ display: flex; gap: 24px; margin-bottom: 20px; }}
    .chip {{ padding: 8px 16px; border-radius: 6px; font-weight: bold; font-size: 14px; }}
    .pass {{ background: #1a3d2b; color: #4caf50; }}
    .fail {{ background: #3d1a1a; color: #e57373; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th    {{ background: #1a1d24; color: #c9a96e; text-align: left; padding: 10px 12px; }}
    td    {{ padding: 9px 12px; border-bottom: 1px solid #222; }}
    tr:hover td {{ background: #151820; }}
    a     {{ color: #c9a96e; }}
  </style>
</head>
<body>
  <h1>🛡 Guardrail Debug</h1>
  <p>{industry} · {location} · {len(rows)} businesses evaluated</p>
  <div class="summary">
    <div class="chip pass">✅ Passed: {passed_count}</div>
    <div class="chip fail">❌ Failed: {failed_count}</div>
    <div class="chip" style="background:#1a1d24;color:#888">
      Pipeline guardrail — passed: {guardrail_passed} / skipped: {guardrail_skipped}
    </div>
  </div>
  <table>
    <thead>
      <tr>
        <th>Business</th>
        <th>Images (total / valid / AI-added)</th>
        <th>Reviews (total / accepted)</th>
        <th>Rating</th>
        <th>Status</th>
        <th>Reason for failure</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
  <p style="margin-top:24px"><a href="/">← Back to dashboard</a></p>
</body>
</html>"""
    return HTMLResponse(html)
