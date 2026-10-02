"""
Subscription state machine driven by Stripe-style webhooks (no Stripe account needed to run or test it).

What it guards against (the usual ways a billing backend goes wrong):
  - forged or tampered requests         -> HMAC-SHA256 signature check (Stripe's documented scheme)
  - replayed requests                   -> signature timestamp must be recent
  - the same event delivered twice      -> events are recorded by id and applied once
  - events that arrive out of order     -> an older event never overwrites newer state
  - a crash halfway through an event    -> state change and "event processed" mark are one transaction,
                                           so Stripe's retry is applied cleanly
  - a missed renewal webhook            -> access ends after the period + grace even if no "cancel" arrives
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import time

TOLERANCE = 300          # seconds a signed request stays valid
GRACE_DAYS = 3           # days of access kept after a failed payment (and after a missed renewal)

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY, customer TEXT, email TEXT, plan TEXT, status TEXT,
    current_period_end INTEGER, cancel_at_period_end INTEGER DEFAULT 0,
    past_due_since INTEGER, failed_payments INTEGER DEFAULT 0, last_event_created INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sub_customer ON subscriptions(customer);
CREATE TABLE IF NOT EXISTS processed_events (
    id TEXT PRIMARY KEY, type TEXT, created INTEGER, outcome TEXT
);
"""


class SignatureError(Exception):
    pass


class BadEvent(Exception):
    pass


# ---------- signatures (Stripe scheme: header "t=<unix>,v1=<hex hmac of '<t>.<raw body>'>") ----------

def sign(secret: str, payload: bytes, timestamp: int) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verify(secret: str, payload: bytes, header: str | None, now: float | None = None, tolerance: int = TOLERANCE):
    if not header:
        raise SignatureError("missing Stripe-Signature header")
    pairs = [p.split("=", 1) for p in header.split(",") if "=" in p]
    ts = next((v for k, v in pairs if k == "t"), "")
    sigs = [v for k, v in pairs if k == "v1"]
    if not ts.isdigit() or not sigs:
        raise SignatureError("malformed Stripe-Signature header")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise SignatureError("signature does not match")
    now = time.time() if now is None else now
    if abs(now - int(ts)) > tolerance:
        raise SignatureError("timestamp outside tolerance (possible replay)")


# ---------- database ----------

def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)  # we manage transactions explicitly
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.close()


# ---------- event handlers: (existing row or None, event object, event time) -> columns to change ----------

def _paid(row, obj, created):
    lines = (obj.get("lines") or {}).get("data") or [{}]
    end = (lines[0].get("period") or {}).get("end") or obj.get("period_end")
    return {"status": "active", "current_period_end": end, "past_due_since": None, "failed_payments": 0}


def _payment_failed(row, obj, created):
    since = row["past_due_since"] if row and row["past_due_since"] else created
    return {"status": "past_due", "past_due_since": since,
            "failed_payments": (row["failed_payments"] if row else 0) + 1}


def _checkout_done(row, obj, created):
    return {"status": "active" if obj.get("payment_status") == "paid" else "incomplete"}


def _sub_updated(row, obj, created):
    changes = {"status": obj.get("status") or (row["status"] if row else "incomplete"),
               "cancel_at_period_end": int(bool(obj.get("cancel_at_period_end")))}
    if obj.get("current_period_end"):
        changes["current_period_end"] = obj["current_period_end"]
    items = (obj.get("items") or {}).get("data") or []
    plan = (items[0].get("price") or {}).get("nickname") if items else None
    if plan or (obj.get("metadata") or {}).get("plan"):
        changes["plan"] = plan or obj["metadata"]["plan"]
    return changes


def _sub_deleted(row, obj, created):
    return {"status": "canceled"}


HANDLERS = {
    "checkout.session.completed": _checkout_done,
    "invoice.paid": _paid,
    "invoice.payment_failed": _payment_failed,
    "customer.subscription.updated": _sub_updated,
    "customer.subscription.deleted": _sub_deleted,
}


def _subscription_id(typ: str, obj: dict) -> str | None:
    return obj.get("id") if typ.startswith("customer.subscription.") else obj.get("subscription")


def _info(typ: str, obj: dict) -> dict:
    """Descriptive fields that can safely be filled in even from an older event."""
    details = obj.get("customer_details") if isinstance(obj.get("customer_details"), dict) else {}
    return {"customer": obj.get("customer"),
            "email": obj.get("customer_email") or details.get("email"),
            "plan": (obj.get("metadata") or {}).get("plan")}


def validate_event(event) -> tuple[str, str, int, dict]:
    try:
        eid, typ, created, obj = event["id"], event["type"], int(event["created"]), event["data"]["object"]
    except (KeyError, TypeError, ValueError):
        raise BadEvent("event must have id, type, created and data.object")
    if not isinstance(obj, dict) or not isinstance(eid, str) or not isinstance(typ, str):
        raise BadEvent("event fields have the wrong type")
    return eid, typ, created, obj


def process(conn: sqlite3.Connection, event: dict) -> str:
    """Apply one event. Returns 'applied', 'stale', 'ignored' or 'duplicate'. Raises on bad input or DB errors."""
    eid, typ, created, obj = validate_event(event)
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM processed_events WHERE id=?", (eid,)).fetchone():
            conn.execute("ROLLBACK")
            return "duplicate"

        handler = HANDLERS.get(typ)
        sub_id = _subscription_id(typ, obj) if handler else None
        if not handler:
            outcome = "ignored"
        elif not sub_id:
            raise BadEvent(f"{typ} has no subscription id")
        else:
            conn.execute("INSERT OR IGNORE INTO subscriptions(id) VALUES (?)", (sub_id,))
            row = conn.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
            info = _info(typ, obj)
            conn.execute("UPDATE subscriptions SET customer=COALESCE(customer,?), email=COALESCE(email,?), plan=COALESCE(plan,?) "
                         "WHERE id=?", (info["customer"], info["email"], info["plan"], sub_id))
            if created < (row["last_event_created"] or 0):
                outcome = "stale"  # an older event must not undo newer state
            else:
                changes = handler(row if row["status"] else None, obj, created)
                changes["last_event_created"] = created
                sets = ", ".join(f"{k}=?" for k in changes)
                conn.execute(f"UPDATE subscriptions SET {sets} WHERE id=?", (*changes.values(), sub_id))
                outcome = "applied"

        conn.execute("INSERT INTO processed_events(id,type,created,outcome) VALUES (?,?,?,?)", (eid, typ, created, outcome))
        conn.execute("COMMIT")
        return outcome
    except BaseException:
        conn.execute("ROLLBACK")
        raise


# ---------- access decision ----------

def has_access(row: sqlite3.Row, now: float) -> tuple[bool, str]:
    status = row["status"]
    grace = GRACE_DAYS * 86400
    if status in ("active", "trialing"):
        end = row["current_period_end"]
        if end and now > end + grace:
            return False, "billing period ended and no renewal was received"
        return True, "active"
    if status == "past_due":
        since = row["past_due_since"] or 0
        if now <= since + grace:
            return True, "payment failed, still inside the grace period"
        return False, "payment failed and the grace period is over"
    return False, status or "unknown"
