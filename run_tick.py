"""Fill In - the scheduler.

The agent has to run without anyone opening anything; that is the whole claim.
This is the smallest thing that makes it true: a loop that calls tick() on an
interval.

  python run_tick.py              every 30 seconds, forever
  python run_tick.py 10           every 10 seconds
  python run_tick.py 10 20        every 10 seconds, 20 times, then stop

In production this process is not the scheduler. The mapping is:

  EventBridge Scheduler (rate: 1 minute)  ->  Lambda  ->  tick()

tick() is already shaped for that: it takes no arguments, holds no state
between calls, reads everything it needs from the database, and is safe to run
again if a firing is duplicated - every hard rule it could violate is enforced
in tool code, not here. The Lambda handler is three lines:

  def handler(event, context):
      from agent.core import tick
      return tick()
"""

import sys
import time

from agent.core import ProviderNotReady, tick
from agent.db import now


def main():
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None

    print(f"Fill In scheduler. Waking every {interval}s. Ctrl-C to stop.")
    fired = 0
    while limit is None or fired < limit:
        fired += 1
        stamp = now().isoformat()[11:19]
        try:
            result = tick()
        except ProviderNotReady as exc:
            # No point looping on a credentials problem - it will not fix itself.
            print(f"[{stamp}] the agent could not reach a model.\n\n{exc}\n")
            return 1
        except Exception as exc:  # a bad tick must not kill the scheduler
            print(f"[{stamp}] tick failed: {type(exc).__name__}: {exc}")
            result = None

        if result is not None:
            if result["open_shifts"] == 0:
                print(f"[{stamp}] nothing open. Waiting.")
            else:
                for item in result["handled"]:
                    if "error" in item:
                        print(f"[{stamp}] shift {item['shift_id']}: {item['error']}")
                    else:
                        print(f"[{stamp}] shift {item['shift_id']}: {item['outcome']}")

        if limit is None or fired < limit:
            time.sleep(interval)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
