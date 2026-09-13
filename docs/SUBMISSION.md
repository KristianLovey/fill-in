# Fill In — Devpost submission text

Each section below maps to a field on the Devpost submission form.

---

## Project name

Fill In

## Elevator pitch

An agent that backfills cancelled volunteer shifts for community kitchens — one fair ask at a time — and only interrupts the coordinator when a real decision exists.

## Track

Good Neighbor Agents

---

## About the project

### Inspiration

A community kitchen runs on volunteers, and volunteers cancel. When someone drops out four hours before a shift, a coordinator starts phoning down a list: first name, no answer; second name, can't; third name, yes. The work isn't hard. It's relentless, it arrives at the worst times, and it always lands on the same person.

It has a quieter failure too. Whoever is phoning reaches for the reliable names first, so the most dependable volunteers get asked the most and burn out the fastest. I wanted an agent that takes the phoning off the coordinator without inheriting that habit.

### What it does

Fill In watches the roster and backfills cancelled shifts on its own:

- It notices an open shift on its next wake-up. Nobody has to tell it.
- It ranks who could cover it: the right certificate, available at that hour, and weighted towards the people who have carried the *least* recently.
- It asks **one** person, then waits out their 20-minute window.
- On a decline or a timeout it moves to the next name. On an accept it books them and stops.
- It escalates to the coordinator — once, with the context to act — only when a human decision genuinely exists: five people asked with no yes, a shift starting within two hours, nobody qualified, or anything ambiguous.

The coordinator's dashboard has two columns. **Handled without you** shows every shift the agent is working and the trail it took down the roster. **Waiting for you** holds escalations, and its normal state is empty.

### Who it's for

The volunteer coordinator at a community kitchen, food bank or shelter. Usually one person, often a volunteer themselves, with no budget for scheduling software and no appetite for another app to check. Fill In is built to *not* be opened.

### How I built it

Fill In is a **Strands Agents** agent. The demo runs on Google's **Gemini** (`gemini-3.5-flash-lite`, on the free tier); the same code runs Claude on Amazon Bedrock or the Anthropic API by changing one environment variable. Nothing about the rules depends on which model is reasoning, because the rules live in the tools.

- **One step per wake-up.** A scheduler calls `tick()`, which gives each open shift a fresh `Agent` and asks it for the single next step: check replies, book an acceptance, ask the next person, wait, or escalate. The agent has no loop of its own and no memory between wake-ups; all state lives in SQLite. In production the scheduler maps directly onto EventBridge calling a Lambda.
- **Six tools, with the rules inside them.** `get_shift`, `rank_candidates`, `send_ask`, `check_replies`, `confirm_and_book` and `escalate_to_human`. Every hard rule is a `return` statement in tool code rather than a sentence in the prompt. `send_ask` refuses an uncertified volunteer, a second person while someone is still deciding, anyone but the fairest remaining candidate, a sixth ask, and any ask inside the two-hour window. The model can be confused or simply wrong and still cannot break them.
- **One channel to a human.** `escalate_to_human` is the only path that reaches a person, and it attaches who could still cover the shift — fairest first, certificate checked — looked up from the database rather than written by the model, so every escalation is actionable. There is no fallback where the agent mentions a problem in its reply and hopes somebody reads it.
- **Fairness scoring.** Recent shifts and recent asks push a volunteer down the ranking, and anyone asked six or more times in 30 days goes to the back of the queue.
- **A Flask dashboard** reading the audit log and the escalations, with a filter, a CSV export of the whole audit trail for reporting, and a manual wake for demos.

### Challenges I ran into

**Rules that only lived in the prompt.** Two of the most important rules — ask one person at a time, and follow the fairness ranking — started out as instructions in the system prompt. Adding a manual "wake now" button made the gap concrete: two wake-ups running together could each pick a different volunteer and send two "we need you" messages for the same shift. Both rules now live in `send_ask`, which recomputes the ranking itself and refuses anything else.

**A demo that changed overnight.** Volunteer availability is weekly, but the seed anchored the roster to "tomorrow", so the same seed produced different rankings on different days. The week now always starts on a Monday, and every ranking is identical whichever day it runs.

**A colour that couldn't carry text.** The amber that means "a person is needed" is 2.2:1 on white — fine for a border, unreadable at 11px. The interface uses the pure hue only for marks and a darkened step of it for every label, with the ratios measured rather than judged by eye.

### Accomplishments I'm proud of

- The model is allowed to be wrong. Every rule it could break is a refusal it can't argue with.
- An empty "Waiting for you" column reads as the product working, not as a blank screen.
- Fairness is visible: the dashboard puts the volunteers carrying the most next to the ones the agent reaches for instead.
- Swapping the model is one environment variable. On its first full run, on Gemini's free tier, the agent followed every rule without a single refusal from the tools — and the refusals were there if it hadn't.

### What I learned

The prompt is the place for judgement — how to word a warm, easy-to-decline message — and tool code is the place for rules. Most of what makes this agent good is what it refuses to do: ask a crowd, wear down the reliable few, or interrupt a person about something it could have handled.

### What's next

- Real channels: send asks by SMS and email, and read replies back in.
- Import real rosters from CSV.
- Deploy on Amazon Bedrock AgentCore Runtime behind an EventBridge schedule.
- Support several sites and coordinators.

---

## Built with

strands-agents · gemini · python · flask · sqlite

## About the data

All volunteers, shifts and availability are synthetic, generated by `data/seed.py`. No real volunteer data was used; the structure mirrors a real volunteer roster.
