---
title: "Delhivery Ops Autopilot"
slug: "site-delhivery-ops-autopilot"
kind: "portfolio"
site_slug: "delhivery-ops-autopilot"
page_url: "https://adityamukhopadhyay.vercel.app/work/delhivery-ops-autopilot"
source: "site/projects.ts"
themes: ["Agents", "MCP", "Safety & cost", "Money paths"]
---
# Delhivery Ops Autopilot

An agent that files real weight claims and tickets against our courier partner's API with no human in the loop — and a single kill switch that stops all of it, and all AI spend, the moment the vendor session dies.

Period: 2026 · Badho. Stack: Python, FastAPI, MCP, Claude Haiku 4.5, Supabase, Railway, Vercel, Next.js.

## Headline numbers

- **698 + 370** — claims + tickets filed in 24 h
- **2,143** — tickets closed to date
- **1** — predicate gates the money

## Context

Couriers overcharge on weight, lose parcels, and leave shipments stuck. Recovering that money used to mean a person filing claims one at a time in a vendor portal. This is a standalone ops product — dashboard, backend, and a bearer-gated remote MCP — that does it autonomously: detects weight discrepancies and files overcharge claims (with **vision over the vendor's own exception photos**), raises NDR / lost / damaged / RTO tickets, chases stuck and overdue shipments, dedups against every open ticket before filing, and drafts replies to vendor responses.

It is the clearest case in my work of an agent taking real, irreversible actions against an external system. The guardrails exist because the failure modes are filing junk claims at a vendor, or burning spend against a dependency that has quietly died.

## How it works

### Session-liveness kill switch

`TokenManager.live()` is one predicate on all eight background loops *and* every AI entry point. It is true only while the refresh chain is genuinely usable: token expiry in the future **and** no `_dead` latch. The latch matters because **a revoked token can still look unexpired by its own clock** — it trips the moment the auth server answers `invalid_grant`, and clears when a fresh token is pasted in the dashboard. No redeploy. It fails *open* on a non-JWT refresh token so a healthy session is never falsely paused.

### Before the fix, 'ready' meant a file existed

The readiness check had returned true for any token file that merely existed. With a months-dead session the loops were hitting the vendor's auth server roughly every 2.8 minutes forever — **76 `invalid_grant` responses in 3.5 hours of logs** — free, but pointless traffic against someone else's infrastructure. After: zero in four hours. The AI paths had been safe only by accident, because each happened to hit the vendor first and die there.

### Fail fast in the client

Post-deploy logs showed the loops silent but an 11-call burst in 12 seconds from one MCP client, each call costing a round trip to die. Now every on-demand call — all 30 MCP tools, every dashboard read — short-circuits on a dead session with "paste a fresh token" and **zero network traffic**. It still can't die silently: a one-shot Slack alarm fires on the live→dead transition, then everything goes quiet by design.

### A judge without thresholds

The first triage queue was deterministic and produced nonsense like "0 days past promised — expedite". Version two lets Claude decide what's critical per stream with a forced tool call. Two tuning bugs worth keeping: ~19 concurrent calls rate-limited the weight stream to *empty* (fixed with a shared semaphore of five), and a "be thorough" prompt overran `max_tokens` and truncated to empty (fixed with batches of 25 and a bigger budget). Both failed silently until the run logs carried per-source errors.

### Writes that can't hammer the vendor

Bulk auto-filing is throttled with 429/503 backoff. Every real submission is recorded in a write ledger and surfaced with a deeplink to the vendor's record; dry-run previews the exact payload without firing. Before raising, the system re-queries the vendor per shipment and skips anything that already has an open ticket or claim, so stale flags never double-file. Writes for claim types whose payloads weren't yet captured live stay in preview until they are.

## Measured results

- **698 + 370** — weight claims + tickets auto-filed in 24 h (Snapshot 2026-08-12, plus 19 responses drafted and sent to vendor replies.)
- **2,143** — tickets closed to date (Cumulative at the same snapshot.)
- **₹41,480 / ₹12,736** — claims raised / recovered (Raised is not recovered; both shown. The wallet view tracks ₹13.8L on delivered against ₹8.8L of RTO loss.)
- **76 → 0** — pointless auth calls per 3.5 h (Keycloak `invalid_grant` responses from the loops before and after the liveness gate; verified in production logs.)
- **30** — MCP tools, bearer-gated (The same capability exposed to any Claude client, guarded by the same liveness predicate.)

## What the numbers do and do not claim

Claims raised and money recovered are different numbers and I show both. Throughput figures are a one-day snapshot, not a sustained rate — the session was deliberately left paused for a period while the guards above were built and verified.

## Lessons

- An agent that acts on an external system needs a way to stop that doesn't depend on the thing that broke.
- Expiry is not liveness.
- A deterministic threshold you can't justify is worse than a judgement you can audit.

