"""
Records the demo video of the billing backend (needs: pip install playwright imageio-ffmpeg flask).
    python make_video.py [output.mp4]

It starts the REAL Flask app, sends it correctly signed (and deliberately broken) Stripe-style events, and shows
the real responses on a split-screen stage page. Nothing on screen is mocked: every status, chip and access
decision comes back from the running server.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "video"))
sys.path.insert(0, str(HERE))

PORT = 5611
SECRET, KEY = "whsec_demo_secret", "demo-key"
os.environ.update(STRIPE_WEBHOOK_SECRET=SECRET, API_KEY=KEY, BASE_URL=f"http://127.0.0.1:{PORT}")

import assinaturas as core  # noqa: E402
from simular_eventos import DAY, _event, post, signed  # noqa: E402
from videokit import Recorder  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "video" / "billing-backend-demo.mp4")
BASE = f"http://127.0.0.1:{PORT}"


def start_server(db):
    env = dict(os.environ, DB_PATH=db, FLASK_APP="app")
    proc = subprocess.Popen([sys.executable, "-m", "flask", "--app", "app", "run", "--port", str(PORT)], cwd=HERE, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/health", timeout=1)
            return proc
        except Exception:
            time.sleep(0.4)
    proc.kill()
    raise SystemExit("server did not start")


def get_access(customer):
    req = urllib.request.Request(f"{BASE}/api/customers/{customer}/access", headers={"X-API-Key": KEY})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def fmt_date(ts):
    return time.strftime("%b %d, %Y", time.gmtime(ts)) if ts else None


def short_header(h):
    return h[:34] + "..." if len(h) > 36 else h


def main():
    db = os.path.join(tempfile.mkdtemp(), "demo.db")
    server = start_server(db)
    t0 = int(time.time()) - 900
    try:
        with Recorder(OUT, caption_top=True) as r:
            p = r.page
            p.goto((HERE / "demo_stage.html").as_uri())
            p.evaluate("h => setHost(h)", f"live · real Flask server on {BASE} · SQLite")
            p.evaluate("() => setAccess({has_access:null, customer:'cus_ana', reason:'Waiting for the first event...'})")
            r.card_show("Subscription Billing Backend", "Stripe-style webhooks, handled safely - and one answer your app can trust",
                        tag="Python · Flask · SQLite · HMAC-SHA256")
            r.wait(0.8)
            r.mark_start()
            r.wait(4.2)
            r.card_hide()

            def send(label, event, customer, *, mutate=None, header=None, secret=SECRET, ts=None, note=None,
                     caption=None, sub="", hold=3.2):
                body, sig = signed(event, secret=secret, timestamp=ts)
                if mutate:
                    body = mutate(body)
                if header:
                    sig = header
                status, text = post("/webhooks/stripe", body, sig)
                outcome = ""
                try:
                    outcome = json.loads(text).get("outcome") or json.loads(text).get("error", "")
                except ValueError:
                    outcome = text
                tone = "ok" if status == 200 and outcome == "applied" else ("warn" if status == 200 else "bad")
                chip = f"{status} {outcome}" if status == 200 else f"{status} rejected"
                meta = f"{event.get('id')} · {note or event.get('type')}"
                p.evaluate("e => pushEvent(e)", {"title": label, "meta": meta, "chip": chip, "tone": tone})
                req = (f'<span class="k">POST</span> /webhooks/stripe\n<span class="k">Stripe-Signature:</span> '
                       f'{short_header(sig)}\n<span class="k">type:</span> {event.get("type")}  <span class="k">id:</span> {event.get("id")}')
                res = f'<span class="k">HTTP {status}</span>\n<span class="s">{text.strip()}</span>'
                p.evaluate("([a, b]) => setReq(a, b)", [req, res])
                a = get_access(customer)
                p.evaluate("a => setAccess(a)", {
                    "has_access": a.get("has_access"), "customer": customer, "status": a.get("status"), "plan": a.get("plan"),
                    "period_end": fmt_date(a.get("current_period_end")), "failed": a.get("failed_payments"), "reason": a.get("reason")})
                if caption:
                    r.caption(caption, sub, hold=hold)
                    r.caption_off(0.3)
                else:
                    r.wait(hold)
                return status, outcome

            # ---- Act 1: a customer's life -------------------------------------------------------------------
            r.card("Act 1 - A customer's life", "Sign up, pay, fail a payment, recover, cancel", tag="Happy path", hold=3)
            cus, sub = "cus_ana", "sub_ana"
            paid = {"customer": cus, "subscription": sub, "lines": {"data": [{"period": {"end": t0 + 30 * DAY}}]}}
            send("Customer signs up and pays", _event("evt_1001", "checkout.session.completed", t0, {
                "customer": cus, "subscription": sub, "customer_email": "ana@example.com", "payment_status": "paid",
                "metadata": {"plan": "pro"}}), cus, caption="Checkout completes - the account becomes active",
                 sub="Email and plan are stored from the event.")
            send("First invoice paid", _event("evt_1002", "invoice.paid", t0 + 60, paid), cus, hold=2.4)
            send("A later payment fails", _event("evt_1003", "invoice.payment_failed", t0 + 120,
                                                 {"customer": cus, "subscription": sub}), cus,
                 caption="Payment failed - but the customer keeps access",
                 sub="A 3-day grace period (configurable) so one bad card doesn't lock out a paying user.", hold=4.5)
            send("Customer fixes the card", _event("evt_1004", "invoice.paid", t0 + 180, paid), cus, hold=2.6)
            send("Customer cancels", _event("evt_1005", "customer.subscription.deleted", t0 + 240,
                                            {"id": sub, "customer": cus}), cus,
                 caption="Cancelled - access ends immediately", hold=3.4)

            # ---- Act 2: the things that go wrong ------------------------------------------------------------
            p.evaluate("() => clearFeed()")
            r.card("Act 2 - When things go wrong", "Webhooks get duplicated, forged, replayed and reordered", tag="Reality", hold=3.2)
            cus, sub = "cus_acme", "sub_acme"
            paid = {"customer": cus, "subscription": sub, "lines": {"data": [{"period": {"end": t0 + 30 * DAY}}]}}
            t1 = t0 + 400
            send("New customer pays", _event("evt_2001", "checkout.session.completed", t1, {
                "customer": cus, "subscription": sub, "customer_email": "billing@acme.example", "payment_status": "paid",
                "metadata": {"plan": "team"}}), cus, hold=2.2)
            dup = _event("evt_2002", "invoice.paid", t1 + 60, paid)
            send("Invoice paid", dup, cus, hold=1.8)
            send("Same event delivered AGAIN", dup, cus, caption="Stripe retries - the event is applied only once",
                 sub="Every event id is recorded in the same database transaction as the state change.", hold=4.4)
            send("Forged request (wrong secret)", _event("evt_9999", "customer.subscription.deleted", t1 + 70,
                                                         {"id": sub, "customer": cus}), cus, secret="whsec_attacker",
                 note="attacker tries to cancel a customer",
                 caption="A forged request is rejected - nothing is stored",
                 sub="HMAC-SHA256 over the exact bytes received, checked before the body is even parsed.", hold=4.6)
            ev = _event("evt_2003", "invoice.paid", t1 + 80, paid)
            send("Tampered request (body edited)", ev, cus,
                 mutate=lambda b: b.replace(b'"acme"', b'"evil"').replace(b"sub_acme", b"sub_evil"),
                 note="valid signature, changed payload", hold=3.4)
            send("Replayed old request", _event("evt_2004", "invoice.paid", t1 + 90, paid), cus,
                 ts=int(time.time()) - 3600, note="signature is 1 hour old",
                 caption="Old captured requests can't be replayed", sub="Signatures older than 5 minutes are refused.", hold=4.2)
            send("Payment fails", _event("evt_2005", "invoice.payment_failed", t1 + 200,
                                         {"customer": cus, "subscription": sub}), cus, hold=2.4)
            send("Late event from the past", _event("evt_2006", "invoice.paid", t1 + 100, paid), cus,
                 note="created BEFORE the failure, arrives after",
                 caption="Out-of-order delivery can't undo newer state",
                 sub="The older 'paid' event arrives late and is ignored - the account stays past_due.", hold=5.2)

            r.shot(str(HERE / "imagens" / "webhooks.jpg"))

            # ---- close ------------------------------------------------------------------------------------
            r.card("Tested, not just written", tag="18 automated tests",
                   bullets=["Duplicates, forgery, tampering, replay, reordering and crashes each have a test",
                            "A crash mid-event rolls back cleanly, so Stripe's retry just works",
                            "A missed renewal webhook can't give free access forever",
                            "Follows Stripe's documented signature scheme; wiring it to your Stripe test account is the last step"],
                   hold=8)
    finally:
        server.kill()
    print("saved", OUT)


if __name__ == "__main__":
    main()
