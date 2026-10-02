"""Billing backend: receives Stripe-style webhooks and answers "does this customer have access?".

Run:   STRIPE_WEBHOOK_SECRET=whsec_test API_KEY=change-me flask --app app run
Needs two environment variables; it refuses to start without them (no insecure defaults).
"""
import json
import os
import time

from flask import Flask, jsonify, request

import assinaturas as core


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        DB_PATH=os.environ.get("DB_PATH", "assinaturas.db"),
        WEBHOOK_SECRET=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        API_KEY=os.environ.get("API_KEY", ""),
        CLOCK=time.time,
        MAX_CONTENT_LENGTH=1_000_000,
    )
    if config:
        app.config.update(config)
    if not app.config["WEBHOOK_SECRET"] or not app.config["API_KEY"]:
        raise RuntimeError("Set STRIPE_WEBHOOK_SECRET and API_KEY before starting the app.")
    core.init_db(app.config["DB_PATH"])

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.post("/webhooks/stripe")
    def webhook():
        raw = request.get_data()  # the signature is over the exact bytes received, so verify before parsing
        try:
            core.verify(app.config["WEBHOOK_SECRET"], raw, request.headers.get("Stripe-Signature"), now=app.config["CLOCK"]())
        except core.SignatureError as e:
            return jsonify(error=str(e)), 400
        try:
            event = json.loads(raw)
        except ValueError:
            return jsonify(error="body is not valid JSON"), 400

        conn = core.connect(app.config["DB_PATH"])
        try:
            outcome = core.process(conn, event)
        except core.BadEvent as e:
            return jsonify(error=str(e)), 400
        except Exception:
            app.logger.exception("webhook processing failed")
            return jsonify(error="processing failed, safe to retry"), 500  # Stripe retries any non-2xx
        finally:
            conn.close()
        return jsonify(outcome=outcome), 200  # 200 also for duplicate/stale/ignored so Stripe stops retrying

    @app.get("/api/customers/<customer>/access")
    def access(customer):
        if request.headers.get("X-API-Key") != app.config["API_KEY"]:
            return jsonify(error="invalid or missing API key"), 401
        conn = core.connect(app.config["DB_PATH"])
        try:
            rows = conn.execute("SELECT * FROM subscriptions WHERE customer=?", (customer,)).fetchall()
        finally:
            conn.close()
        if not rows:
            return jsonify(customer=customer, has_access=False, reason="no subscription found"), 404
        now = app.config["CLOCK"]()
        decisions = [(core.has_access(r, now), r) for r in rows]
        (ok, reason), row = next((d for d in decisions if d[0][0]), decisions[0])
        return jsonify(customer=customer, has_access=ok, reason=reason, status=row["status"], plan=row["plan"],
                       current_period_end=row["current_period_end"], failed_payments=row["failed_payments"])

    return app
