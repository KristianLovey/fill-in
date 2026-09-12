"""Fill In - the coordinator's dashboard.

Two columns. The left one is everything the agent did on its own; the right one
is the only thing that needs a person. The contrast between them is the point,
so the right-hand colour appears nowhere else in the interface.

  python web/app.py       ->  http://127.0.0.1:5000

Read-only except for one button: resolving an escalation. The agent is not
driven from here - it runs from run_tick.py.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, render_template  # noqa: E402

from agent.db import query, execute, log_event, now  # noqa: E402
from agent.tools import ASK_TIMEOUT_MINUTES, MAX_ASKS_PER_SHIFT  # noqa: E402

app = Flask(__name__)

# What counts as "handled without you". Escalations are deliberately absent:
# an escalation is the opposite of handled, and it has its own column.
HANDLED_KINDS = ("cancelled", "asked", "declined", "accepted", "timeout", "filled")


def _ago(ts):
    """Relative time, so the page never has to explain a timezone."""
    seconds = int((now() - datetime.fromisoformat(ts)).total_seconds())
    if seconds < 10:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


def _state():
    placeholders = ",".join("?" * len(HANDLED_KINDS))
    handled = query(
        f"SELECT e.*, s.role FROM events e LEFT JOIN shifts s ON s.id = e.shift_id "
        f"WHERE e.kind IN ({placeholders}) ORDER BY e.id DESC LIMIT 60",
        HANDLED_KINDS,
    )

    inflight = query(
        "SELECT a.id, a.expires_at, v.name, s.id AS shift_id, s.role "
        "FROM asks a JOIN volunteers v ON v.id = a.volunteer_id "
        "JOIN shifts s ON s.id = a.shift_id "
        "WHERE a.status = 'pending' ORDER BY a.id"
    )
    for ask in inflight:
        left = (datetime.fromisoformat(ask["expires_at"]) - now()).total_seconds()
        ask["seconds_left"] = max(0, int(left))

    escalations = query(
        "SELECT x.*, s.role, s.starts_at, s.required_cert "
        "FROM escalations x LEFT JOIN shifts s ON s.id = x.shift_id "
        "WHERE x.resolved = 0 ORDER BY x.id"
    )

    ticks = query("SELECT ts FROM events WHERE kind = 'tick' ORDER BY id DESC LIMIT 1")

    return {
        "handled": [
            {
                "id": e["id"],
                "kind": e["kind"],
                "detail": e["detail"],
                "role": e["role"],
                "shift_id": e["shift_id"],
                "ago": _ago(e["ts"]),
            }
            for e in handled
        ],
        "inflight": [
            {
                "id": a["id"],
                "name": a["name"],
                "role": a["role"],
                "shift_id": a["shift_id"],
                "seconds_left": a["seconds_left"],
            }
            for a in inflight
        ],
        "escalations": [
            {
                "id": x["id"],
                "shift_id": x["shift_id"],
                "role": x["role"],
                "reason": x["reason"].replace("_", " "),
                "detail": x["detail"],
                "required_cert": x["required_cert"],
                "ago": _ago(x["created_at"]),
            }
            for x in escalations
        ],
        "counts": {"handled": len(handled), "waiting": len(escalations)},
        "last_tick": _ago(ticks[0]["ts"]) if ticks else None,
        "policy": {
            "window_minutes": ASK_TIMEOUT_MINUTES,
            "max_asks": MAX_ASKS_PER_SHIFT,
        },
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    response = jsonify(_state())
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/escalations/<int:escalation_id>/resolve", methods=["POST"])
def resolve(escalation_id):
    rows = query("SELECT * FROM escalations WHERE id = ?", (escalation_id,))
    if not rows:
        return jsonify({"error": "no such escalation"}), 404

    execute("UPDATE escalations SET resolved = 1 WHERE id = ?", (escalation_id,))
    log_event(
        "resolved",
        f"Coordinator handled: {rows[0]['reason']}.",
        rows[0]["shift_id"],
    )
    return jsonify(_state())


if __name__ == "__main__":
    # Debug off by default: the reloader restarts the process mid-recording.
    app.run(
        port=int(os.environ.get("PORT", 5000)),
        debug=bool(os.environ.get("FILLIN_DEBUG")),
    )
