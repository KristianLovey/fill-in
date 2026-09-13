# Fill In — demo video script

Target **4:40**, hard limit 5:00. Two live scenarios, both on the real agent.
The voiceover is under 600 words — about 145 a minute, which leaves room to breathe.

## Before you record

1. **Credentials.** `python -m agent.cli doctor` must report *ready*.
2. **Rehearse once, on the same model.** Leave `FILLIN_MODEL` unset. The default,
   `gemini-3.5-flash-lite`, is the model this whole script was verified on end to
   end, and the fastest on the free tier at under a second a call. Do one full
   dry run with it before the real take.
3. **Clean state.** Run `python data/seed.py` right before the take. The roster
   always starts on a Monday, so shift 3 always ranks **Ivan Bozic** first and
   **Ema Grgic** second. Scenario 1 depends on that, and it was checked against
   four different seed dates.
4. **Three terminals.**
   - T1 — `python web/app.py`. Leave it running.
   - T2 — the scheduler. Don't start it yet. It prints every tool call as the
     agent makes it (`Tool #3: rank_candidates`), which is worth having on screen.
   - T3 — the CLI, standing in for the volunteers.
5. **Browser** at `http://127.0.0.1:5000`, window about **1440 px wide**, zoom
   100 %. At that width the top bar fits on one line. Hide the bookmarks bar and
   turn notifications off.
6. **Recorder.** Win + Alt + R (Xbox Game Bar) records a single window, and
   Clipchamp, built into Windows 11, is enough to trim. Record each scene
   straight through and **cut the waiting in the edit**. Don't press *Wake now*
   on camera during scenario 1 — the whole point is that nobody touched it.

---

## 0:00 – 0:30 · The problem

**Screen:** the empty dashboard, or a title card.

> Every community kitchen has a coordinator, and every week somebody cancels a
> shift. So the coordinator picks up the phone and works down the list. First
> name — no answer. Second — can't make it. Third — yes. It isn't hard work.
> It's relentless, it comes at the worst times, and it always lands on the same
> person.

## 0:30 – 0:50 · Who it's for

> Fill In is for that coordinator — at a food bank, a shelter, a community
> kitchen. Usually one person, often a volunteer themselves, with no budget for
> scheduling software and no time for another app.

## 0:50 – 1:15 · Why it matters

> There's a second problem hiding inside the first. Whoever's phoning reaches for
> the reliable names first, so the most dependable volunteers get asked the most
> and burn out the fastest. Fill In takes the phoning away without inheriting
> that habit. It runs in the background, and it only comes to you when there's a
> real decision to make.

## 1:15 – 2:50 · Scenario 1 — plenty of notice

**T3:**

```
python -m agent.cli cancel 3
```

> Someone has just dropped out of Monday's warehouse shift. That's the last thing
> I'm going to do.

**T2:**

```
python run_tick.py 30
```

Every 30 seconds rather than 20, to stay clear of the free tier's per-minute
limit.

**Screen:** within seconds the heartbeat updates and a *Warehouse sorting — In
progress* card appears, with Ivan Bozic deciding and a countdown running.

> The agent woke up on its own. It ranked everyone who's free at that time, and
> it asked exactly one person: Ivan, who hasn't worked a shift this month.

**Point at the Fairness panel.**

> These three have carried the most this month, so they go to the back of the
> queue. That isn't a suggestion to the model — the tool that sends the message
> refuses anyone but the person at the top of this ranking.

**T3:**

```
python -m agent.cli decline 3
```

**Screen:** on the next wake-up Ivan turns to *declined* and Ema Grgic starts
deciding.

> Ivan can't make it, so it moves to the next name — still one person at a time.
> Nobody gets a group message saying "we need you".

**T3:**

```
python -m agent.cli accept 3
```

**Screen:** on the next wake-up the card flips to *Covered*, the audit log shows
*filled*, and the *shifts covered* tile goes to 1.

> Ema says yes. It books her, stops asking, and logs every step. I didn't touch
> any of it.

## 2:50 – 3:40 · Scenario 2 — a real decision

**T3:**

```
python -m agent.cli urgent 1 90
```

> Now a different cancellation: meal prep, starting in ninety minutes, and it
> needs a food-safety certificate.

**Screen:** leave the scheduler running. On the next wake-up a single amber card
appears under *Waiting for you*, and the waiting tile turns amber.

> This time it doesn't ask anyone. With under two hours to go, a message somebody
> might read in twenty minutes is the wrong tool — so it escalates straight away.
> One card, with what I need to act: the shift, the certificate, that nobody's
> been contacted — and who could cover it, fairest first. That list doesn't come
> from the model. The tool looks it up, so it's there however the model writes.

**Stop the scheduler** (Ctrl + C in T2).

## 3:40 – 4:20 · How it works

**Screen:** `docs/architecture.svg`, then `agent/tools.py` scrolled to `send_ask`.

> Under the hood it's a Strands agent running on Gemini, with six tools. A
> scheduler wakes it, it takes one step per shift, and it stops. Every hard rule — the certificate, the
> ask limit, the two-hour window, one person at a time, the fairness order — is a
> return statement in the tools, not a sentence in the prompt. The model can be
> wrong and still can't break them. And there's exactly one way for it to reach
> a person: escalate to human, the one amber arrow in this diagram. In
> production, that scheduler becomes EventBridge calling a Lambda.

## 4:20 – 4:40 · Close

**Screen:** back to the full dashboard — teal everywhere, one amber card.

> **[N]** decisions handled without me. One question for me.
>
> Nobody phones down the list any more.

Read **N** off the *decisions handled* tile and say the number that is actually
on screen. After both scenarios exactly as scripted it reads **7** — that is what
the first real run produced. For a bigger number, cancel a few more shifts off
camera first (`cancel 7`, `cancel 12`) and let the agent really work them before
this shot.

---

## If something goes sideways

| What you see | What to do |
|---|---|
| The bar says *connection lost* | T1 stopped. Run `python web/app.py` again; the page reconnects on its own. |
| A red toast after *Wake now* | No model is reachable. Run `python -m agent.cli doctor`. |
| Scenario 1 escalates as "ambiguous" | The rehearsal model is too weak. Record with the stronger one. |
| Nothing moves after `decline 3` | The scheduler interval hasn't elapsed, or the model call is slow. Wait, and cut it in the edit. |
| `503 … high demand` or `429 Too Many Requests` in T2 | Google's free tier is briefly busy, or the per-minute limit was hit. A failed wake-up does nothing, and the next one retries on its own. Keep recording and cut the gap. |
| You need a clean slate | `python data/seed.py`, then refresh the page. |
