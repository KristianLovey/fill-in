<p align="center">
  <img src="docs/logo.png" alt="Fill In logo" width="220">
</p>

# Fill In

**Nobody phones down the list any more.**

Fill In backfills cancelled volunteer shifts for a community kitchen. When
someone drops out, it works through the roster one person at a time. It asks,
waits for an answer, moves on if needed, and stops as soon as the shift is
covered. The coordinator only hears about it when a person has to make a
decision.

Built with [Strands Agents](https://strandsagents.com) for the AWS *Agents for
Humans* hackathon, Good Neighbor track.

## The problem

A community kitchen runs on a roster of volunteers. Someone cancels four hours
before their shift, and a coordinator starts phoning down a list asking who is
free tonight. The first person doesn't answer, the second can't make it, the
third says yes.

None of this is hard, but it happens all the time, often at bad moments, and it
always falls on the same person. There is a second problem too. Whoever is
phoning tends to call the reliable people first, so the most dependable
volunteers get asked the most and burn out first.

## Who it is for

The volunteer coordinator at a small community kitchen, food bank or shelter.
That is usually one person, often a volunteer themselves, with no budget for
scheduling software and no time to keep checking another dashboard. Fill In is
meant to run without being watched, so most of the time the right-hand column of
the dashboard is empty.

## What it does

| | |
|---|---|
| A shift opens up | The agent notices on its next wake-up |
| It picks who to contact | The fairest candidate first (see [Fairness](#fairness)) |
| It asks one person | It waits for their full response window |
| They decline or don't answer | It moves to the next name |
| Someone accepts | It books them and stops asking |
| It runs out of options | It escalates once, with what the coordinator needs to act |

## How it works

![Architecture](docs/architecture.svg)

A scheduler wakes the agent. On each wake-up the agent takes one step for every
open shift and then stops. It has no loop of its own and no memory between
wake-ups, and it can only act through six tools. All state is kept in SQLite,
and every action is written to an audit log that the dashboard shows.

### Rules are enforced in the tools

The main design decision is that hard rules are checked in code instead of
being described in the prompt. A missing certificate, a used-up ask limit or a
shift that starts too soon each end in a `return` in
[`agent/tools.py`](agent/tools.py):

```python
if required and required not in vol["certs"].split(","):
    return {"refused": f"{vol['name']} does not hold '{required}'."}
```

The prompt tells the model what to do, but the tools decide what is allowed.
Even if the model gets confused or makes a mistake, it cannot book someone
without the required certificate, ask two people at once, skip the fairest
volunteer, ask someone who already said no, or contact a person in any way
other than `escalate_to_human`.

### Escalation policy

| Situation | What the agent does | Who is involved |
|---|---|---|
| A qualified volunteer is free and hasn't been asked | Asks one of them and waits | Nobody |
| Someone is still inside their response window | Refuses to ask anyone else | Nobody |
| The model picks someone other than the fairest remaining candidate | Refuses and says who ranks first | Nobody |
| The person declines or their window expires | Moves to the next name | Nobody |
| Someone accepts | Books them and releases the others | Nobody |
| 5 people asked and nobody accepted | `escalate_to_human` | **You** |
| The shift starts within 2 hours | Escalates straight away without asking anyone | **You** |
| Nobody qualified is available | Escalates | **You** |
| Anything is unclear | Does nothing and escalates | **You** |

`escalate_to_human` is the only way the agent can reach a person. There is no
fallback where it writes about a problem in its reply and hopes someone reads
it.

Each escalation also lists who could still cover the shift: the three fairest
volunteers who hold the certificate and are free at that time. The tool looks
this up in the database and adds it, so it is included no matter how the model
wrote the rest of the message.

Policy constants, all in [`agent/tools.py`](agent/tools.py):

| Constant | Value | Meaning |
|---|---|---|
| `ASK_TIMEOUT_MINUTES` | 20 | How long one person has to answer |
| `MAX_ASKS_PER_SHIFT` | 5 | After this many asks, a person decides |
| `URGENT_WINDOW_HOURS` | 2 | Inside this window the agent doesn't ask anyone |
| `FATIGUE_ASKS_30D` | 6 | Volunteers asked this often recently move to the back of the queue |

### Fairness

`rank_candidates` removes anyone without the required certificate or without
availability at that hour, then scores the rest by how much they have done
recently:

```
score = 100 - (shifts_last_30d * 8) - (asks_last_30d * 4) + (response_rate * 20)
        - 30 if asked 6 or more times in the last 30 days
```

The prompt asks the model to follow this order, and `send_ask` checks that it
does. It recalculates the ranking and refuses anyone except the volunteer at the
top, so the model can't pick someone else because they seem more likely to say
yes. Volunteers who were already asked drop out of the ranking, and asking the
same person twice is refused. The aim is to spread the work out instead of
wearing down the most reliable people.

## Setup

```bash
pip install -r requirements.txt
python data/seed.py
```

Then set up a model. Any of the three providers below works. The hackathon
requires Strands, not a particular model provider.

**Google Gemini (free tier, no card needed)**

```bash
pip install "strands-agents[gemini]"
setx GEMINI_API_KEY "your-key"
setx FILLIN_PROVIDER gemini
```

Create the key at [Google AI Studio](https://aistudio.google.com/apikey). On
Windows you don't need to open a new terminal after `setx`, because Fill In
also reads the user environment directly. Keep billing turned off on that
project to stay on the free tier. Google may use free-tier requests to improve
its products. All data in this repo is synthetic, so nothing real is sent.

**Amazon Bedrock (used for the demo)**

Put an IAM user's access key in `~/.aws/credentials` and `region = us-east-1`
in `~/.aws/config`, or use the standard `AWS_*` environment variables. Then:

```bash
setx FILLIN_PROVIDER bedrock
```

The IAM user needs `AmazonBedrockFullAccess`. The default model is Amazon Nova 2
Lite (`us.amazon.nova-2-lite-v1:0`). It is Amazon's own model and is billed as
Amazon Bedrock, so AWS credits apply to it. Anthropic models on Bedrock can be
billed through AWS Marketplace, which promotional credits don't cover. A new AWS
account rejects model calls with "Your account is currently being verified"
until verification is complete.

**Anthropic API**

```bash
pip install "strands-agents[anthropic]"
set ANTHROPIC_API_KEY=...
set FILLIN_PROVIDER=anthropic
```

Check which provider and model the agent will use:

```bash
python -m agent.cli doctor
```

| Variable | Default | Notes |
|---|---|---|
| `FILLIN_PROVIDER` | whichever credentials exist | `gemini`, `bedrock` or `anthropic` |
| `FILLIN_MODEL` | `gemini-3.5-flash-lite` (Gemini)<br>`us.amazon.nova-2-lite-v1:0` (Bedrock)<br>`claude-sonnet-5` (Anthropic) | For example `gemini-3.8-flash` for a stronger Gemini model, or `claude-haiku-4-5` to test cheaply on Anthropic |
| `PORT` | `5000` | Dashboard port |

### Run it

Use two terminals. Start the agent in one:

```bash
python run_tick.py 30        # wake every 30 seconds
```

And the dashboard in the other:

```bash
python web/app.py           # http://127.0.0.1:5000
```

The dashboard has two columns.

**Handled without you** (left, teal) shows each shift the agent is working on as
a card with its ask chain: who was asked, in what order, what they answered, who
is still deciding and how long they have left, and how many asks remain before a
person has to step in. The full audit log is below the cards.

**Waiting for you** (right, amber) shows unresolved escalations. Each one
includes the shift, the certificate it needs, who has already been contacted
and who could cover it. Amber is only used for this. When nothing needs
attention, the column shows a green all-clear message.

The right side also shows **Fairness** (recent shifts for the three busiest
volunteers next to the three the agent asks instead, on the same scale), **the
roster this week** (one dot per shift) and the **policy** the tools enforce.

On a phone the page switches to one column and **Waiting for you** moves to the
top, so the thing that needs attention is seen first.

The dashboard uses a light frosted-glass style: translucent cards over a soft
pastel background. Colours have fixed meanings: teal for work the agent handled,
amber only for escalations, and green for the all-clear state. The bright teal
(3.3:1 contrast on white) and amber (2.2:1) are used for borders, bars and dots,
and text uses darker shades that stay above 4.5:1 on the glass. The font is SF
Pro on Apple devices and Inter everywhere else, served from `web/static/fonts/`,
so the page looks the same offline.

The top bar has four actions:

| Action | Shortcut | What it does |
|---|---|---|
| Filter | `/` | Filters shift cards and the audit log by role, volunteer or certificate |
| Wake now | `w` | Runs one `tick()` straight away, the same one the scheduler runs, so a demo doesn't have to wait 30 seconds |
| Live / Paused | `p` | Pauses auto-refresh while you read a card or record a still |
| Export log | | Downloads the full audit trail as CSV |

If the dashboard loses its connection to the server, the status dot stops
pulsing and the top bar shows a message, so old data is never mistaken for live
data.

## Two scenarios

**Plenty of notice, handled without the coordinator**

```bash
python -m agent.cli cancel 3        # someone drops out of Monday's warehouse shift
python run_tick.py 30               # watch the agent work
```

The agent wakes up on its own, asks the fairest candidate and waits. Reply as
that volunteer from a third terminal. Only one person is asked at a time, so you
don't need a volunteer id:

```bash
python -m agent.cli decline 3
python -m agent.cli accept 3
```

After a decline it asks the next person, and after an accept it books them. The
amber column stays empty.

**Starts soon and needs a certificate, escalated straight away**

```bash
python -m agent.cli urgent 1 90     # shift 1 now starts in 90 minutes
python -m agent.cli tick
```

Inside the two-hour window the agent doesn't ask anyone. It escalates once, and
an amber card appears with the shift, the certificate it needs, a note that
nobody has been contacted, and who could cover it.

Other commands: `status` (both columns in the terminal), `loop n secs` and
`doctor`. Run `python -m agent.cli` to see all of them.

## Production

The scheduler here is a simple `while` loop. In production it would be:

```
EventBridge Scheduler (rate: 1 minute) -> Lambda -> tick()
```

`tick()` already fits this. It takes no arguments, keeps no state between
calls, reads everything from the database and can safely run twice if a trigger
fires twice, because the rules are enforced in the tools and not in the caller.
The Lambda handler is three lines and is included in [`run_tick.py`](run_tick.py).

## Project layout

```
agent/tools.py      the six tools, where every hard rule is checked
agent/core.py       the Strands agent, the system prompt and tick()
agent/db.py         a thin SQLite layer; log_event() writes the audit trail
agent/cli.py        demo driver that stands in for volunteers replying
run_tick.py         the scheduler
web/app.py          the dashboard
data/schema.sql     volunteers, availability, shifts, asks, escalations, events
data/seed.py        25 synthetic volunteers and one week of shifts
docs/               architecture diagram, logo and submission text
```

## About the data

The volunteers, shifts and availability in this repo are synthetic and generated
by [`data/seed.py`](data/seed.py). No real volunteer data was used. The random
seed is fixed and the week always starts on the next Monday, so the roster and
every fairness ranking are the same whichever day you run it. The structure
follows a real volunteer roster, with certificates, weekly availability and an
uneven spread of recent work, since that unevenness is what the fairness scoring
is meant to correct.

## Licence

MIT, see [LICENSE](LICENSE).
