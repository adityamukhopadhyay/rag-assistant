---
title: "Serverless Multimodal Call QA"
slug: "site-call-qa"
kind: "portfolio"
site_slug: "call-qa"
page_url: "https://adityamukhopadhyay.vercel.app/#work"
source: "site/projects.ts"
themes: ["Pipelines"]
---
# Serverless Multimodal Call QA

Automated auditing of every recorded sales call, replacing a manual QA sample with 100% coverage.

Period: 2025 · Badho. Stack: AWS Lambda, Node.js, Gemini 2.5 Pro, API Gateway, PostgreSQL, Metabase.

## Headline numbers

- **100%** — call coverage

## Detail

Audio is fed directly to the model alongside campaign-specific questions — was the combo pitched? what was the tone? — returning structured JSON verdicts into Postgres and Metabase. No transcription step, no sampling.

