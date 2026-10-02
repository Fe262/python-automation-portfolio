# Subscription Billing Backend — Stripe-style webhooks done safely

The backend half of "customers pay monthly": it receives billing events, keeps each customer's subscription state correct, and answers one question for your app — **does this customer have access right now?**

**[Watch the demo video](video/billing-backend-demo-web.mp4)**: recorded against the real billing backend, not a mock-up. Re-record it with `python make_video.py` (needs `pip install -r ../requirements-video.txt` and `playwright install chromium`).

Webhook code is easy to write and easy to get subtly wrong. This project handles the ways it usually goes wrong, and each one has a test.

## What it protects against

| Problem | What this does |
|---|---|
| Forged or tampered requests | Verifies Stripe's documented HMAC-SHA256 signature over the exact bytes received |
| Replayed requests | Rejects signatures older than 5 minutes |
| The same event delivered twice | Records every event id; a repeat is acknowledged and not applied again |
| Events arriving out of order | An older event never overwrites newer state; if an invoice arrives before checkout, the late checkout still fills in email and plan |
| A crash halfway through an event | State change and "event processed" mark are one database transaction, so Stripe's retry applies cleanly |
| A missed renewal webhook | Access ends once the billing period plus grace has passed, even if no cancellation ever arrived |
| Failed payments | Customer keeps access for a 3-day grace period, then loses it (configurable) |

Events handled: `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`. Anything else is acknowledged and ignored, so Stripe doesn't keep retrying it.

## See it work (no Stripe account needed)

```bash
pip install flask pytest
export STRIPE_WEBHOOK_SECRET=whsec_test API_KEY=demo-key    # Windows: set X=Y
flask --app app run                                         # terminal 1
python simular_eventos.py                                   # terminal 2
```

```
customer signs up and pays                 -> 200 {"outcome":"applied"}  access=True (active)
first invoice paid                         -> 200 {"outcome":"applied"}  access=True (active)
a later invoice payment fails              -> 200 {"outcome":"applied"}  access=True (past_due)
customer fixes the card, invoice paid      -> 200 {"outcome":"applied"}  access=True (active)
customer cancels                           -> 200 {"outcome":"applied"}  access=False (canceled)

Same event delivered twice  -> (200, '{"outcome":"duplicate"}')
Forged signature            -> (400, '{"error":"signature does not match"}')
```

## API

- `POST /webhooks/stripe` — the endpoint you register in Stripe.
- `GET /api/customers/<customer_id>/access` — header `X-API-Key`. Returns `has_access`, `reason`, `status`, `plan`, `current_period_end`.
- `GET /health`

The app refuses to start without `STRIPE_WEBHOOK_SECRET` and `API_KEY`; there are no insecure defaults.

## Tests

`python -m pytest` runs 18 tests. For the key protections (duplicate delivery, out-of-order events, replay window) I removed the protection from the code and confirmed a test fails, so the tests actually guard them.

## What is real and what is not

- The signature scheme and event shapes follow Stripe's documentation, but **this has not been run against live Stripe**. Connecting it needs your Stripe test keys and `stripe listen` (or a public URL), which is a short step but not something I could do here.
- Only the fields needed for subscription state are read from each event. Adding coupons, metered usage, invoices in PDF, a customer portal link, or Stripe Checkout session creation are straightforward extensions.
- Storage is SQLite, which is fine for a small SaaS; the same code moves to Postgres if you need it.
