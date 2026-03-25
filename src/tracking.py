"""
tracking.py

Outreach status tracker backed by SQLite.
One DB file (data/tracking.db) — safer writes, append-only history,
ready for future reporting without changing the public API.

Schema:
  leads_tracking (
    slug         TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'new',
    channel      TEXT,
    history_json TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
  )

Valid statuses (pipeline order):
  new → contacted → replied → no_response → demo_sent → negotiating → closed → not_interested

Exports:
  get_status(slug)                          -> str
  update_status(slug, status, channel="")   -> None
  get_all_statuses()                        -> dict[str, str]
  get_all_entries()                         -> dict[str, dict]
  followup_needed(entry)                    -> str | None
"""

import os
import json
import sqlite3
from datetime import datetime, timezone
from src.config import OUTPUT_DIR

DB_PATH      = os.path.join(OUTPUT_DIR, "tracking.db")
LEGACY_JSON  = os.path.join(OUTPUT_DIR, "outreach.json")

OUTREACH_STATUSES = (
    "new",
    "contacted",
    "replied",
    "no_response",
    "demo_sent",
    "negotiating",
    "closed",
    "not_interested",
)

STATUS_LABELS = {
    "new":            "New",
    "contacted":      "Contacted",
    "replied":        "Replied",
    "no_response":    "No Response",
    "demo_sent":      "Demo Sent",
    "negotiating":    "Negotiating",
    "closed":         "Closed",
    "not_interested": "Not Interested",
}


# ── Internal helpers ───────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS leads_tracking (
                slug         TEXT PRIMARY KEY,
                status       TEXT NOT NULL DEFAULT 'new',
                channel      TEXT,
                history_json TEXT NOT NULL DEFAULT '[]',
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        c.commit()


def _migrate_from_json() -> None:
    """One-time migration: import outreach.json into SQLite then rename it."""
    if not os.path.exists(LEGACY_JSON):
        return
    try:
        data = json.loads(open(LEGACY_JSON, encoding="utf-8").read())
        with _conn() as c:
            for slug, entry in data.items():
                ts = entry.get("updated_at") or entry.get("created_at") or _now()
                c.execute("""
                    INSERT OR IGNORE INTO leads_tracking
                        (slug, status, channel, history_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    slug,
                    entry.get("status", "new"),
                    entry.get("channel"),
                    json.dumps(entry.get("history", [])),
                    entry.get("created_at", ts),
                    ts,
                ))
            c.commit()
        os.rename(LEGACY_JSON, LEGACY_JSON + ".migrated")
        print(f"[Tracking] Migrated {len(data)} entries from JSON → SQLite")
    except Exception as e:
        print(f"[Tracking] Migration warning: {e}")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "status":     row["status"],
        "channel":    row["channel"],
        "history":    json.loads(row["history_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def get_status(slug: str) -> str:
    """Return the current outreach status for a slug (defaults to 'new')."""
    _ensure_db()
    with _conn() as c:
        row = c.execute(
            "SELECT status FROM leads_tracking WHERE slug = ?", (slug,)
        ).fetchone()
    return row["status"] if row else "new"


def update_status(slug: str, status: str, channel: str = "") -> None:
    """
    Persist a new status for slug with full audit history.
    Raises ValueError for unrecognised status values.
    """
    _ensure_db()
    if status not in OUTREACH_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of {OUTREACH_STATUSES}"
        )
    ts = _now()
    with _conn() as c:
        row = c.execute(
            "SELECT history_json, created_at FROM leads_tracking WHERE slug = ?",
            (slug,)
        ).fetchone()

        if row:
            history   = json.loads(row["history_json"])
            created   = row["created_at"]
        else:
            history   = []
            created   = ts

        history.append({
            "status":  status,
            "ts":      ts,
            "channel": channel or None,
        })

        c.execute("""
            INSERT INTO leads_tracking (slug, status, channel, history_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                status       = excluded.status,
                channel      = excluded.channel,
                history_json = excluded.history_json,
                updated_at   = excluded.updated_at
        """, (slug, status, channel or None, json.dumps(history), created, ts))
        c.commit()

    print(f"[Tracking] {slug} → {status}" + (f" via {channel}" if channel else ""))


def get_all_statuses() -> dict:
    """Return {slug: status} for every tracked lead."""
    _ensure_db()
    with _conn() as c:
        rows = c.execute(
            "SELECT slug, status FROM leads_tracking"
        ).fetchall()
    return {r["slug"]: r["status"] for r in rows}


def get_all_entries() -> dict:
    """Return full tracking entry dict keyed by slug."""
    _ensure_db()
    with _conn() as c:
        rows = c.execute(
            "SELECT slug, status, channel, history_json, created_at, updated_at "
            "FROM leads_tracking"
        ).fetchall()
    return {r["slug"]: _row_to_dict(r) for r in rows}


def followup_needed(entry: dict) -> str | None:
    """
    Return a nudge string if this entry needs a follow-up action,
    or None if no action is needed yet.

    Rules:
      contacted  + 2+ days old → 'Send follow-up'
      demo_sent  + 3+ days old → 'Check in on demo'
    """
    status     = entry.get("status")
    updated_str = entry.get("updated_at")
    if not status or not updated_str:
        return None
    try:
        updated_at = datetime.fromisoformat(updated_str)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - updated_at).days
    except Exception:
        return None

    if status == "contacted" and age_days >= 2:
        return "Send follow-up"
    if status == "demo_sent" and age_days >= 3:
        return "Check in on demo"
    return None


# ── Lazy initialisation ───────────────────────────────────────────────────────
# _init_db() + _migrate_from_json() are called on first real access so that
# tests can monkeypatch DB_PATH / LEGACY_JSON before any SQLite connection is
# opened.  FastAPI's startup hook triggers the first call in production.

_db_ready = False


def _ensure_db() -> None:
    """Idempotent: init + migrate exactly once per process."""
    global _db_ready
    if _db_ready:
        return
    _init_db()
    _migrate_from_json()
    _db_ready = True
