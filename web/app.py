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
from agent.tools import (  # noqa: E402
    ASK_TIMEOUT_MINUTES,
    FATIGUE_ASKS_30D,
    MAX_ASKS_PER_SHIFT,
    URGENT_WINDOW_HOURS,
)

app = Flask(__name__)

# What counts as "handled without you". Escalations are deliberately absent:
# an escalation is the opposite of handled, and it has its own column.
HANDLED_KINDS = ("cancelled", "asked", "declined", "accepted", "timeout", "filled")

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _agent_config():
    """Which provider and model back the agent.

    Resolved once at import: the credential chain can be slow, and this page
    polls every couple of seconds.
    """
    try:
        from agent.core import DEFAULT_MODEL, resolve_provider

        provider = resolve_provider()
        if not provider:
            return {"provider": None, "model": None}
        return {
            "provider": provider,
            "model": os.environ.get("FILLIN_MODEL") or DEFAULT_MODEL.get(provider),
        }
    except Exception:
        return {"provider": None, "model": None}


AGENT_CONFIG = _agent_config()


# ----------------------------------------------------------------- time ----

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


def _starts_in(ts):
    """How long until a shift starts, in the words a coordinator would use."""
    start = datetime.fromisoformat(ts)
    minutes = int((start - now()).total_seconds() // 60)
    if minutes < 0:
        return "already started"
    if minutes < 60:
        return f"starts in {minutes} min"
    if minutes < 24 * 60:
        hours, rest = divmod(minutes, 60)
        return f"starts in {hours} h" + (f" {rest} min" if rest else "")
    return f"{WEEKDAYS[start.weekday()]} {start.strftime('%H:%M')}"


def _is_urgent(ts):
    return (datetime.fromisoformat(ts) - now()).total_seconds() < URGENT_WINDOW_HOURS * 3600


# ------------------------------------------------------------ ask chains ----

def _asks_for(shift_id):
    """The agent's trail on one shift: who it asked, in order, and what came back."""
    rows = query(
        "SELECT a.*, v.name FROM asks a JOIN volunteers v ON v.id = a.volunteer_id "
        "WHERE a.shift_id = ? ORDER BY a.id",
        (shift_id,),
    )
    chain = []
    for row in rows:
        seconds_left = 0
        if row["status"] == "pending":
            left = (datetime.fromisoformat(row["expires_at"]) - now()).total_seconds()
            seconds_left = max(0, int(left))
        chain.append({
            "name": row["name"],
            "volunteer_id": row["volunteer_id"],
            "status": row["status"],
            "ago": _ago(row["sent_at"]),
            "seconds_left": seconds_left,
        })
    return chain


def _shift_cards():
    """Shifts the agent is working on or has already covered.

    Escalated shifts are not here - they are the other column.
    """
    rows = query(
        "SELECT s.*, v.name AS assigned_name FROM shifts s "
        "LEFT JOIN volunteers v ON v.id = s.assigned_to "
        "WHERE s.status = 'open' OR s.id IN (SELECT shift_id FROM asks)"
    )

    cards = []
    for shift in rows:
        if shift["status"] == "escalated":
            continue
        chain = _asks_for(shift["id"])
        cards.append({
            "id": shift["id"],
            "role": shift["role"],
            "location": shift["location"],
            "status": shift["status"],
            "required_cert": shift["required_cert"],
            "starts_in": _starts_in(shift["starts_at"]),
            "urgent": _is_urgent(shift["starts_at"]),
            "assigned_name": shift["assigned_name"],
            "asks": chain,
            "asks_used": len(chain),
            "asks_remaining": MAX_ASKS_PER_SHIFT - len(chain),
            "waiting_on": next((a["name"] for a in chain if a["status"] == "pending"), None),
        })

    # Open work first, then the covered ones, newest activity at the top.
    cards.sort(key=lambda c: (c["status"] != "open", -c["id"]))
    return cards


# -------------------------------------------------------------- fairness ----

def _roster():
    """Recent load per volunteer - the thing fairness scoring exists to even out.

    Shown as two ends rather than one ranked list: the people carrying the most
    are exactly the people `rank_candidates` pushes to the back, and the only way
    to see that is to show who it reaches for instead.
    """
    rows = query(
        "SELECT id, name, shifts_last_30d, asks_last_30d, response_rate FROM volunteers"
    )

    def shape(r):
        return {
            "name": r["name"],
            "shifts": r["shifts_last_30d"],
            "asks": r["asks_last_30d"],
            "response_rate": round(r["response_rate"] * 100),
            "protected": r["asks_last_30d"] >= FATIGUE_ASKS_30D,
        }

    heaviest = sorted(rows, key=lambda r: (-r["shifts_last_30d"], -r["asks_last_30d"]))[:3]
    lightest = sorted(rows, key=lambda r: (r["shifts_last_30d"], r["asks_last_30d"]))[:3]

    return {
        "peak": max([r["shifts_last_30d"] for r in rows] + [1]),
        "protected": sum(1 for r in rows if r["asks_last_30d"] >= FATIGUE_ASKS_30D),
        "total": len(rows),
        "threshold": FATIGUE_ASKS_30D,
        "heaviest": [shape(r) for r in heaviest],
        "lightest": [shape(r) for r in lightest],
    }


def _week():
    """One dot per shift, so the whole roster is visible at a glance."""
    rows = query("SELECT id, role, status, starts_at FROM shifts ORDER BY starts_at, id")
    counts = {"filled": 0, "open": 0, "escalated": 0}
    dots = []
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        start = datetime.fromisoformat(row["starts_at"])
        dots.append({
            "id": row["id"],
            "status": row["status"],
            "label": f"{row['role']} · {WEEKDAYS[start.weekday()]} {start.strftime('%H:%M')}",
        })
    return {"dots": dots, "counts": counts, "total": len(rows)}


# ----------------------------------------------------------------- state ----

def _state():
    placeholders = ",".join("?" * len(HANDLED_KINDS))
    handled = query(
        f"SELECT e.* FROM events e WHERE e.kind IN ({placeholders}) "
        f"ORDER BY e.id DESC LIMIT 40",
        HANDLED_KINDS,
    )
    handled_total = query(
        f"SELECT COUNT(*) AS n FROM events WHERE kind IN ({placeholders})", HANDLED_KINDS
    )[0]["n"]
    covered = query("SELECT COUNT(*) AS n FROM events WHERE kind = 'filled'")[0]["n"]

    escalations = query(
        "SELECT x.*, s.role, s.starts_at, s.required_cert "
        "FROM escalations x LEFT JOIN shifts s ON s.id = x.shift_id "
        "WHERE x.resolved = 0 ORDER BY x.id"
    )
    ticks = query("SELECT ts FROM events WHERE kind = 'tick' ORDER BY id DESC LIMIT 1")

    return {
        "kpi": {
            "handled": handled_total,
            "covered": covered,
            "waiting": len(escalations),
        },
        "shifts": _shift_cards(),
        "escalations": [
            {
                "id": x["id"],
                "shift_id": x["shift_id"],
                "role": x["role"],
                "reason": x["reason"].replace("_", " "),
                "detail": x["detail"],
                "required_cert": x["required_cert"],
                "starts_in": _starts_in(x["starts_at"]) if x["starts_at"] else None,
                "asks": _asks_for(x["shift_id"]),
                "ago": _ago(x["created_at"]),
            }
            for x in escalations
        ],
        "audit": [
            {
                "id": e["id"],
                "kind": e["kind"],
                "detail": e["detail"],
                "ago": _ago(e["ts"]),
            }
            for e in handled
        ],
        "roster": _roster(),
        "week": _week(),
        "agent": {
            "last_tick": _ago(ticks[0]["ts"]) if ticks else None,
            "provider": AGENT_CONFIG["provider"],
            "model": AGENT_CONFIG["model"],
        },
        "policy": {
            "window_minutes": ASK_TIMEOUT_MINUTES,
            "max_asks": MAX_ASKS_PER_SHIFT,
            "urgent_hours": URGENT_WINDOW_HOURS,
            "fatigue_asks": FATIGUE_ASKS_30D,
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
