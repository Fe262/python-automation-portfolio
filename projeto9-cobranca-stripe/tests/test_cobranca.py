import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import assinaturas as core
from app import create_app
from simular_eventos import DAY, story

SECRET, KEY = "whsec_test", "k-123"
NOW = 1_800_000_000


@pytest.fixture
def ctx(tmp_path):
    clock = {"now": NOW}
    db = str(tmp_path / "t.db")
    app = create_app({"DB_PATH": db, "WEBHOOK_SECRET": SECRET, "API_KEY": KEY, "CLOCK": lambda: clock["now"]})
    return SimpleNamespace(client=app.test_client(), clock=clock, db=db)


def send(ctx, event, secret=SECRET, ts=None, header=None, body=None):
    body = body if body is not None else json.dumps(event).encode()
    header = header if header is not None else core.sign(secret, body, ts if ts is not None else ctx.clock["now"])
    return ctx.client.post("/webhooks/stripe", data=body, headers={"Stripe-Signature": header})


def sql(ctx, query, *args):
    conn = sqlite3.connect(ctx.db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query, args).fetchall()
    finally:
        conn.close()


def sub(ctx, sub_id="sub_demo"):
    rows = sql(ctx, "SELECT * FROM subscriptions WHERE id=?", sub_id)
    return dict(rows[0]) if rows else None


def access(ctx, customer="cus_demo"):
    return ctx.client.get(f"/api/customers/{customer}/access", headers={"X-API-Key": KEY})


def ev(eid, typ, created, **obj):
    return {"id": eid, "type": typ, "created": created, "data": {"object": obj}}


# ---------- signatures ----------

def test_valid_signature_is_accepted(ctx):
    r = send(ctx, story(NOW - 5 * DAY)[0][1])
    assert r.status_code == 200 and r.get_json()["outcome"] == "applied"


def test_wrong_secret_is_rejected_and_nothing_is_stored(ctx):
    r = send(ctx, story(NOW)[0][1], secret="whsec_attacker")
    assert r.status_code == 400
    assert sub(ctx) is None and sql(ctx, "SELECT * FROM processed_events") == []


def test_missing_and_malformed_headers_are_rejected(ctx):
    body = json.dumps(story(NOW)[0][1]).encode()
    assert ctx.client.post("/webhooks/stripe", data=body).status_code == 400
    assert send(ctx, None, body=body, header="garbage").status_code == 400
    assert send(ctx, None, body=body, header="t=abc,v1=00").status_code == 400


def test_tampered_body_is_rejected(ctx):
    event = story(NOW)[0][1]
    body = json.dumps(event).encode()
    good_header = core.sign(SECRET, body, NOW)
    evil = json.dumps({**event, "data": {"object": {**event["data"]["object"], "customer": "cus_evil"}}}).encode()
    assert send(ctx, None, body=evil, header=good_header).status_code == 400


def test_old_signature_is_rejected_as_replay(ctx):
    r = send(ctx, story(NOW)[0][1], ts=NOW - 3600)
    assert r.status_code == 400 and "replay" in r.get_json()["error"]


# ---------- the subscription life cycle ----------

def test_checkout_creates_an_active_subscription(ctx):
    send(ctx, story(NOW - 5 * DAY)[0][1])
    s = sub(ctx)
    assert (s["status"], s["plan"], s["email"], s["customer"]) == ("active", "pro", "ana@example.com", "cus_demo")


def test_failed_payment_then_recovery(ctx):
    events = story(NOW - 40 * DAY)
    for _, e in events[:3]:
        send(ctx, e)
    s = sub(ctx)
    assert s["status"] == "past_due" and s["failed_payments"] == 1
    send(ctx, events[3][1])
    s = sub(ctx)
    assert s["status"] == "active" and s["failed_payments"] == 0 and s["past_due_since"] is None


def test_cancellation_removes_access(ctx):
    for _, e in story(NOW - 100 * DAY):
        send(ctx, e)
    assert sub(ctx)["status"] == "canceled"
    r = access(ctx)
    assert r.get_json()["has_access"] is False


def test_unknown_event_types_are_acknowledged_and_ignored(ctx):
    r = send(ctx, ev("evt_x", "charge.dispute.created", NOW, id="dp_1"))
    assert r.status_code == 200 and r.get_json()["outcome"] == "ignored"


# ---------- the classic webhook bugs ----------

