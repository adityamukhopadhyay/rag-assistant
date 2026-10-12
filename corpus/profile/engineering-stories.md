---
title: "Engineering stories — problems, decisions, failures and fixes"
slug: "engineering-stories"
kind: "profile"
source: "INTERVIEW_PREP.md (story bank)"
---
# Engineering stories — how the projects were built, what failed, what changed

Every project in the story arc they asked for:
**Problem → What I built → Why I designed it that way → What failed → What I changed →
Result → What I'd do differently.**

Learn the *shape*, not the words. The "what failed" beat is the one that wins these
interviews — most candidates have nothing there.

---

## 1. Autonomous Delivery Fleet — the flagship

**Problem.** Delivery problems surfaced only when a human noticed a rider was stuck. No one
was watching 20 riders through a 13-hour shift.

**What I built.** A root orchestrator agent runs each rider's day, ~20 concurrent, delegating
to specialised sub-agents: an empath that drafts every Hinglish message, a driver-profile
analyst that sets tone from history, an escalation governor, a judgement tiebreaker, and a
Google Maps route planner. All of them act through one in-process MCP server — trip snapshot,
log deltas, telemetry, SQL, WhatsApp, push, Freshdesk tickets, vision over rider photos.

**Why this design.** One big prompt cannot hold "be empathetic", "decide whether to escalate",
and "plan a route" without the objectives bleeding into each other. Splitting them gives each
sub-agent one job I can test in isolation, and it lets me run a cheap model where judgement
isn't needed. Guards sit *below* the model, not inside the prompt — the model can ask to send
a message, but code decides whether it's allowed.

**What failed.** The WhatsApp session it depends on died and **nothing alerted for 48 hours**.
Health checks were green because the process was up. The bot was simply silent.
Separately, the Anthropic key ran dry and the same thing happened — 27 hours of silence, with
`/health` reporting fine, and one log line repeating: `reply_agent_unavailable`.

**What I changed.** Liveness probes that exercise the actual dependency — the WhatsApp session
and the model key — and flip the health endpoint when they fail, short-circuiting before
spending. Count what's actually failing (`inbox.failed`), not what merely exists.

**Result.** Runs unattended across 13-hour shifts, 23 offline test suites, plus an "Ask the
fleet" agent operators query directly.

**Differently.** I'd build the observability before the agents, not after. Every silent
failure I've hit traced back to a health check that didn't touch the thing it claimed to check.

**If they ask "how does this scale past ~20 riders?"** — the answer is the pattern already
running in the WhatsApp agent, and say so explicitly: one queue and one worker per entity so a
single rider's actions stay strictly ordered, plus a global slot gate bounding how many agent
turns hold a subprocess at once. Today the fleet runs an orchestrator per rider directly
because ~20 fits in memory; the moment that number grows, riders become queued entities
competing for a bounded pool of turn slots rather than each holding a live process. The
per-entity ordering guarantee is what you must not lose — two turns racing on one rider's
state is the bug that pattern exists to prevent.

> **The line to land:** *"A health check that doesn't exercise the dependency is worse than no
> health check — it converts a loud failure into a silent one."*

---

## 2. Buyer MCP — the buyer app as ~100 agent tools

**Problem.** Agents had no safe way to act inside the buyer app. Anything they did would
either bypass business rules or reimplement them and drift.

**What I built.** An MCP server in TypeScript exposing the app as ~100 typed tools — search,
carts, coupons and schemes, deeplinks, orders, cancellations, wallet, vouchers, tickets —
behind phone-OTP OAuth and per-buyer JWTs. It imports the app's *own* cart and coupon
functions so a price an agent quotes can never differ from the app's.

**Why this design.** Typed tools over free-form API access means the agent can only do things
I've explicitly allowed, and the schema is the contract. Importing the app's pricing code
rather than reimplementing it was deliberate: two implementations of a discount always diverge.

**What failed.** Two things, both real.

1. *One — a stale import cost money.* Because I imported by relative path from my own branch,
when the app fixed `Number(null) → 0` on an uncoupon cap upstream, my copy kept the bug. Any
**uncapped** coupon made the agent quote ₹0 discount while the app charged correctly. Nothing
in my own diff showed it — every file I'd touched was correct.
2. *Two — a permission hole.* Stress-testing, I found `list_vouchers` returned the **same 179
voucher rows including unredeemed codes** for two different buyers. The backend's row-level
permission didn't scope that table at all.

