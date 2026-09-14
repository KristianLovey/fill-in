# Fill In: Devpost submission text

Each section below goes into the matching field on the Devpost form.

## Project name

Fill In

## Elevator pitch

An agent that backfills cancelled volunteer shifts for community kitchens, one fair ask at a time and only interrupts the coordinator when a real decision exists.

## Track

Good Neighbor Agents

## About the project

### Inspiration

A community kitchen depends on volunteers, and volunteers cancel. When someone drops out a few hours before a shift, the coordinator starts phoning people on a list. The first person doesn't answer, the second can't come, the third says yes. It isn't difficult work, but it comes up all the time, often at bad moments, and it always lands on the same person.

There is also a less obvious problem. The person making the calls usually starts with the most reliable volunteers, so those people get asked the most and are the first to burn out. I wanted an agent that takes over the phoning without repeating that pattern.

### What it does

Fill In watches the roster and backfills cancelled shifts on its own:

- It notices an open shift the next time it wakes up.
- It ranks who could cover it: people with the right certificate who are available at that time, with priority for those who have done the least recently.
- It asks one person and waits for their 20-minute response window.
- If they decline or don't answer, it moves to the next person. If they accept, it books them and stops.
- It escalates to the coordinator once, with the information needed to act, only when a person has to decide: five people asked without a yes, a shift starting within two hours, nobody qualified, or an unclear situation.

The dashboard has two columns. **Handled without you** shows each shift the agent is working on and who it has asked so far. **Waiting for you** shows escalations, and it is usually empty.

### Who it's for

Volunteer coordinators at community kitchens, food banks and shelters. This is usually one person, often a volunteer, with no budget for scheduling software and no time to keep checking another app. Fill In is meant to run in the background without being watched.

### How I built it

Fill In is a **Strands Agents** agent running on **Amazon Nova 2 Lite through Amazon Bedrock**. The same code can run on Gemini or Claude by changing one environment variable. The rules don't depend on the model because they are enforced in the tools.

- **One step per wake-up.** A scheduler calls `tick()`, which creates a fresh `Agent` for each open shift and asks it for the next step: check replies, book someone who accepted, ask the next person, wait, or escalate. The agent has no loop and no memory between wake-ups. All state is stored in SQLite. In production the scheduler would be EventBridge calling a Lambda.
- **Six tools that enforce the rules.** `get_shift`, `rank_candidates`, `send_ask`, `check_replies`, `confirm_and_book` and `escalate_to_human`. Hard rules are checked in the tool code instead of being described in the prompt. `send_ask` refuses a volunteer without the certificate, a second person while someone is still deciding, anyone other than the fairest remaining candidate, a sixth ask, and any ask within two hours of the shift. If the model makes a mistake, the tools still block it.
- **One way to reach a person.** `escalate_to_human` is the only path to the coordinator. It adds the volunteers who could still cover the shift, fairest first and with the certificate checked, taken from the database rather than written by the model. The agent has no other way to flag a problem.
- **Fairness scoring.** Recent shifts and recent asks lower a volunteer's score, and anyone asked six or more times in 30 days goes to the back of the queue.
- **A Flask dashboard** that reads the audit log and escalations, with a filter, a CSV export of the audit trail and a manual wake button for demos.

### Challenges I ran into

**Rules that were only in the prompt.** At first, two important rules (ask one person at a time, and follow the fairness ranking) were only instructions in the system prompt. When I added a manual "wake now" button, it became clear this wasn't enough: two wake-ups at the same time could each pick a different volunteer and send two messages for the same shift. Both rules are now enforced in `send_ask`, which recalculates the ranking itself and refuses anything else.

**A demo that changed from one day to the next.** Volunteer availability is weekly, but the seed script started the roster "tomorrow", so the same seed gave different rankings on different days. The week now always starts on a Monday, so the rankings are the same whenever it runs.

**AWS credits and the model choice.** I planned to use Claude on Amazon Bedrock, but Anthropic models on Bedrock can be billed through AWS Marketplace, and promotional credits don't cover that. I switched to Amazon Nova, which is billed as Bedrock. Because the rules are in the tools, the switch was a one-line change.

**Colour contrast.** The amber that marks "a person is needed" has a 2.2:1 contrast ratio on white, which works for borders but not for small text. The interface uses the bright colour only for borders and bars, and a darker shade for text. I checked the contrast ratios with a script.

### Accomplishments that I'm proud of

- The agent can make mistakes without breaking any rule, because every rule is enforced by the tools.
- An empty "Waiting for you" column means everything has been handled.
- Fairness is visible on the dashboard, which shows the busiest volunteers next to the ones the agent asks instead.
- The rules held on every model I tested. The full demo ran end to end on Gemini 3.5 Flash-Lite and on three Amazon Nova models. When Nova Lite skipped the fairest volunteer, and later used a volunteer id that didn't exist, the tools refused and it corrected itself. When the Nova models tried to ask a volunteer about a shift starting within two hours, the tool refused and they escalated instead.

### What I learned

The prompt is useful for judgement, like writing a friendly message that is easy to say no to. Rules belong in code. A lot of what makes this agent useful is what it doesn't do: it doesn't message a crowd, it doesn't keep asking the same reliable people, and it doesn't bother the coordinator with things it can handle itself.

### What's next

- Send asks by SMS and email and read the replies automatically.
- Import real rosters from CSV.
- Deploy on Amazon Bedrock AgentCore Runtime with an EventBridge schedule.
- Support multiple sites and coordinators.

## Built with

strands-agents, amazon-web-services, amazon-bedrock, amazon-nova, gemini, python, flask, sqlite, javascript

## About the data

All volunteers, shifts and availability are synthetic and generated by `data/seed.py`. No real volunteer data was used. The structure follows a real volunteer roster.
