"""
Sends a realistic, correctly signed sequence of Stripe-style events to a running server, so you can watch the
state change without a Stripe account:

    # terminal 1
    set STRIPE_WEBHOOK_SECRET=whsec_test & set API_KEY=demo-key & flask --app app run
    # terminal 2
    python simular_eventos.py

It also sends a duplicate and a forged request to show they are handled safely.
"""
import json
import os
import time
import urllib.error
import urllib.request

import assinaturas as core

SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_test")
API_KEY = os.environ.get("API_KEY", "demo-key")
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
DAY = 86400


def _event(eid, typ, created, obj):
    return {"id": eid, "type": typ, "created": created, "data": {"object": obj}}


def story(t0: int, customer="cus_demo", sub="sub_demo") -> list[tuple[str, dict]]:
    """A customer's life: signs up, pays, a later payment fails, they recover, then cancel.

    Event times are a few minutes apart (so the demo reads truthfully against the real clock);
    each paid invoice covers 30 days from t0.
    """
    paid = {"customer": customer, "subscription": sub, "lines": {"data": [{"period": {"end": t0 + 30 * DAY}}]}}
    return [
        ("customer signs up and pays", _event("evt_1", "checkout.session.completed", t0, {
            "customer": customer, "subscription": sub, "customer_email": "ana@example.com",
            "payment_status": "paid", "metadata": {"plan": "pro"}})),
        ("first invoice paid", _event("evt_2", "invoice.paid", t0 + 60, paid)),
        ("a later invoice payment fails", _event("evt_3", "invoice.payment_failed", t0 + 120,
                                                  {"customer": customer, "subscription": sub})),
        ("customer fixes the card, invoice paid", _event("evt_4", "invoice.paid", t0 + 180, paid)),
        ("customer cancels", _event("evt_5", "customer.subscription.deleted", t0 + 240, {"id": sub, "customer": customer})),
    ]


def signed(event: dict, secret: str = SECRET, timestamp: int | None = None) -> tuple[bytes, str]:
    body = json.dumps(event).encode()
    return body, core.sign(secret, body, int(time.time()) if timestamp is None else timestamp)


def post(path: str, body: bytes, signature: str):
    req = urllib.request.Request(BASE + path, data=body, headers={"Stripe-Signature": signature, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def access():
    req = urllib.request.Request(BASE + "/api/customers/cus_demo/access", headers={"X-API-Key": API_KEY})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


if __name__ == "__main__":
    t0 = int(time.time()) - 600
    for label, ev in story(t0):
        status, text = post("/webhooks/stripe", *signed(ev))
        a = access()
        print(f"{label:<42} -> {status} {text.strip():<22} access={a.get('has_access')} ({a.get('status')})")
    print("\nSame event delivered twice  ->", post("/webhooks/stripe", *signed(story(t0)[0][1])))
    body, _ = signed(story(t0)[0][1])
    print("Forged signature            ->", post("/webhooks/stripe", body, "t=1,v1=" + "0" * 64))
