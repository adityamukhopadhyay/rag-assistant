---
title: "About Aditya Mukhopadhyay"
slug: "about"
kind: "profile"
page_url: "https://adityamukhopadhyay.vercel.app/"
source: "site/profile.ts"
---
# About Aditya Mukhopadhyay

**AI Engineer at Badho Technologies** (https://badho.in)

I build production multi-agent systems and the MCP infrastructure they run on — with a working obsession for agent safety, honest evaluation and LLM cost engineering.

I'm an AI Engineer at Badho, a B2B distribution platform in India. My work is the unglamorous half of AI: agents that run unattended for a full working day, MCP servers that real products call, WhatsApp agents that talk to thousands of retailers — and the guards, ledgers and kill switches that keep all of it honest.

Everything here ran in production. Every number was measured, and each one says how. Where a figure is flattering but not causal, I say so.

## What differentiates the work

### Agent fleets that run unattended in production

~20 concurrent Claude Agent SDK sessions, one per rider per day, talking to real riders over WhatsApp for a 13-hour shift. Not a demo.
(See: https://adityamukhopadhyay.vercel.app/work/delivery-fleet)

### I build MCP servers, not just consume them

A 100-tool buyer-app MCP with real auth (phone-OTP OAuth → per-buyer JWT), a bearer-gated remote MCP over a courier's ops API, and a personal agent-ops MCP.
(See: https://adityamukhopadhyay.vercel.app/work/buyer-mcp)

### Deterministic where it can be, the model where it must be

Routine rider nudges run as deterministic templates filled from the live snapshot and re-checked at send time; the LLM is kept for judgement, escalation and real replies. The same rule/LLM split that makes the fleet reliable is what keeps it cheap to run at scale.
(See: https://adityamukhopadhyay.vercel.app/work/delivery-fleet)

### Agents must not be able to lie

Structural guards below the model — recipient guards, invented-number blocking, ticket gates, a reply agent that can't see tool narration — not prompt-level pleading.
(See: https://adityamukhopadhyay.vercel.app/work/whatsapp-sales-agent)

### Live money paths

Referral credits and cashback with DB-level double-credit prevention. Real rupees, adversarially audited against production.
(See: https://adityamukhopadhyay.vercel.app/work/live-money-paths)

## Skills

- **Core:** Python, TypeScript, SQL, FastAPI, PostgreSQL, Supabase, Docker, AWS (EC2, Lambda, S3), Railway, Vercel, Next.js
- **AI:** Claude Agent SDK, Model Context Protocol (MCP), Claude / GPT / Gemini APIs, LangGraph, FAISS, embeddings & RAG, prompt caching & cost optimization, agent guardrails & evals, n8n

## Experience

### AI Engineer — Badho Technologies Pvt. Ltd. (Jun 2025 – Present)

- Built a delivery fleet where a root orchestrator agent runs each rider's day (~20 concurrent) and delegates to sub-agents — empath, driver-profile analyst, escalation governor, judgement tiebreaker, Google Maps route planner — over one in-process MCP server with WhatsApp, push, Freshdesk tickets and vision on rider photos.
- Authored an MCP server exposing the buyer app as 100 typed tools behind phone-OTP OAuth and per-buyer JWTs, and shipped a live WhatsApp sales agent on it that searches the catalogue, builds carts, applies coupons, sends deeplinks and raises tickets — with deterministic honesty gates.
- Guards below the model — recipient guard, invented-number blocking, watchdog, healthcheck — pinned by 23 offline test suites; routine nudges run as deterministic templates so the model is used only for judgement.
- An autopilot over the courier partner's API that auto-files weight claims with vision over sorter images and raises NDR/lost/damaged tickets — 698 claims and 370 tickets filed in 24 hours, 2,143 closed to date.
- Sub-100 ms hybrid search (FAISS + PostgreSQL metaphone), sister-product clustering across 85,000+ SKUs, and 170,000+ external SKUs matched through an n8n funnel ending in an LLM decision.
- Event-driven order-lifecycle notifications (10 stages, ~500 messages a day) and live money paths — a referral engine (407 buyers referred, INR 48.1K paid out, 155 orders across both cohorts) and QR cashback with DB-level double-credit prevention.

### AI Developer (Freelance) — Strix Digital (Jul 2023 – May 2025)

- Built AI web-apps (a custom cold-email generator on Groq), automation tooling and scrapers; shipped an iOS app for a Houston client.

### Data Science Intern — Acmegrade (in collaboration with IIT Bombay) (Apr 2022 – Jun 2022)

- ML models for movie recommendation, sales forecasting and CNN sound classification; EDA and feature engineering on multi-modal data.

## Links

- linkedin: https://www.linkedin.com/in/adityamukhopadhyay2003/
- github: https://github.com/adityamukhopadhyay/
- projectDocs: https://drive.google.com/drive/folders/1zYhjtbmRBKxq09_61hzhWWnQZ2N1uAtj?usp=sharing

