---
title: "Live money paths — referral credits & QR cashback"
slug: "site-live-money-paths"
kind: "portfolio"
site_slug: "live-money-paths"
page_url: "https://adityamukhopadhyay.vercel.app/work/live-money-paths"
source: "site/projects.ts"
themes: ["Money paths", "Safety & cost", "Pipelines"]
---
# Live money paths — referral credits & QR cashback

Two real-rupee systems run end to end: a multi-leg refer-and-earn with 361 of 361 bonuses credited, and carton-QR cashback where double credit is physically impossible.

Period: 2026 · Badho. Stack: Next.js, Supabase, Python poller, Hasura, PostgreSQL, AiSensy, GA4, Vercel, Railway.

## Headline numbers

- **361 / 361** — bonuses credited, zero misses
- **₹42,030** — paid out across three legs
- **1** — unique index is the whole guarantee

## Context

**Refer-and-earn:** an existing buyer shares a code, a new buyer enters it at signup, and wallet cash goes to both — ₹100 to the referred buyer at signup, ₹50 to the referrer on the referred buyer's **first delivered order**, never on signup alone. A Next.js buyer webview with app-injected auth (one link serves every buyer), a Supabase credit service, a poller that releases rewards on delivery, and WhatsApp status updates.

**Package scratch:** every carton carries the same QR. Scan it in the app, scratch a card, and get 5% of the delivered order value back, capped at ₹100. Designed so that a QR on a discarded box is worth nothing to anyone.

## How it works

### The QR is not a bearer token

The code is constant across every package and carries **no order, no buyer, no secret**. Identity comes from the app, which substitutes the logged-in buyer's token on open. If buyer B scans buyer A's carton, the page opens as B, looks up B's own delivered orders, and pays B only what B is owed — or shows "no reward yet". The cross-buyer theft case isn't defended against; it is designed out.

### No double credit — structural, not best-effort

One partial unique index on the wallet ledger is the entire guarantee. The claim **writes first and lets Postgres arbitrate** — a second insert is physically unstorable and comes back as `ALREADY_CLAIMED`. There is no check-then-write window because there is no gap. It holds under double-tap, two devices, a retried serverless call, a redeploy mid-flight, replica lag, and a different buyer entirely — the key is the order alone, deliberately. The wallet table *is* the claim ledger; there is no second source of truth on a money path.

### Identity proven upstream, no secret to leak

The buyer ID is read only from signed token claims, never from a URL or body parameter, and then proven by calling the platform *as that buyer*. A forged or expired token is rejected there and never reaches the credit path. The service holds no signing secret. Every gate re-runs at payment time, not just at preview, and already-claimed is read from the primary, not the lagging replica.

### Adversarial audit against live production

Probed the deployed money path directly. No identity → `MISSING_TOKEN`. Forged buyer ID in body *and* query → ignored, `AUTH_FAILED`. Nominated order and `amount: 99999` → both ignored. **Valid-shaped JWT with a real buyer ID and a fake signature → `REJECTED_UPSTREAM`.** Dev-mode probe as a non-dev → nothing returned. Every attempt failed closed; the client cannot choose anything, and a tampered amount is not just rejected — it is never consulted.

### Referrals: pay on delivery, backfill on failure

The credit poller reads pending referrals every 180 seconds, finds the referred buyer's first delivered order on the read replica, credits through the platform, and flips the row. It also backfills the referred buyer's signup bonus if that credit ever failed. Both legs are idempotent through a partial unique index of their own. A ₹10 referrer-signup leg was added later, modularly, and proven live on real money.

## Measured results

- **361 / 361** — signup bonuses paid (Every referred buyer got ₹100; zero missed credits across 361 referrals from 254 referrers. Live figures, 2026-08-19.)
- **₹42,030** — paid out across all three legs (₹36,100 to referred buyers, ₹5,930 to referrers (₹50 delivery + ₹10 signup legs).)
- **5 / 5** — attack paths failed closed (Adversarial audit against the live scratch endpoint; see the table in the mechanism above.)
- **5% · cap ₹100** — scratch reward rule (`min`, not `max`, of 5% of delivered order value and ₹100 — confirmed against the live config, one scratch per delivered order.)
- **1** — partial unique index (`WHERE comment = 'Package scratch reward'` — the predicate is mandatory because 96,663 orders already carry more than one wallet row. Verified valid on production before go-live.)

## What the numbers do and do not claim

The 100%-paid figure is the one that matters engineering-wise: a money path with zero missed credits. Conversion and activation are product metrics and I leave them to the product dashboard.

## Lessons

- Fail closed on money. Guarantees belong at the database, never in app logic.
- Don't defend against the attack — design it out.
- A retry that can never double-pay is a retry you can offer the user.

