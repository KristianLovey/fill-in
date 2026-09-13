"""Fill In - demo driver.

  python -m agent.cli doctor              which provider and model will be used
  python -m agent.cli status              the two columns, in the terminal
  python -m agent.cli cancel <shift>      someone drops out; shift becomes open
  python -m agent.cli urgent <shift> [m]  drop out of a shift starting in m
                                          minutes (default 90) - the escalation
                                          path
  python -m agent.cli tick                wake the agent once
  python -m agent.cli loop [n] [secs]     wake it n times, secs apart
  python -m agent.cli accept <shift> [volunteer]    answer as whoever is being
  python -m agent.cli decline <shift> [volunteer]   asked, or as a named volunteer

Nothing here is part of the agent. It stands in for the world: volunteers
replying, a coordinator watching. The agent only ever runs from tick().
"""

import sys
import time
from datetime import timedelta

from agent.db import query, execute, log_event, now, iso


def cancel(shift_id):
    rows = query("SELECT * FROM shifts WHERE id = ?", (shift_id,))
    if not rows:
        print(f"No shift {shift_id}")
        return
    shift = rows[0]
    who = query("SELECT name FROM volunteers WHERE id = ?", (shift["assigned_to"],))
    name = who[0]["name"] if who else "someone"
    execute("UPDATE shifts SET status = 'open', assigned_to = NULL WHERE id = ?", (shift_id,))
    log_event("cancelled", f"{name} dropped out of {shift['role']}.", shift_id)
    print(f"Shift {shift_id} ({shift['role']}, {shift['starts_at']}) is now open.")
    print("The agent will pick it up on the next tick. Nobody was notified by hand.")


def urgent(shift_id, minutes=90):
    """Move a shift to just before it starts, then drop out of it.

    Every seeded shift starts tomorrow at the earliest, so there is no way to
    demonstrate the urgent path without moving one. This is the second demo
    scenario: inside the urgent window the agent must not run the ask loop at
    all.
    """
    rows = query("SELECT * FROM shifts WHERE id = ?", (shift_id,))
    if not rows:
        print(f"No shift {shift_id}")
        return
    shift = rows[0]
    starts = now() + timedelta(minutes=minutes)
    execute(
        "UPDATE shifts SET starts_at = ?, ends_at = ? WHERE id = ?",
        (iso(starts), iso(starts + timedelta(hours=4)), shift_id),
    )
    print(f"Shift {shift_id} ({shift['role']}) now starts in {minutes} minutes.")
    if shift["required_cert"]:
        print(f"It requires '{shift['required_cert']}'.")
    cancel(shift_id)


def reply(shift_id, volunteer_id, status):
    """Answer as a volunteer.

    Without a volunteer id, answers as whoever is currently being asked. There
    is only ever one - send_ask refuses a second - so a demo never needs to look
    an id up, and never breaks when the ranking changes.
    """
    if volunteer_id is None:
        rows = query(
            "SELECT id, volunteer_id FROM asks WHERE shift_id = ? AND status = 'pending'",
            (shift_id,),
        )
    else:
        rows = query(
            "SELECT id, volunteer_id FROM asks "
            "WHERE shift_id = ? AND volunteer_id = ? AND status = 'pending'",
            (shift_id, volunteer_id),
        )
    if not rows:
        print(f"Nobody is waiting on an answer for shift {shift_id} right now."
              if volunteer_id is None else "No pending ask for that volunteer on that shift.")
        return
    ask = rows[0]
    execute("UPDATE asks SET status = ? WHERE id = ?", (status, ask["id"]))
    name = query("SELECT name FROM volunteers WHERE id = ?", (ask["volunteer_id"],))[0]["name"]
    log_event(status, f"{name} {status} shift {shift_id}.", shift_id)
    print(f"{name} -> {status}")


def doctor():
    """Say which provider will be used, before a tick fails in a stack trace."""
    from agent.core import DEFAULT_MODEL, ProviderNotReady, build_model, resolve_provider

    provider = resolve_provider()
    print(f"provider : {provider or '(none found)'}")
    if provider:
        import os

        print(f"model    : {os.environ.get('FILLIN_MODEL') or DEFAULT_MODEL.get(provider)}")
    try:
        build_model()
        print("status   : ready. Credentials resolve and the model can be built.")
        print("           A tick can still fail if model access is not enabled.")
    except ProviderNotReady as exc:
        print("status   : NOT READY\n")
        print(exc)


def status():
    print("\n--- HANDLED WITHOUT YOU ---")
    for e in query(
        "SELECT * FROM events WHERE kind IN ('asked','filled','timeout','declined',"
        "'accepted','cancelled') ORDER BY id"
    ):
        print(f"  [{e['ts'][11:16]}] {e['kind']:<10} {e['detail']}")

    print("\n--- WAITING FOR YOU ---")
    esc = query("SELECT * FROM escalations WHERE resolved = 0")
    if not esc:
        print("  Nothing. That is the point.")
    for e in esc:
        print(f"  Shift {e['shift_id']} | {e['reason']}\n    {e['detail']}")
    print()


def _run_tick():
    """Run one tick, turning a credentials failure into advice."""
    from agent.core import ProviderNotReady, tick

    try:
        print(tick())
        return True
    except ProviderNotReady as exc:
        print(f"\nThe agent could not reach a model.\n\n{exc}\n")
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]

    if cmd == "cancel":
        cancel(int(sys.argv[2]))
    elif cmd == "urgent":
        urgent(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 90)
    elif cmd in ("accept", "decline"):
        volunteer = int(sys.argv[3]) if len(sys.argv) > 3 else None
        reply(int(sys.argv[2]), volunteer, "accepted" if cmd == "accept" else "declined")
    elif cmd == "status":
        status()
    elif cmd == "doctor":
        doctor()
    elif cmd == "tick":
        _run_tick()
    elif cmd == "loop":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        gap = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        for i in range(n):
            print(f"\n=== tick {i + 1}/{n} ===")
            if not _run_tick():
                return
            if i < n - 1:
                time.sleep(gap)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