def test_same_event_delivered_twice_is_applied_once(ctx):
    failed = ev("evt_f", "invoice.payment_failed", NOW - DAY, customer="cus_demo", subscription="sub_demo")
    assert send(ctx, failed).get_json()["outcome"] == "applied"
    assert send(ctx, failed).get_json()["outcome"] == "duplicate"
    assert sub(ctx)["failed_payments"] == 1  # not 2


def test_old_event_arriving_late_does_not_undo_newer_state(ctx):
    send(ctx, ev("evt_new", "invoice.payment_failed", NOW - 1 * DAY, customer="cus_demo", subscription="sub_demo"))
    late = send(ctx, ev("evt_old", "invoice.paid", NOW - 5 * DAY, customer="cus_demo", subscription="sub_demo"))
    assert late.get_json()["outcome"] == "stale"
    assert sub(ctx)["status"] == "past_due"


def test_invoice_before_checkout_still_ends_up_complete(ctx):
    """Stripe does not promise order: the invoice can arrive first. The later, older checkout event fills in
    the missing email and plan without touching the status."""
    t = NOW - 5 * DAY
    send(ctx, ev("evt_inv", "invoice.paid", t + 1, customer="cus_demo", subscription="sub_demo",
                 lines={"data": [{"period": {"end": t + 30 * DAY}}]}))
    send(ctx, ev("evt_chk", "checkout.session.completed", t, customer="cus_demo", subscription="sub_demo",
                 customer_email="ana@example.com", payment_status="paid", metadata={"plan": "pro"}))
    s = sub(ctx)
    assert (s["status"], s["email"], s["plan"]) == ("active", "ana@example.com", "pro")


def test_crash_midway_leaves_no_trace_and_retry_works(ctx, monkeypatch):
    paid = ev("evt_p", "invoice.paid", NOW - DAY, customer="cus_demo", subscription="sub_demo",
              lines={"data": [{"period": {"end": NOW + 29 * DAY}}]})

    def boom(*a):
        raise RuntimeError("database exploded")
    monkeypatch.setitem(core.HANDLERS, "invoice.paid", boom)
    assert send(ctx, paid).status_code == 500
    assert sql(ctx, "SELECT * FROM processed_events") == []  # not marked as processed
    assert sub(ctx) is None                                   # the half-made subscription row was rolled back too

    monkeypatch.undo()
    r = send(ctx, paid)  # Stripe's retry
    assert r.status_code == 200 and r.get_json()["outcome"] == "applied"
    assert sub(ctx)["status"] == "active"


def test_malformed_events_get_400_and_are_not_recorded(ctx):
    assert send(ctx, {"hello": "world"}).status_code == 400
    assert send(ctx, ev("evt_ns", "invoice.paid", NOW, customer="cus_demo")).status_code == 400  # no subscription id
    assert send(ctx, None, body=b"not json").status_code == 400
    assert sql(ctx, "SELECT * FROM processed_events") == []


# ---------- who gets access ----------

def test_grace_period_after_failed_payment(ctx):
    failed_at = NOW - 2 * DAY
    send(ctx, ev("evt_f", "invoice.payment_failed", failed_at, customer="cus_demo", subscription="sub_demo"))
    inside = access(ctx).get_json()
    assert inside["has_access"] is True and "grace" in inside["reason"]
    ctx.clock["now"] = failed_at + core.GRACE_DAYS * DAY + 60
    outside = access(ctx).get_json()
    assert outside["has_access"] is False and "grace period is over" in outside["reason"]


def test_missed_renewal_webhook_does_not_give_free_access_forever(ctx):
    t = NOW - 60 * DAY
    send(ctx, ev("evt_i", "invoice.paid", t, customer="cus_demo", subscription="sub_demo",
                 lines={"data": [{"period": {"end": t + 30 * DAY}}]}))
    # period ended 30 days ago and no renewal (or cancellation) was ever received
    r = access(ctx).get_json()
    assert r["has_access"] is False and "no renewal" in r["reason"]


def test_access_api_needs_the_key_and_unknown_customers_are_404(ctx):
    assert ctx.client.get("/api/customers/cus_demo/access").status_code == 401
    assert ctx.client.get("/api/customers/cus_demo/access", headers={"X-API-Key": "wrong"}).status_code == 401
    assert access(ctx, "cus_nobody").status_code == 404


def test_app_refuses_to_start_without_secrets(tmp_path):
    with pytest.raises(RuntimeError):
        create_app({"DB_PATH": str(tmp_path / "x.db"), "WEBHOOK_SECRET": "", "API_KEY": "k"})
