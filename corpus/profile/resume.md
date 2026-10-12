---
title: "Aditya Mukhopadhyay — Resume"
slug: "resume"
kind: "profile"
page_url: "https://adityamukhopadhyay.vercel.app/resume"
source: "resume_copy.py"
---
# Aditya Mukhopadhyay — Resume

**AI Engineer — LLM Agents, MCP, RAG & Production Machine Learning**

Location: Jabalpur, India · open to relocation / remote

## Summary

AI Engineer who ships production LLM agent systems end to end — multi-agent orchestration on the Claude Agent SDK, MCP tool servers, RAG and classical ML — in Python, TypeScript and PostgreSQL, with guardrails and evaluation built in.

## Skills

- **Languages & Backend:** Python · TypeScript · SQL · FastAPI · GraphQL (Hasura) · PostgreSQL (JSONB, pgvector, pg_trgm) · Supabase · Docker · AWS (Lambda, EC2, S3) · Railway · Vercel · Git · CI/CD
- **AI / ML:** Machine Learning · LLM agents · Claude Agent SDK · Model Context Protocol (MCP) · multi-agent orchestration · tool calling · RAG · embeddings (FAISS, MiniLM, nomic-embed) · semantic search · clustering (HDBSCAN, K-Means) · entity resolution · prompt engineering · structured outputs · evaluation & guardrails · cost tracing · Claude / GPT / Gemini APIs · n8n
- **Leadership:** Managed a 3-person AI team · worked directly with stakeholders · client-facing delivery

## Experience

### AI Engineer — Badho Technologies Pvt. Ltd. (Jun 2025 – Present)

#### Autonomous Delivery Fleet — multi-agent orchestration (Claude Agent SDK, MCP, Python)
- Tackled a blind spot where delivery failures surfaced only when a human noticed a stuck rider.
- Architected a **per-rider orchestrator agent (~20 concurrent)** delegating to messaging, escalation, judgement and route-planning sub-agents over one in-process MCP server, with **deterministic guards below the model**.
- Enabled **unattended 13-hour shifts**, backed by **23 offline test suites** and an "Ask the fleet" agent for operators.

#### Buyer MCP — the buyer app as 100 typed agent tools (TypeScript, MCP, Hasura GraphQL, OAuth/JWT)
- Solved the absence of any safe, permissioned way for agents to act inside the buyer application.
- Developed an MCP server exposing search, carts, coupons, orders, wallet and tickets as **100 typed tools** behind phone-OTP OAuth and **per-buyer JWTs**, reusing the app's own pricing logic so **quotes never diverge**.
- Powers the **production sales agent**, Claude Desktop and Claude Code, with the tool schema as the permission boundary.

#### WhatsApp AI Sales Agent (Claude Agent SDK, Buyer MCP, Python, asyncio)
- Addressed retailers asking questions and abandoning carts faster than a sales team could respond.
- Designed a two-model architecture — a tool-using worker reasons, a **tool-less reply agent is the only voice** — with a **claim verifier**, per-buyer queues, a bounded concurrency gate and a warm session pool.
- Handles buyer conversations end to end in production and influenced **475 orders (INR 5.0 lakh)**, with gates that block any false order or ticket claim.

#### Courier Ops Autopilot — claims & ticket automation (FastAPI, remote MCP, Claude Haiku, vision)
- Recovered money left unclaimed because weight-overcharge and failed-delivery filing with the courier was manual.
- Created a backend, dashboard and bearer-gated remote MCP over the courier API that **auto-files weight claims from sorter images**, raises NDR / lost / damaged tickets and drafts vendor replies, guarded by a **single liveness gate**.
- Filed **698 claims and 370 tickets in the first 24 hours**; **2,143 closed** to date.

#### Search, Matching & Catalog Intelligence — ML pipeline (FAISS, HDBSCAN, embeddings, PostgreSQL, n8n)
- Targeted Hinglish and phonetic search misses, 85,000+ SKUs with no variant grouping, and 170,000+ competitor SKUs needing catalogue mapping.
- **Led a 3-person team** to deliver **sub-100 ms hybrid search** (FAISS + local embeddings + metaphone), sister-product clustering (MiniLM, HDBSCAN / K-Means, shadow-write staging with human approval) and a cost-tiered matching funnel (exact → trigram → batched LLM).
- Mapped **~40,000 product groups**, lifted sister-product conversion from **20% to 60%**, and matched **170,000+ SKUs**.

### AI Developer (Freelance) — Strix Digital (Jul 2023 – May 2025)
- Delivered AI web apps (a **cold-email generator on Groq**), scrapers, automation tooling and an **iOS app** for a Houston client, client-facing from scoping to hand-off.

### Data Science Intern — Acmegrade (in collaboration with IIT Bombay) (Apr 2022 – Jun 2022)
- Built ML models for **movie recommendation**, **sales forecasting** and **CNN sound classification**, with EDA and feature engineering on multi-modal datasets.

## Education

- **B.Tech, Information Technology** — IGEC Sagar (RGPV), Madhya Pradesh · 2021 – 2025 · CGPA 7.5
- **Class XII (PCM)** — St. Joseph's Convent S.S. School, Ranjhi, Jabalpur · 2021 · 93.4%

## Side projects

- **Aditya MCP — agent-ops infrastructure** (2026) — Built a read-only MCP server over AI-session transcripts, git history and handoff docs; drives a daily work report.
- **Serverless Multimodal Call QA** (2025) — Wired AWS Lambda to send call audio to Gemini 2.5 Pro with campaign questions; strict JSON to PostgreSQL/Metabase. 100% coverage.

## Contact

- Email: adul.m.2003@gmail.com
- Phone: +91-9981861975
- Portfolio: https://adityamukhopadhyay.vercel.app
- LinkedIn: https://www.linkedin.com/in/adityamukhopadhyay2003/
- GitHub: https://github.com/adityamukhopadhyay/