**What I changed.** For the first: re-synced, and made "diff the *imported* paths against
production, not just your own files" a required step of every sync. For the second: forced the
buyer ID into the query on my side, and reported the underlying permission gap upstream — my
fix closed my door, it didn't close the hole.

**Result.** Serves the production sales agent, Claude Desktop and Claude Code.

**Differently.** Consume shared logic as a versioned package, never a relative path across
branches. A stale copy should be a visible version number, not an invisible file.

> **The line to land:** *"A relative import is resolved by your checkout, not by production.
> Same repo doesn't mean same code."*

---

## 3. WhatsApp AI Sales Agent

**Problem.** Retailers ask questions and abandon carts faster than a sales team can answer.

**What I built.** A live agent that searches the catalogue, builds carts, applies coupons,
sends order deeplinks, answers order and cancellation questions from live state, handles
complaints and images, and raises support tickets — acting through Buyer MCP.

**Why this design — the key architectural decision.** The agent is **split in two**. A
tool-using worker reasons and calls tools; a separate **tool-less reply agent is the only
thing that ever speaks to the buyer.** The worker's text never reaches a human. That means a
worker that hallucinates mid-reasoning cannot leak that to a retailer, and the only surface I
have to police for tone and claims is one small model with no tools.

**What failed.** I shipped a **regex gate** on outbound messages to stop false claims — and
killed it the same day. Regex cannot tell "your order is placed" from "once your order is
placed", so it blocked correct messages and passed wrong ones.

**What I changed.** Replaced it with a real pipeline: the reply agent *declares* its claims as
structured output, a separate tool-less verifier judges those claims against fetched facts,
the worker does a verify-first pass, and the message is re-drafted or withheld. It fails
closed — if the source of truth is unreachable, nothing is sent.

### The concurrency model — know this cold, it's the strongest systems answer you have

This is the part interviewers dig into, because it's a real distributed-systems design and not
prompt work. Two layers, and the distinction matters:

**Layer 1 — one agent per buyer.** Every chat gets its own queue and its own worker task:

```python
_queues:  dict[str, asyncio.Queue] = {}   # phone -> pending messages
_workers: dict[str, asyncio.Task]  = {}   # phone -> the task draining it
```

A buyer's turns are therefore **strictly ordered** — they can't race or stack replies — while
**different buyers run fully in parallel**. Workers exit after 10 minutes idle
(`CHAT_WORKER_IDLE_S=600`) and are recreated on the next message, so idle chats cost nothing.
There's a race guard on exit: if a message lands while the worker is shutting down, it
respawns rather than dropping it.

**Layer 2 — a global slot gate decides who actually runs.** Each turn spawns a Claude CLI
subprocess of roughly 200MB. Spawning hundreds at once OOMs the box, so an
`asyncio.Condition` bounds concurrent turns (`MAX_CONCURRENT_TURNS=8`):

```python
async with _turn_cv:
    while _active_turns >= limit:
        await _turn_cv.wait()      # this chat waits its turn
    _active_turns += 1
# ... run the turn ...
    _turn_cv.notify(1)             # a freed slot wakes the next waiting chat
```

**This is the bit to say out loud:** a flood *queues and drains* instead of crashing. As a slot
frees, the next waiting chat proceeds. The limit is re-read from config on every acquire, so
it's tunable from the dashboard without a redeploy.

**Two refinements worth mentioning if they probe:**

*Debounce.* Rapid-fire messages coalesce into one turn (1.5s window). Images get 8s, because
the caption lands seconds after the photo — without it the agent answered "what's in the
photo?" while the question was still in flight.

*A warm session pool.* One live SDK client kept per phone between turns, LRU-capped at 20,
evicted after 6 minutes idle, recycled every 12 turns to bound context growth. **This is only
safe because each phone has a single serial worker** — the client is never used concurrently.
Any reuse error discards the client and the turn retries fresh, so it can only ever be a
speed and cost optimisation, never a behaviour change.

*A staleness gate placed deliberately.* Checked **before** taking a slot, minting a JWT or
calling the model — so a stale turn costs nothing. Age is read from the buyer's newest stored
message rather than the message object, which catches turns that were fresh when queued but
aged out waiting behind a backlog. Fails closed: unknown age means skip.

