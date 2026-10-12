---
title: "Order-Lifecycle WhatsApp Automation"
slug: "site-order-lifecycle-automation"
kind: "portfolio"
site_slug: "order-lifecycle-automation"
page_url: "https://adityamukhopadhyay.vercel.app/work/order-lifecycle-automation"
source: "site/projects.ts"
themes: ["Pipelines", "Safety & cost", "Conversational AI"]
---
# Order-Lifecycle WhatsApp Automation

Event-driven order notifications to the entire buyer base — ten stages, ~500 messages a day, zero errors across eight consecutive days — with its guard architecture built from a real incident.

Period: 2026 · Badho · live since Jul 2026. Stack: Python, asyncpg, PostgreSQL (read replica), Supabase, AiSensy, Railway.

## Headline numbers

- **10** — order stages
- **~500** — messages / day
- **0** — errors over 8 days

## Context

Every buyer gets told when their order is confirmed, dispatched, out for delivery, delivered, returned, cancelled or partially delivered — in Hindi, with a deeplink, from Meta-approved templates. Four pollers read the order and courier-shipment tables on the read replica; a ledger makes every (order, stage) pair idempotent; an admin dashboard shows every send and has a stop switch.

The interesting part is not the happy path. It is what the system learned from the night it sent 469 wrong messages in fifteen minutes.

## How it works

### The incident

An external weight-recomputation job stamped **15,018 order rows with one identical `updated_at`**. The main tick keyed its fetch on that column, saw "fresh" COMPLETED rows, mapped them to `delivered`, found nothing in the ledger (they pre-dated go-live), and sent **469 stale "your order has been delivered"** messages for orders up to two years old — most as "your first order", because the old order usually was. A second, earlier wave had leaked 28 more. Forensics in the audit table proved the trigger was a backend backfill — `updatedColumns = {updated_at, totalWeightInGram}` — not any order activity.

### The standing rule: `updated_at` is not an event

Bulk touches turned out to be routine — six waves over 2,000 rows in fourteen days. So: **no trigger may key on `updated_at` as an event signal, on any table.** Scanning on it is fine (it's the only indexed change signal); every staged message must pass an event-time check — `markedDeliveredTime`, `created_at`, `archiveTime` — or the bulk-cluster guard. Replaying the incident window with the clock frozen: the guard blocked 2,140 stale rows and passed 64 genuine ones.

### A guard for the tick that has no event column

The courier tick can't gate on an event time — the only candidate is missing on ~20% of legitimate rows. Its defence is the bulk job's own signature: **any same-timestamp cluster larger than 50 rows is dropped whole**. The largest natural cluster measured was 9; the bulk waves were 2,600–15,000. Both guards fired in production within minutes of deploy — the cluster guard on a real 276-row reconciliation touch nobody had predicted.

### Deleting a mapping instead of patching it

`COMPLETED → delivered` was removed outright once measured that 100% of marketplace deliveries (1,158 of 1,158 in fourteen days) have a courier row; the main tick's only "delivered" output in a week had been 28 stale leaks. The whole stale-delivered attack surface went with it. An earlier version of this change had asked the wrong question of the data and would have silently killed delivery messages for half of all orders — an audit caught it.

### Scope gates that match on flags, never names

Other order flows share the same tables and must never get these messages. Every fetcher joins on the seller's D2R flag. One brand had **seven seller rows with the flag true on exactly one**; a name filter would have silenced a top seller. Verified zero non-D2R sellers across all five fetchers over fourteen days before deploy, at a cost of zero real messages.

### Fail loud at boot, never infer a refund

Three of twelve templates had once been silently dead in production, hidden for hours behind a per-order log line. Now the stage vocabulary is checked against the database constraint at startup and logs loudly on mismatch. And a message that promises a refund is gated on the actual refundable-amount column — a claim-bearing message is never derived from a status.

## Measured results

- **10** — stages wired (Confirmed, dispatched, out-for-delivery, delivered, first-delivered, partial, RTO in transit, RTO delivered, cancelled, and a driver-onboarding flow added later.)
- **~500** — messages per day (All buyers, D2R orders only. Expected volume re-measured when the cadence changed.)
- **0** — errors across 8 consecutive days (Audited against the send ledger and the provider's responses; zero poller failures in the same window.)
- **497** — stale messages — the incident I own (469 in the main wave plus 28 from an earlier one. The rows stay in the ledger as history; deleting them was asked for and declined.)
- **2,140** — stale rows blocked in the replay (Incident fetch window re-run with "now" frozen at 20:41 UTC; 64 genuine sends passed.)
- **276** — rows in the cluster guard's first real catch (A reconciliation job on shipments, twelve mixed statuses, within minutes of deploy. Genuine sends continued in the same tick.)

## What the numbers do and do not claim

The zero-error figure is real and so is the 497. A notification system that has never sent a wrong message has not been running long enough; what matters is whether the class of failure can recur. Here it cannot, by construction, and the proof is a replay, not a promise.

## Lessons

- `updated_at` is not an event.
- When a mapping exists only to cover a case you can measure is empty, delete the mapping.
- Match on the flag, never on the name.

