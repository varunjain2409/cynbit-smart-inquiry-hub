"""
Cynbit Smart Inquiry Hub — Flask application

Routes:
  GET  /                     → improved inquiry experience (styled like cynbit.in)
  GET  /admin                → mini-CRM dashboard (pipeline view)
  POST /api/inquire          → validate → score → persist → Project Intelligence
  GET  /api/leads            → leads list (admin feed)
  GET  /api/stats            → pipeline stats
  POST /api/leads/<id>/status→ update pipeline status
  GET  /api/health           → health probe for Render
"""
import re
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

import database
import lead_engine

app = Flask(__name__)
database.init_db()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
SERVICES = set(lead_engine.SERVICE_KEYWORDS.keys()) | {"Other"}
BUDGETS = set(lead_engine.BUDGET_POINTS.keys())
TIMELINES = set(lead_engine.TIMELINE_POINTS.keys())
STATUSES = {"New", "Contacted", "Call booked", "Won", "Lost"}


def _clean(value: str, max_len: int = 400) -> str:
    return (value or "").strip()[:max_len]


@app.after_request
def add_headers(resp):
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Cache-Control", "public, max-age=300")
    return resp


# ------------------------------------------------------------------ pages ---

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/admin")
def admin():
    return render_template("admin.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "cynbit-smart-inquiry-hub"})


# ------------------------------------------------------------------- API ----

@app.post("/api/inquire")
def inquire():
    data = request.get_json(silent=True) or {}
    name = _clean(data.get("name"), 80)
    email = _clean(data.get("email"), 120)
    message = _clean(data.get("message"), 3000)
    service = data.get("service") in SERVICES and data.get("service") or ""
    budget = data.get("budget") in BUDGETS and data.get("budget") or "Not sure yet"
    timeline = data.get("timeline") in TIMELINES and data.get("timeline") or "Just exploring"

    errors = {}
    if len(name) < 2:
        errors["name"] = "Please enter your full name."
    if not EMAIL_RE.match(email):
        errors["email"] = "Please enter a valid email address."
    if service not in SERVICES:
        errors["service"] = "Please choose a service track."
    if len(message) < 25:
        errors["message"] = "Tell us a bit more (25+ characters) so we can qualify your project."
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    score, tier, next_step, signals = lead_engine.score_lead(
        {"message": message, "budget": budget, "timeline": timeline,
         "email": email, "company": data.get("company"), "industry": data.get("industry"),
         "service": service}
    )
    intel_text, intel_type = lead_engine.intelligence(
        {"service": service, "industry": data.get("industry"), "budget": budget,
         "timeline": timeline, "message": message},
        score, tier,
    )

    lead_id = database.insert_lead({
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name": name, "email": email,
        "company": _clean(data.get("company"), 100),
        "industry": _clean(data.get("industry"), 60),
        "service": service, "budget": budget, "timeline": timeline,
        "message": message,
        "score": score, "tier": tier, "next_step": next_step,
        "summary_type": intel_type, "intelligence": intel_text,
    })

    return jsonify({
        "ok": True,
        "id": lead_id,
        "score": score,
        "tier": tier,
        "next_step": next_step,
        "signals": signals,
        "intelligence": intel_text,
        "summary_type": intel_type,
    })


@app.get("/api/leads")
def leads():
    return jsonify({"ok": True, "leads": database.all_leads()})


@app.get("/api/stats")
def get_stats():
    s = database.stats()
    return jsonify({
        "ok": True,
        "total": s.get("total", 0),
        "hot": s.get("hot", 0),
        "warm": s.get("warm", 0),
        "exploring": s.get("exploring", 0),
        "avg_score": s.get("avg_score", 0),
        "worked_on": s.get("contacted", 0),
        "new_count": s.get("new_count", 0),
    })


@app.post("/api/leads/<int:lead_id>/status")
def set_status(lead_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status", "")
    if status not in STATUSES:
        return jsonify({"ok": False, "error": "invalid status"}), 400
    if database.update_status(lead_id, status):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "lead not found"}), 404


# Render free tier / local probe
if __name__ == "__main__":
    # Local dev only; Render uses gunicorn via startCommand.
    app.run(host="0.0.0.0", port=5000)