**Result.** Handles buyer chats end to end in production. Enforces register rules too (formal
*aap*, never *tu*), and returns an explicit no-reply signal when a chat is concluded rather
than making small talk.

**Differently.** I'd have written the claim taxonomy before the prompt. I built the behaviour
first and the definition of correctness second, which is why the first gate was wrong.

> **The line to land:** *"Pattern-matching the output is not verification. The model must say
> what it's claiming, and something else must check it against the source of truth."*

---

## 4. Courier Ops Autopilot (the Delhivery automation)

**Problem.** Weight overcharges and failed deliveries with our courier partner went unclaimed
because filing was manual, so real money was being left on the table every week.

**What I built.** A FastAPI backend, an operator dashboard, and a bearer-gated remote MCP over
the courier's API that auto-files weight claims using **vision over sorter images**, raises
NDR/lost/damaged tickets, and drafts vendor replies.

**Why this design.** The claims are repetitive and evidence-based — exactly where a model with
a tool beats a human. Vision was needed because the proof is a photo of the parcel on the
sorter. A cheap fast model handles the bulk; the expensive one isn't needed for this.

**What failed / what I designed against.** The vendor's session can die mid-run. Without a
guard, every loop keeps calling the model against a dead dependency — burning money producing
nothing.

**What I changed.** **One liveness gate halts every loop and every model call** the moment the
vendor session dies. Nothing downstream runs against a dead upstream.

**Result.** 698 claims and 370 tickets filed in the first 24 hours; 2,143 closed to date.

**Differently.** I'd add a spend ceiling per run as a second belt — liveness protects against
a dead dependency, not against a live one behaving unexpectedly.

---

## 5. Search, Matching & Catalog Intelligence

**Problem.** Three at once: retailers search in Hinglish and phonetic spellings ("biscut"),
85,000+ SKUs had no variant grouping, and 170,000+ competitor SKUs needed mapping to our
catalogue for price intelligence.

**What I built.**

- **Search:** FAISS over locally-served `nomic-embed-text` vectors, Postgres full-text +
`dmetaphone` for phonetic spellings, sub-100ms.
- **Clustering:** label normalisation (strip brand and promo text to isolate the variant
string) → `all-MiniLM-L6-v2` 384-dim embeddings → **HDBSCAN** per brand, switching to
**K-Means above ~1,000 SKUs** to hold sub-second latency. Hybrid Euclidean + Levenshtein
distance.
- **Matching:** a cost-tiered cascade — exact, then `pg_trgm` trigram candidates scored
50% full-text / 35% trigram / 15% phonetic, and only genuine ambiguity (100g vs 200g)
reaches a batched LLM call.

**Why this design.** Token spend scales with *difficulty*, not volume — most matches never
touch a model. HDBSCAN finds density blobs without being told how many clusters exist, but
degrades on large brands, hence the K-Means switch. And the commercially important piece is a
filter applied **after** retrieval: candidates are intersected with live inventory for the
buyer's mapped sellers, so nothing undeliverable ever surfaces.

**What failed.** The model wrote cluster mappings that were sometimes wrong, and a wrong
sister-product mapping is visible to every buyer.
Separately, the agent's product search turned out to be **brand-blind** — it couldn't tell
"we don't sell this" from "this didn't match", so the agent implied we stocked things we don't.

**What I changed.** **Shadow-write staging** — every cluster elects a primary SKU and mappings
land in a *draft* table with a confidence score, noise flagged −1; catalogue managers approve
in bulk; human labels always override model labels (`COALESCE(humanId, aiId)`). No model
output reaches production without a reviewable step. For search, I made the brand scope
complete and paginated, so off-scope now definitively means "not sold" — and the agent says so
and pivots rather than guessing.

**Result.** ~40,000 product groups mapped; sister-product conversion 40% → 60%;
170,000+ SKUs matched.

**Differently.** I'd have measured cluster precision against a labelled sample before shipping,
rather than relying on review to catch it downstream.

---

## 6. Order-Lifecycle WhatsApp Notifications — **your best failure story**

**Problem.** Buyers heard nothing as their orders moved.

