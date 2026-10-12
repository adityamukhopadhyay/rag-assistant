---
title: "Autonomous Delivery Fleet"
slug: "site-delivery-fleet"
kind: "portfolio"
site_slug: "delivery-fleet"
page_url: "https://adityamukhopadhyay.vercel.app/work/delivery-fleet"
source: "site/projects.ts"
themes: ["Agents", "MCP", "Safety & cost"]
---
# Autonomous Delivery Fleet

One Claude agent per rider, per day, supervising real deliveries over WhatsApp — about twenty at once, unattended for a 13-hour shift.

Period: 2026 · Badho. Stack: Python, Claude Agent SDK, MCP, FastAPI, PostgreSQL, Supabase, WAHA, Freshdesk, Railway, React.

## Headline numbers

- **~20** — concurrent agents, one per rider
- **13 h** — unattended per shift
- **23** — offline test suites

## Context

Badho runs a fleet of last-mile riders. Anomaly detection used to be reactive and human: someone noticed a rider was late, or a distributor called. I built a system where **one Claude Agent SDK session supervises one rider's entire day** — it pulls log deltas, decides whether each event is an anomaly, coaches the rider in Hinglish over WhatsApp, alerts the distributor, files a ticket, and escalates only when something is genuinely wrong.

It replaced a LangGraph orchestration with the Agent SDK plus an in-process MCP server, and it runs without anyone watching: sessions auto-start inside the shift window, refill after deploys, and are structurally gated off on Sundays. The brief from the CEO was explicit — riders must experience a supportive partner, not a robotic alerting system.

## How it works

### Nudges were templates all along

Heartbeats, chases, pickup reminders and greetings were most of the model's traffic — and every one, sampled across the corpus, was the same shape: "{name}, {facts} — {action}?". So they became deterministic Python over the snapshot the sweep had already fetched, and the empath subagent was kept for the drafts that genuinely need judgement. Escalation evaluation, inbound replies and log-delta judgement stay with the model, pinned by tests that assert no rule branch creeps in near them. What comes out is a rule/LLM hybrid: the model runs where thinking is required, deterministic code everywhere else.

### Freshness guard — templates can't think, so re-check at send time

Sweeps decide off a snapshot up to five minutes old. The LLM path compensated by instruction ("call get_trip_snapshot first"); a template can't. So every rule-based send re-fetches at the moment of sending and re-verifies its condition: **send** with fresh values, **abort** if the condition cleared, or **fall back to the LLM** if the rider spoke recently — degrade to intelligence, never to a wrong message. It fails open on a fetch failure, deliberately: freshness is an upgrade, not a new dependency.

### Guards below the model, with a deliberate asymmetry

Prompts drift; gates don't. The recipient guard sits at the single path every agent message must take, and **blocks only on a proven mismatch** — the trip's resolved rider phone versus a different plain number — while **allowing every uncertainty**. Blocking on uncertainty would take the whole fleet down on a read-replica blip, which is far worse than the risk it prevents. Alongside it: a respect guard (riders are always `aap`), a figure guard (no invented numbers), sanitised agent-authored tickets, a watchdog that alarms when the *agents* go quiet, and a container that fails its healthcheck if it can't run agents.

### The outage that looked like health

An unpinned transitive dependency (`mcp` 2.0.0) removed an API the SDK called. All 25 auto-started sessions died at start — and stayed registered as running, so the dashboard showed *more* agents than riders, and recovery was impossible because the next start found the corpse. 5h 20m unmonitored. Fixed the same day: rollback on start failure, a test pinning the invariant (N failed spawns ⇒ 0 agents live), and the transitive dep pinned separately. An unpinned transitive dep is a time bomb with a random fuse.

### Quality that tests cannot see

Reading real rider threads found six defects no suite could catch: **35% of sends were content-free** (one rider got eight in a day; fleet reply rate 4%); **12.6% used `tu`/`tum`**; a deadline quoted after it had passed; verbatim repeats across restarts; a stall the counters couldn't see; silence toward a rider who had just explained himself. Each got a structural fix. The design rule that came out of it: be proactive — say what has *not* happened and for how long, and never ask a rider for an update the lifecycle already shows.

### Measure the bill before you optimise it

The SDK's `total_cost_usd` is cumulative per session; summing it per turn had multiplied every spend figure fleet-wide — so the first thing to fix was the measurement, not the cost, reconciled turn by turn against the provider console. Only then the real levers, all architectural: cache re-priming was most of the bill, so a 1-hour prompt-cache TTL; context recycling bounded at 60k tokens; 25 unused built-in tools dropped. Coverage kept scaling while daily spend stayed flat — the saving is a property of the design, not a one-off cut.

## Measured results

- **~20** — concurrent sessions, one per rider (Auto-started for every active rider in the 08:00–21:00 IST window; 22 riders traced on Aug 11. Sundays gated off at every spawn path.)
- **13 h** — unattended per shift (Sessions auto-start inside the shift window, refill after deploys, and are structurally gated off on Sundays — nobody watches the fleet during the day.)
- **23 / ~800** — offline test suites / assertions (Run before every deploy. They pin the guard asymmetries, the registry rollback, the rule/LLM boundary and the figure rules — by construction, templates cannot write numbers.)
- **5h 20m** — the outage I own (25 sessions dead at start, registered as live. Same-day fix, invariant test, dependency pinned.)

## What the numbers do and do not claim

The efficiency here is a property of the architecture, not a headline cut: the same rule/LLM split that makes the fleet predictable is what makes it cheap to run. Where I did trace spend, I traced it per turn against the provider console rather than trusting the SDK's cumulative field — because the figures everyone first quoted turned out to be an artefact of how that field was summed.

## Lessons

- Prompts drift; gates don't. Put every invariant below the model.
- Measure the bill before optimising it — the first number was wrong by an order of magnitude.
- Tests can't see tone. Read the threads.

