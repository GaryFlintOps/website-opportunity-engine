"""
outreach.py

Generate a deterministic, confidence-segmented cold-outreach opener.

Key design decisions:
  1. Deterministic per lead — same slug always produces the same message.
     Angle is picked via MD5(slug) so it's stable across page loads,
     follow-ups, and export jobs.

  2. Copy branches on whatsapp_confidence:
       0   = no WhatsApp signals → Chat Close angle (strongest hook)
       1   = weak / unclear      → curiosity angle, softer
       2+  = likely already on WA → website / conversion upgrade angle

Exports:
  generate_message(lead: dict)  -> str
  generate_followup(lead: dict) -> str
"""

import hashlib


# ── Angle hook pools (one pool per confidence tier) ───────────────────────────

# Tier 0 — no WhatsApp at all: lead can't message you instantly
_HOOKS_NO_WA = [
    "People are finding you on Google but have no fast way to message you.",
    "Customers searching for you right now have no direct way to reach out.",
    "Your Google profile gets views, but there's no instant contact path.",
    "You're likely losing enquiries because customers can't message in one tap.",
    "A simple WhatsApp-first flow could turn more profile views into bookings.",
]

# Tier 1 — weak or unclear WhatsApp signal: presence is inconsistent
_HOOKS_WEAK_WA = [
    "Your WhatsApp presence is hard to find — most customers give up.",
    "People can find you but your contact flow isn't conversion-ready.",
    "Your listing could capture more leads with a cleaner message path.",
    "Nearby competitors are making it easier for customers to reach them.",
    "A few quick changes could turn your Google presence into an enquiry engine.",
]

# Tier 2+ — likely already on WhatsApp: pitch website / conversion upgrade
_HOOKS_HAS_WA = [
    "Your Google profile is underperforming compared to nearby competitors.",
    "You have WhatsApp, but your website isn't working hard enough for you.",
    "Most of your profile views aren't converting — here's what's missing.",
    "You're capturing chats but losing the customers who want to browse first.",
    "A proper website would turn your Google traffic into booked appointments.",
]


def _pick_angle(slug: str, pool: list[str]) -> str:
    """Choose deterministically from pool using MD5 of slug as seed."""
    h   = hashlib.md5(slug.encode("utf-8")).hexdigest()
    idx = int(h, 16) % len(pool)
    return pool[idx]


def _format_city(lead: dict) -> str:
    city = (lead.get("city") or "").strip()
    if city:
        return city
    addr = (lead.get("address") or "").strip()
    return addr.split(",")[-1].strip() if addr else "your area"


def generate_message(lead: dict) -> str:
    """
    Build a short, personalised outreach opener.

    Copy branches on whatsapp_confidence:
      0   → Chat Close angle (no website + no WhatsApp = strongest)
      1   → Curiosity / weak presence angle
      2+  → Website/conversion upgrade angle
    """
    slug      = lead.get("slug") or lead.get("name", "lead")
    name      = (lead.get("name") or "there").strip()
    city      = _format_city(lead)
    category  = (lead.get("category") or "business").strip().lower()
    wc        = lead.get("whatsapp_confidence", 0)

    # ── Pick angle pool based on confidence tier ──────────────────────────
    if wc == 0:
        pool = _HOOKS_NO_WA
    elif wc == 1:
        pool = _HOOKS_WEAK_WA
    else:
        pool = _HOOKS_HAS_WA

    hook = _pick_angle(slug, pool)

    # ── Build context-specific body line ──────────────────────────────────
    if wc == 0:
        if not lead.get("website"):
            body = (
                f"I put together a quick demo showing how your {category} in {city} "
                f"could capture more enquiries directly from Google — no website needed to start."
            )
        else:
            body = (
                f"I put together a quick demo showing how your {category} in {city} "
                f"could convert more Google searches into direct messages."
            )
    elif wc == 1:
        body = (
            f"I've already built a quick demo for your {category} in {city} "
            f"that shows what a proper message-first setup could look like."
        )
    else:
        body = (
            f"I've put together a demo showing how your {category} in {city} "
            f"could turn more profile views into booked appointments — "
            f"working alongside your existing WhatsApp."
        )

    # ── Compose final message ─────────────────────────────────────────────
    return (
        f"Hi {name},\n\n"
        f"{hook}\n\n"
        f"{body}\n\n"
        f"Want me to send it through?\n\n"
        f"[Your name]"
    )


def generate_followup(lead: dict) -> str:
    """
    Short follow-up nudge sent 2–3 days after the initial outreach.
    Keeps it warm without restating the pitch — just opens the loop again.
    """
    name = (lead.get("name") or "there").strip()
    return (
        f"Hey {name} — just wanted to follow up on this.\n\n"
        f"Happy to send the demo I mentioned for {name}.\n\n"
        f"Worth a quick look?"
    )
