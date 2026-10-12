---
title: "Buyer MCP — the app as 100 agent tools"
slug: "site-buyer-mcp"
kind: "portfolio"
site_slug: "buyer-mcp"
page_url: "https://adityamukhopadhyay.vercel.app/work/buyer-mcp"
source: "site/projects.ts"
themes: ["MCP", "Agents", "Safety & cost"]
---
# Buyer MCP — the app as 100 agent tools

A Model Context Protocol server that exposes the whole buyer marketplace as typed tools, with real OAuth and exact app parity — consumed by production agents, Claude Desktop and Claude Code.

Period: 2026 · Badho. Stack: TypeScript, MCP SDK, Hasura GraphQL, REST, OAuth 2.0 / JWT, Railway.

## Headline numbers

- **100** — typed tools
- **1** — buyer per session, row-scoped
- **0** — genuine failures in the tool sweep

## Context

I build MCP servers, not just consume them. This one mirrors what a buyer can do in the Badho app — catalogue, sellers, cart, coupons, orders, support tickets, addresses, payouts, wallet, referrals, even the home-screen layout — by replaying the app's **exact** GraphQL and REST calls, scoped to one authenticated buyer per session. "Nothing more, nothing less" is enforced by the platform's buyer role and the buyer's own JWT.

It is the substrate the WhatsApp sales agent stands on, and it connects to Claude Desktop through OAuth where the login screen is the buyer's real login: phone number, OTP.

## How it works

### Auth that is real, not a shadow identity

OAuth 2.0 with dynamic client registration and PKCE, where the **authorize step is phone + OTP** against the production auth service, and the access token the client receives *is* the buyer's app JWT. Programmatic consumers (the WhatsApp agent) mint a per-buyer JWT server-side; the secret that allows it never leaves the auth layer. Every tool then runs as exactly one buyer, and the data layer's row scoping does the rest.

### Parity by import, not by test

The cart, coupon and deeplink maths are the app's own pure functions imported verbatim, so the agent and the app cannot disagree on a price. When the app's GraphQL operations drifted from live Hasura, thin local overrides were added for just those operations rather than forking the whole layer.

### The cart that vanished

Adding an item worked; opening the cart emptied it. The app's own validation archives any cart whose SKUs aren't orderable from that seller, and the tool had been sourcing SKUs from the global catalogue. Fix: source from the seller-scoped catalogue and price exactly as the app does — MRP × (1 − margin) with the slab picked by quantity. Proven end-to-end: `archivedCart=false, removedItems=[], priceUpdates=[]`.

### Honest absence

Upstream coupon gates fail open and are non-deterministic. A tool that returned an empty list would push the agent into saying "this brand has no offers" — which is frequently false. So coupon lookups return the SKUs *without* coupons and a caveat explaining why, and the agent is forbidden from claiming absence. A tool that can't say "I don't know why" will be forced to lie.

### The ₹0-discount bug and the staleness channel

A relative-path import silently kept a stale copy of the coupon engine, so the MCP quoted ₹0 on every uncapped coupon while the app charged full price. It was caught by a **cross-surface check** — quote the same cart through the MCP and through the app, compare the totals exactly — before any buyer saw it. Documented as a permanent rule: every shared module needs a staleness channel, or parity is an assumption.

### A finding reported upstream

While building the voucher tools I found an authorization gap in a platform role. It wasn't mine to fix and it wasn't mine to work around; it was reported with a reproduction to the team that owns it.

## Measured results

- **100** — tools, each typed and row-scoped (Grew 87 → 93 → 100 across the summer as batches landed: support forms, addresses, payouts, rewards, orders, notifications, referrals, folds, media.)
- **180 days** — refresh-token lifetime (Per-buyer JWT with long refresh, so a Claude Desktop connection survives without re-login; the OTP screen is the only credential a buyer ever types.)
- **48 / 48** — read tools OK in the live sweep (A full sweep of the read tools against live Hasura: 48 OK, 0 genuine failures, 1 new bug found and fixed.)
- **₹0** — the quote the stale import produced (On every uncapped coupon, while the app charged full price. Caught by the cross-surface check, never seen by a buyer.)

## What the numbers do and do not claim

Business-impact numbers for the MCP itself are not measured yet — its usage flows through the WhatsApp agent's analytics, and attributing revenue to infrastructure would be inference. I'd rather say "not yet measured" than invent a number.

## Lessons

- A tool that can't say "I don't know why" will be forced to lie.
- Parity is a property you import, not a test you write.
- Every shared module needs a staleness channel.

