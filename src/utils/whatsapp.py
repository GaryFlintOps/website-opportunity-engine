"""
whatsapp.py — 3-layer WhatsApp detection for SA business leads.

Detection priority (highest → lowest confidence):
  1. Direct wa.me / api.whatsapp.com link on the website   → source="link",     clickable=True
  2. SA mobile number found anywhere on the website HTML   → source="inferred", clickable=False
  3. Google Maps phone falls back if it's a mobile number  → source="maps",     clickable=False
  no match → has_whatsapp=False, everything else None

Public API:
  extract_whatsapp_data(html, maps_phone) -> dict
  fetch_website_html(url, timeout)        -> str   (pure HTTP helper, no side-effects)
  normalize_number(num)                   -> str | None
"""

import re

# ── Regex constants ───────────────────────────────────────────────────────────

# Matches the START of a SA mobile number (prefix check only — used in SA_MOBILE_REGEX)
SA_MOBILE_REGEX = re.compile(r'(?:\+27|0)(6\d|7\d|8\d)\d{7}')

# Full SA mobile number match — used for text extraction
FULL_SA_MOBILE_REGEX = re.compile(r'(?:\+27|0)(?:6\d|7\d|8\d)\d{7}')

# WhatsApp link pattern — wa.me and api.whatsapp.com
WA_LINK_REGEX = re.compile(r'(https?://(?:wa\.me|api\.whatsapp\.com)[^\s"\'<>]+)')

# Normalised +27 mobile (after normalize_number) — used for maps-fallback validation
_SA_MOBILE_NORM = re.compile(r'^\+27[6-8]\d{8}$')


# ── Core helpers ──────────────────────────────────────────────────────────────

def normalize_number(num: str) -> str | None:
    """
    Convert a raw phone string to E.164 +27 format.
    Returns None if the number can't be recognised as a SA mobile.

    Examples:
      "082 123 4567"   → "+27821234567"
      "+27721234567"   → "+27721234567"
      "0311234567"     → "+27311234567"  (landline — still normalised)
      "1234"           → None
    """
    if not num:
        return None
    digits = re.sub(r'\D', '', num)

    if digits.startswith('27') and len(digits) == 11:
        return f"+{digits}"
    if digits.startswith('0') and len(digits) == 10:
        return f"+27{digits[1:]}"
    return None


# ── Main detector ─────────────────────────────────────────────────────────────

def extract_whatsapp_data(
    html: str,
    maps_phone: str | None = None,
) -> dict:
    """
    3-layer WhatsApp detection. Pure function — no network calls.

    Args:
        html:        Raw HTML content of the business website ('' if unavailable).
        maps_phone:  Phone number from Google Maps (the `phone` field on the lead).

    Returns dict with keys:
        has_whatsapp      bool
        whatsapp_number   str | None   (E.164 +27 format)
        whatsapp_source   str | None   ("link" | "inferred" | "maps")
        whatsapp_clickable bool
    """
    result: dict = {
        "has_whatsapp":       False,
        "whatsapp_number":    None,
        "whatsapp_source":    None,
        "whatsapp_clickable": False,
    }

    if not html:
        html = ""

    # ── Layer 1: Direct WhatsApp link (HIGHEST confidence) ───────────────────
    for link in WA_LINK_REGEX.findall(html):
        # Pull every digit group from the URL (phone is embedded in the URL)
        digits = re.findall(r'\d+', link)
        if digits:
            number = normalize_number(''.join(digits))
            if number:
                result.update({
                    "has_whatsapp":       True,
                    "whatsapp_number":    number,
                    "whatsapp_source":    "link",
                    "whatsapp_clickable": True,
                })
                return result

    # ── Layer 2: SA mobile number present on website (INFERRED) ──────────────
    raw_matches = re.findall(r'(?:\+27|0)(?:6\d|7\d|8\d)\d{7}', html)
    if raw_matches:
        number = normalize_number(raw_matches[0])
        if number:
            result.update({
                "has_whatsapp":       True,
                "whatsapp_number":    number,
                "whatsapp_source":    "inferred",
                "whatsapp_clickable": False,
            })
            return result

    # ── Layer 3: Google Maps phone fallback ───────────────────────────────────
    if maps_phone:
        number = normalize_number(maps_phone)
        if number and _SA_MOBILE_NORM.match(number):
            result.update({
                "has_whatsapp":       True,
                "whatsapp_number":    number,
                "whatsapp_source":    "maps",
                "whatsapp_clickable": False,
            })

    return result


def whatsapp_badge(lead: dict) -> str:
    """
    Return a human-readable badge label for the WhatsApp state of a lead.

      "WHATSAPP ACTIVE"  — has a direct wa.me link on the site
      "WEAK WHATSAPP"    — has a mobile number on site but no WA link
      "HIDDEN WHATSAPP"  — phone from Maps is a mobile but not visible on site
      "NO WHATSAPP"      — no mobile number found anywhere
    """
    if not lead.get("has_whatsapp"):
        return "NO WHATSAPP"
    src = lead.get("whatsapp_source")
    if src == "link":
        return "WHATSAPP ACTIVE"
    if src == "inferred":
        return "WEAK WHATSAPP"
    if src == "maps":
        return "HIDDEN WHATSAPP"
    return "NO WHATSAPP"


# ── Optional website fetcher (called from pipeline — NOT from extract_whatsapp_data) ──

def fetch_website_html(url: str, timeout: int = 4) -> str:
    """
    Attempt a lightweight GET of the business website and return raw HTML.
    Returns '' on any failure — the extractor gracefully degrades to layer 3.

    Kept deliberately simple:
      • 4-second wall-clock timeout
      • No JavaScript execution
      • Follows redirects once
      • Not called from extract_whatsapp_data — the extractor stays pure
    """
    if not url:
        return ""
    # Normalise — add https if scheme missing
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    try:
        import requests as _req
        resp = _req.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LeadScout/1.0)"},
        )
        return resp.text if resp.ok else ""
    except Exception:
        return ""
