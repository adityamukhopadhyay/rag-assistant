---
title: "WhatsApp AI Sales Agent"
slug: "site-whatsapp-sales-agent"
kind: "portfolio"
site_slug: "whatsapp-sales-agent"
page_url: "https://adityamukhopadhyay.vercel.app/work/whatsapp-sales-agent"
source: "site/projects.ts"
themes: ["Conversational AI", "Agents", "MCP", "Safety & cost"]
---
# WhatsApp AI Sales Agent

A live, tool-using sales agent for retailers that is architecturally unable to claim an order it didn't place — and whose analytics deliberately report worse numbers than they could.

Period: 2026 · Badho · live since Jul 2026. Stack: Python, Claude Agent SDK, Buyer MCP, AiSensy, Supabase, Railway.

## Headline numbers

- **INR 5.0L** — potential value · 475 orders
- **₹11,690** — causal, exact cart-ID match
- **$152.50** — total LLM spend

## Context

Retailers message a WhatsApp number; a Claude agent answers in Hinglish, looks up live prices and offers through the Buyer MCP, builds a cart, sends a deeplink, and files support tickets when something has gone wrong with an order. It is live for every registered buyer.

Two things make it different from a chatbot demo: it is **structurally prevented from lying** about money and orders, and its dashboard reconciles **exactly** against the production replica — including the uncomfortable finding that most of the revenue it looked responsible for wasn't.

## How it works

### Two agents, one voice

The tool-using worker reasons; its text is only a draft. A separate **tool-less reply agent** rewrites the final message from that draft plus a FACTS bundle — payable amount, cart link, ticket number — captured from tool results, never from prose. It structurally cannot emit "waiting for my tools to connect", and it enforces `aap`, gender-aware address, and `__NO_REPLY__` when a chat is genuinely concluded. On its own failure it fails open to the guarded worker draft.

### Honesty gates that fire even under bypass

`place_order` is blocked for this consumer, so "your order has been placed" is always false — and therefore never said. Cancellations are answered from live order state; seller rejections are owned with the refund surfaced. Ticket creation passes three deterministic PreToolUse gates: **callback-only is always denied** (the buyer gets the support line instead), **you must have looked** at existing tickets first (a recorder hook witnesses it), and **no duplicate within 12 hours**. These fire even when the agent runs with permissions bypassed.

### Reporting worse numbers on purpose

Naive attribution credited every order by any buyer who had ever engaged. I measured it: **75% of those orders predated the buyer's first contact** (118 of 157; 64% on the subset where first contact is certain). So the headline tile became "ordered from our cart" — an exact `cartId` match on the order, the only causal claim the system can defend — and the other tiles stayed, labelled as correlation. RTO was carved out of Rejected because they were double-counting.

### The silent-truncation family

Supabase caps every select at 1,000 rows with no signal; `.limit(50000)` returns 1,000. **37% of engaged buyers were invisible to attribution.** `list_orders` capped at 10, so the best repeat buyers were truncated. Six background sweeps had died after one run because nothing held a reference and the GC took them mid-sleep — frequent redeploys had masked it. The cost ledger itself was being pruned at seven days, which made "all-time spend" structurally impossible. Fixed all four and broadcast the class of bug across every project.

### Taking the automation tool out of the hot path

Replies were arriving hours late, then not at all: the provider's webhooks went through an automation tool whose 15,000-deep FIFO queue had stalled. AiSensy now posts directly; the endpoint acknowledges in ~1 ms, ingests in the background with a held reference, and dedups at ingest so the cutover couldn't double-process.

### Model tiering and true cost

Haiku for greetings, Sonnet for reasoning, and the reply agent rides the same tier as the worker. Every raw SDK call is priced from token usage — cache reads and writes included — so the dashboard's "LLM cost" is the real one, and it reconciles exactly to the console.

## Measured results

- **₹5,00,817** — full potential value · 475 orders (Every order by a bot-engaged buyer. Correlation, not causation — see the 75% figure. Kept on the dashboard, labelled as such.)
- **₹11,690** — ordered from a cart the agent built · 14 orders (Exact cart-ID match on the order. The only number here I would call *caused* by the agent; ₹1,263 of it delivered at the time of measurement.)
- **$152.50** — total LLM spend, whole programme (Reconciled exactly to the Anthropic console: buyers $81.60, pre-ledger $70.90, test/dev $0.00. About three weeks of early traces were lost to a retention bug, so the ledger was rebuilt from the console.)
- **75%** — of naively-credited orders predated first contact (118 of 157 orders on Aug 4; 64% on the gold-standard subset. This is why the headline tile changed.)
- **37%** — of engaged buyers were invisible to attribution (157 of 429, hidden by the 1,000-row cap. Fixing it added 41 orders to the counts immediately.)
- **~1 ms** — webhook acknowledgement (Down from hours through the stalled queue. Verified end-to-end with a raw provider payload: 200 in 0.5 s, one inbound, one two-bubble reply, the duplicate deduped.)

## What the numbers do and do not claim

"INR 5.0L across 475 orders" is the pipeline's full potential value, not revenue caused by the agent. The defensible causal number is ₹11,690 across 14 orders. I show both because the gap between them is the most useful thing the dashboard says.

## Lessons

- The metric you report should be the one you'd defend under cross-examination.
- Every paginated API truncates by default until proven otherwise.
- If the agent can't do it, it can't claim it — make the claim impossible, not discouraged.

