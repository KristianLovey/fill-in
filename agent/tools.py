from datetime import datetime, timedelta

from strands import tool

from agent.db import query, execute, log_event, now, iso

# ---------------------------------------------------------------- policy ----

ASK_TIMEOUT_MINUTES = 20     # how long one person gets to answer
MAX_ASKS_PER_SHIFT = 5       # after this, a human decides
URGENT_WINDOW_HOURS = 2      # inside this, never run the loop - wake the human
FATIGUE_ASKS_30D = 6         # asked this often lately -> push to the back


def _parse(ts):
    return datetime.fromisoformat(ts)


# ----------------------------------------------------------------- tools ----

@tool
def get_shift(shift_id: int) -> dict:
    """Look up one shift: role, time, location, required certificate, status.

    Args:
        shift_id: The shift to inspect.
    """
    rows = query("SELECT * FROM shifts WHERE id = ?", (shift_id,))
    if not rows:
        return {"error": f"No shift with id {shift_id}"}

    shift = rows[0]
    starts = _parse(shift["starts_at"])
    shift["hours_until_start"] = round((starts - now()).total_seconds() / 3600, 1)
    return shift


@tool
def rank_candidates(shift_id: int) -> list:
    """Rank volunteers who could cover this shift, best first.

    Filters out anyone lacking the required certificate or unavailable at that
    time, then scores on fairness: people who have done fewer shifts recently
    and been pestered less rank higher. Already-asked volunteers are excluded.

    Args:
        shift_id: The shift that needs covering.
    """
    shift = query("SELECT * FROM shifts WHERE id = ?", (shift_id,))
    if not shift:
        return [{"error": f"No shift with id {shift_id}"}]
    shift = shift[0]

    starts = _parse(shift["starts_at"])
    weekday, hour = starts.weekday(), starts.hour
    required = shift["required_cert"]

    already = {
        r["volunteer_id"]
        for r in query("SELECT volunteer_id FROM asks WHERE shift_id = ?", (shift_id,))
    }

    candidates = []
    for v in query("SELECT * FROM volunteers"):
        if v["id"] in already or v["id"] == shift["assigned_to"]:
            continue

        # Hard rule: no certificate, no shift. Not negotiable by the model.
        if required and required not in v["certs"].split(","):
            continue

        windows = query(
            "SELECT * FROM availability WHERE volunteer_id = ? AND weekday = ?",
            (v["id"], weekday),
        )
        if not any(w["start_hour"] <= hour < w["end_hour"] for w in windows):
            continue

        # Fairness score. Lower recent load and fewer recent asks win.
        score = (
            100
            - v["shifts_last_30d"] * 8
            - v["asks_last_30d"] * 4
            + v["response_rate"] * 20
        )
        if v["asks_last_30d"] >= FATIGUE_ASKS_30D:
            score -= 30  # recently over-asked: back of the queue

        candidates.append({
            "volunteer_id": v["id"],
            "name": v["name"],
            "score": round(score, 1),
            "shifts_last_30d": v["shifts_last_30d"],
            "asks_last_30d": v["asks_last_30d"],
            "response_rate": v["response_rate"],
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:8]


@tool
def send_ask(shift_id: int, volunteer_id: int, message: str) -> dict:
    """Ask one volunteer to cover a shift and start their response window.

    Refuses if the shift is already covered, if the volunteer lacks the required
    certificate, if they have already been asked, or if the ask limit is reached.

    Args:
        shift_id: The shift needing cover.
        volunteer_id: Who to ask.
        message: The message to send them, written for this person and shift.
    """
    shift = query("SELECT * FROM shifts WHERE id = ?", (shift_id,))
    if not shift:
        return {"refused": f"No shift with id {shift_id}"}
    shift = shift[0]

    if shift["status"] == "filled":
        return {"refused": "Shift is already covered. Stop asking."}

    hours_left = (_parse(shift["starts_at"]) - now()).total_seconds() / 3600
    if hours_left < URGENT_WINDOW_HOURS:
        return {"refused": "Starts too soon for the ask loop. Escalate instead."}

    # One person at a time, enforced here rather than asked for in the prompt.
    # Two wake-ups running at once would otherwise each pick a different name
    # and send two "we need you" messages for the same shift. Asks past their
    # window do not count - they are nobody's turn any more.
    holding = query(
        "SELECT v.name FROM asks a JOIN volunteers v ON v.id = a.volunteer_id "
        "WHERE a.shift_id = ? AND a.status = 'pending' AND a.expires_at > ?",
        (shift_id, iso(now())),
    )
    if holding:
        return {
            "refused": f"{holding[0]['name']} is still inside their response window. "
                       f"One person at a time - wait for them or let it time out."
        }

    vol = query("SELECT * FROM volunteers WHERE id = ?", (volunteer_id,))
    if not vol:
        return {"refused": f"No volunteer with id {volunteer_id}"}
    vol = vol[0]

    required = shift["required_cert"]
    if required and required not in vol["certs"].split(","):
        return {"refused": f"{vol['name']} does not hold '{required}'."}

    prior = query(
        "SELECT * FROM asks WHERE shift_id = ? AND volunteer_id = ?",
        (shift_id, volunteer_id),
    )
    if prior:
        return {"refused": f"{vol['name']} was already asked for this shift."}

    asked_count = len(query("SELECT id FROM asks WHERE shift_id = ?", (shift_id,)))
    if asked_count >= MAX_ASKS_PER_SHIFT:
        return {"refused": f"Ask limit ({MAX_ASKS_PER_SHIFT}) reached. Escalate."}

    expires = now() + timedelta(minutes=ASK_TIMEOUT_MINUTES)
    execute(
        "INSERT INTO asks (shift_id, volunteer_id, sent_at, expires_at, status) "
        "VALUES (?, ?, ?, ?, 'pending')",
        (shift_id, volunteer_id, iso(now()), iso(expires)),
    )
    execute(
        "UPDATE volunteers SET asks_last_30d = asks_last_30d + 1 WHERE id = ?",
        (volunteer_id,),
    )

    # In production this goes out over email/SMS. For the demo it is logged,
    # which is also what the dashboard renders.
    log_event("asked", f"Asked {vol['name']}: {message}", shift_id)
    return {
        "sent_to": vol["name"],
        "expires_at": iso(expires),
        "asks_used": asked_count + 1,
        "asks_remaining": MAX_ASKS_PER_SHIFT - asked_count - 1,
    }


@tool
def check_replies(shift_id: int) -> dict:
    """Check outstanding asks for a shift: who accepted, declined, or timed out.

    Expired asks are marked as timeouts automatically.

    Args:
        shift_id: The shift to check.
    """
    pending = query(
        "SELECT a.*, v.name FROM asks a JOIN volunteers v ON v.id = a.volunteer_id "
        "WHERE a.shift_id = ? AND a.status = 'pending'",
        (shift_id,),
    )
    for ask in pending:
        if _parse(ask["expires_at"]) <= now():
            execute("UPDATE asks SET status = 'timeout' WHERE id = ?", (ask["id"],))
            log_event("timeout", f"{ask['name']} did not answer in time.", shift_id)

    rows = query(
        "SELECT a.status, a.volunteer_id, v.name FROM asks a "
        "JOIN volunteers v ON v.id = a.volunteer_id WHERE a.shift_id = ?",
        (shift_id,),
    )
    return {
        "accepted": [r for r in rows if r["status"] == "accepted"],
        "declined": [r for r in rows if r["status"] == "declined"],
        "timeout": [r for r in rows if r["status"] == "timeout"],
        "still_waiting": [r for r in rows if r["status"] == "pending"],
        "asks_used": len(rows),
    }


@tool
def confirm_and_book(shift_id: int, volunteer_id: int) -> dict:
    """Assign a volunteer who accepted, close the shift, and release the others.

    Handles the race where two people accept at once: the first accepted ask
    wins, later ones are marked superseded so they can be offered another slot.

    Args:
        shift_id: The shift being covered.
        volunteer_id: The volunteer who accepted.
    """
    shift = query("SELECT * FROM shifts WHERE id = ?", (shift_id,))
    if not shift:
        return {"refused": f"No shift with id {shift_id}"}
    if shift[0]["status"] == "filled":
        return {"refused": "Already filled - do not double-book."}

    accepted = query(
        "SELECT * FROM asks WHERE shift_id = ? AND volunteer_id = ? AND status = 'accepted'",
        (shift_id, volunteer_id),
    )
    if not accepted:
        return {"refused": "That volunteer has not accepted this shift."}

    vol = query("SELECT name FROM volunteers WHERE id = ?", (volunteer_id,))[0]

    execute(
        "UPDATE shifts SET status = 'filled', assigned_to = ? WHERE id = ?",
        (volunteer_id, shift_id),
    )
    execute(
        "UPDATE volunteers SET shifts_last_30d = shifts_last_30d + 1 WHERE id = ?",
        (volunteer_id,),
    )
    execute(
        "UPDATE asks SET status = 'superseded' WHERE shift_id = ? AND status = 'pending'",
        (shift_id,),
    )

    log_event("filled", f"{vol['name']} covers the shift. No human involved.", shift_id)
    return {"filled_by": vol["name"], "shift_id": shift_id}


@tool
def escalate_to_human(shift_id: int, reason: str, detail: str) -> dict:
    """Hand this shift to the coordinator. The only channel to a human.

    Use when the ask limit is exhausted, the shift starts within two hours,
    no qualified volunteer exists, or anything looks ambiguous.

    Args:
        shift_id: The shift in question.
        reason: Short label, e.g. 'ask_limit_reached' or 'starts_too_soon'.
        detail: One or two sentences the coordinator can act on, including
            who was already asked and what you suggest.
    """
    existing = query(
        "SELECT id FROM escalations WHERE shift_id = ? AND resolved = 0", (shift_id,)
    )
    if existing:
        return {"already_escalated": True, "shift_id": shift_id}

    execute(
        "INSERT INTO escalations (shift_id, reason, detail, created_at) VALUES (?, ?, ?, ?)",
        (shift_id, reason, detail, iso(now())),
    )
    execute("UPDATE shifts SET status = 'escalated' WHERE id = ?", (shift_id,))
    log_event("escalated", f"{reason}: {detail}", shift_id)
    return {"escalated": True, "shift_id": shift_id, "reason": reason}


TOOLS = [
    get_shift,
    rank_candidates,
    send_ask,
    check_replies,
    confirm_and_book,
    escalate_to_human,
]