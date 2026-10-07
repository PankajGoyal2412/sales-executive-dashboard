"""
Flask web app for the Executive Sales Dashboard.
Renders the interactive UI from data.xlsx (cached JSON via Pulse_Builder).
"""

import json
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

from Pulse_Builder import get_pulse_json, save_pulse_cache

app = Flask(__name__)
METRICS_PATH = Path(__file__).resolve().parent / "metrics.json"


def load_metrics_json() -> str:
    """Read metrics.json on every request so definition edits show up on refresh."""
    payload = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    # Escape "<" so metric text cannot break the HTML <script> tag
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


# Warm Pulse cache on boot (skip quietly if data.xlsx is missing)
try:
    get_pulse_json(force=False)
except FileNotFoundError:
    pass


@app.route("/")
def index():
    # Demo-only role switch: /?role=admin shows Excel rebuild button
    user_role = request.args.get("role", "viewer")
    is_admin = user_role == "admin"

    return render_template(
        "index.html",
        pulse_json=get_pulse_json(force=False),
        metrics_json=load_metrics_json(),
        is_admin=is_admin,
    )


@app.route("/sync", methods=["POST"])
def sync_data():
    """Admin-only: rebuild Pulse cache from data.xlsx."""
    user_role = request.args.get("role", "viewer")
    if user_role != "admin":
        return "Unauthorized Access Request Blocked", 403

    try:
        save_pulse_cache()
    except Exception as exc:
        return f"Data rebuild failed: {exc}", 500

    return redirect(url_for("index", role="admin"))


if __name__ == "__main__":
    # Local run only — Render uses gunicorn via Procfile
    app.run(debug=True)