**What I built.** An event-driven engine over the read replica — per-stage pollers, an
idempotent send ledger keyed on order+stage, event-time guards, per-flow scope gates,
boot-time template checks — sending WhatsApp updates through Meta-approved templates.

**Why this design.** Idempotency at the ledger, not in application logic, because retries and
redeploys are certain. Read replica so the service *cannot* write to the order system by
construction. Shipped OFF behind three gates: an API key, an enable flag, and a phone
allowlist.

**What failed — three real incidents, tell them in this order:**

**(a) The stale-message blast.** One day, 497 buyers got *"your order is delivered ✅"* for
orders completed between Feb 2024 and Jun 2026. Root cause: a backend job bulk-stamped
**15,018 order rows with one identical `updated_at`**. My poller found work by asking "what
changed since I last looked?" — so to it those rows were 8 minutes old. The audit table later
showed the job was a **weight recomputation**: it touched `updated_at` and `totalWeightInGram`
and nothing else. No order activity at all.
**Why my existing guard missed it:** my lag limit bounded the age of the *cursor*, not the age
of the *event*.
**Fix:** an event-recency guard — a row only sends if **its own** event timestamp is recent;
a bulk-cluster guard on the other tick (any >50-row identical-timestamp cluster dropped whole,
against a measured natural maximum of 9); and I removed the `COMPLETED → delivered` mapping
entirely, because completion is a cron that runs ~7 days *after* delivery and was never a
delivery event. Proven by **replaying the incident with the clock frozen** — the guard blocked
2,140 stale rows and passed 64 genuine ones. Both guards then caught real bulk touches within
minutes of deploy.

**(b) The overpayment.** A message told buyers how much cash to pay on delivery and used the
order **total** instead of the **remaining due** — coupons and wallet credit make those differ.
106 buyers were told to overpay, ₹17,776 in total. I fixed the field and then **deleted the
total from that message's context entirely**, so the wrong number can't reach a buyer again.

**(c) The refund that wasn't.** A returns message inferred *"nothing due, so they must have
paid, so promise a refund."* But the balance is **zeroed on cancellation** too. Replaying over
real history: wrong on **1,323 of 2,181** returns. Caught before it shipped. Fixed by reading
`refundableAmount` — the actual fact — and re-replaying over 2,387 orders, all correct.

**Result.** 10 order stages, ~500 messages a day to the whole buyer base.

**Differently.** I'd treat *every* timestamp column as untrusted until proven to be an event
time. We now have a standing rule: no trigger may key on `updated_at` as an event signal, on
any table.

> **Two lines to land:**
> *"`updated_at` tells you a row changed. It doesn't tell you what happened, or when."*
> *"Synthetic tests passed. Replaying real data didn't."*

---

## 7. Live Money Paths — referral credits & QR cashback

**Problem.** Reward programmes on real money must never pay twice or pay early.

**What I built.** A referral engine (buyer webview with app-injected auth; reward released
only on the referred buyer's **first delivered** order) and carton-QR cashback.

**Why this design.** Double credit is blocked by a **partial unique index on the wallet
ledger** — a database constraint, not application logic. Application logic has races; a unique
index does not.

**What failed.** The WhatsApp queue could offer a message claiming *"order delivered, ₹50
credited"* based on a derived status flag — which also included dry-run and manual credits
with no real delivery.

**What I changed.** Claims are verified against the **source of truth** — the actual delivery
timestamp and the real wallet transaction id — not a derived flag. Fails closed when the
source is unreachable, and the block is enforced in both the UI and the send API.

**Result.** 407 buyers referred, ₹48.1K paid out, 155 orders (₹1.03L) across both cohorts.

**Differently.** I'd have written the "what must be true for this sentence to be sendable"
list before writing the message copy.

> **The line to land:** *"Distrust any field that's a side effect of another process rather
> than the fact itself. A zeroed balance isn't proof of payment."*

---

## 8. Side projects (brief)

**Aditya MCP** — read-only MCP over session transcripts, git history and handoff docs; drives
a daily work report and stale-doc nudges. Point: I instrument my own process the way I
instrument production.

**Serverless Multimodal Call QA** — AWS Lambda feeds raw call audio to Gemini 2.5 Pro with
campaign-specific objective questions, strict JSON into Postgres/Metabase. Went from sampling
a handful of calls by hand to 100% coverage with consistent, auditable labels.

---
