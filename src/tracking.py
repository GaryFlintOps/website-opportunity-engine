"""
tracking.py

Outreach status tracker backed by SQLite.
One DB file (data/tracking.db) — safer writes, append-only history,
ready for future reporting without changing the public API.

Schema:
  leads_tracking (
    slug           TEXT PRIMARY KEY,
    status         TEXT NOT NULL DEFAULT 'new',
    channel        TEXT,
    history_json   TEXT NOT NULL DEFAULT '[]',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    last_action_at TEXT,
    stage          TEXT DEFAULT 'NEW'
  )

  lead_activity (
    id         TEXT PRIMARY KEY,
    lead_id    TEXT NOT NULL,
    type       TEXT NOT NULL,   -- GENERATED | SENT | NOTE | FOLLOW_UP | CLOSED
    note       TEXT,
    created_at TEXT NOT NULL
  )

Valid statuses (pipeline order):
  new → contacted → replied → no_response → demo_sent → negotiating → closed → not_interested

Valid stages (simplified pipeline):
  NEW → REVIEWED → DEMO_GENERATED → SENT → REPLIED → CLOSED

Valid activity types:
  GENERATED | SENT | NOTE | FOLLOW_UP | CLOSED

Exports:
  get_status(slug)                               -> str
  update_status(slug, status, channel="")        -> None
  get_all_statuses()                             -> dict[str, str]
  get_all_entries()                              -> dict[str, dict]
  followup_needed(entry)                         -> str | None
  update_lead_action(slug, type, note=None)      -> None
  get_lead_activities(slug)                      -> list[dict]
  get_days_since_last_action(entry)              -> int | None
"""

import os
import json
import uuid
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

LEAD_STAGES = (
    "NEW",
    "REVIEWED",
    "DEMO_GENERATED",
    "SENT",
    "REPLIED",
    "CLOSED",
)

ACTIVITY_TYPES = (
    "GENERATED",
    "SENT",
    "NOTE",
    "FOLLOW_UP",
    "CLOSED",
)

# Maps activity type → stage update (None = no stage change)
_ACTIVITY_TO_STAGE: dict[str, str | None] = {
    "GENERATED": "DEMO_GENERATED",
    "SENT":      "SENT",
    "NOTE":      None,
    "FOLLOW_UP": None,
    "CLOSED":    "CLOSED",
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
                slug           TEXT PRIMARY KEY,
                status         TEXT NOT NULL DEFAULT 'new',
                channel        TEXT,
                history_json   TEXT NOT NULL DEFAULT '[]',
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                last_action_at TEXT,
                stage          TEXT DEFAULT 'NEW'
            )
        """)
        # Idempotent migrations: add new columns if they don't exist yet
        for col, defn in [
            ("last_action_at", "TEXT"),
            ("stage",          "TEXT DEFAULT 'NEW'"),
        ]:
            try:
                c.execute(f"ALTER TABLE leads_tracking ADD COLUMN {col} {defn}")
            except Exception:
                pass  # Column already exists — safe to ignore

        # Activity log table
        c.execute("""
            CREATE TABLE IF NOT EXISTS lead_activity (
                id         TEXT PRIMARY KEY,
                lead_id    TEXT NOT NULL,
                type       TEXT NOT NULL,
                note       TEXT,
                created_at TEXT NOT NULL
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
    d = {
        "status":     row["status"],
        "channel":    row["channel"],
        "history":    json.loads(row["history_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    # New columns added via migration — use try/except for safety on old DB snapshots
    try:
        d["last_action_at"] = row["last_action_at"]
    except Exception:
        d["last_action_at"] = None
    try:
        d["stage"] = row["stage"] or "NEW"
    except Exception:
        d["stage"] = "NEW"
    return d


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
            "SELECT slug, status, channel, history_json, created_at, updated_at, "
            "last_action_at, stage "
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


def get_days_since_last_action(entry: dict) -> int | None:
    """
    Return the whole number of days elapsed since the lead's last recorded action.
    Returns None if no action has been recorded yet (last_action_at is NULL).
    """
    last_action = entry.get("last_action_at")
    if not last_action:
        return None
    try:
        ts = datetime.fromisoformat(last_action)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - ts).total_seconds() // 86400)
    except Exception:
        return None


def update_lead_action(slug: str, type: str, note: str | None = None) -> None:
    """
    Record a lead action:
      1. Updates leads_tracking.last_action_at to now()
      2. Updates leads_tracking.stage if the action implies a stage change
      3. Inserts a new record into lead_activity

    Raises ValueError for unrecognised activity types.
    """
    _ensure_db()
    if type not in ACTIVITY_TYPES:
        raise ValueError(f"Invalid activity type '{type}'. Must be one of {ACTIVITY_TYPES}")

    ts           = _now()
    activity_id  = str(uuid.uuid4())
    new_stage    = _ACTIVITY_TO_STAGE.get(type)  # None → no stage change

    with _conn() as c:
        # Ensure a tracking row exists for this slug
        row = c.execute(
            "SELECT slug FROM leads_tracking WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            c.execute("""
                INSERT OR IGNORE INTO leads_tracking
                    (slug, status, channel, history_json, created_at, updated_at, last_action_at, stage)
                VALUES (?, 'new', NULL, '[]', ?, ?, ?, 'NEW')
            """, (slug, ts, ts, ts))

        if new_stage:
            c.execute("""
                UPDATE leads_tracking
                SET last_action_at = ?, stage = ?, updated_at = ?
                WHERE slug = ?
            """, (ts, new_stage, ts, slug))
        else:
            c.execute("""
                UPDATE leads_tracking
                SET last_action_at = ?, updated_at = ?
                WHERE slug = ?
            """, (ts, ts, slug))

        c.execute("""
            INSERT INTO lead_activity (id, lead_id, type, note, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (activity_id, slug, type, note, ts))
        c.commit()

    print(f"[Activity] {slug} → {type}" + (f": {note[:60]}" if note else ""))


def get_lead_activities(slug: str) -> list:
    """Return all activity records for a lead, newest first."""
    _ensure_db()
    with _conn() as c:
        rows = c.execute(
            "SELECT id, type, note, created_at "
            "FROM lead_activity "
            "WHERE lead_id = ? "
            "ORDER BY created_at DESC",
            (slug,),
        ).fetchall()
    return [
        {
            "id":         r["id"],
            "type":       r["type"],
            "note":       r["note"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


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
