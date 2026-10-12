---
title: "AI Product Matcher & Price Intelligence"
slug: "site-product-matcher"
kind: "portfolio"
site_slug: "product-matcher"
page_url: "https://adityamukhopadhyay.vercel.app/#work"
source: "site/projects.ts"
themes: ["Retrieval & matching", "Safety & cost"]
---
# AI Product Matcher & Price Intelligence

Mapping 170,000+ external SKUs from Amazon, ApnaKlub and Hyperpure onto the internal catalogue with a cost-tiered funnel.

Period: 2025 · Badho. Stack: Typesense, PostgreSQL (pg_trgm), LLMs, n8n, Hasura, React.

## Headline numbers

- **170,000+** — external SKUs matched

## Detail

Exact match → trigram candidates → a batched LLM only for genuine ambiguity (100 g versus 200 g), so token spend is proportional to difficulty rather than volume. Extended into a brand-scoped price-gap dashboard comparing internal against competitor pricing.

