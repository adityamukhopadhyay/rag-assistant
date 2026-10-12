---
title: "Catalog Metadata Standardization"
slug: "site-catalog-metadata"
kind: "portfolio"
site_slug: "catalog-metadata"
page_url: "https://adityamukhopadhyay.vercel.app/#work"
source: "site/projects.ts"
themes: ["Pipelines"]
---
# Catalog Metadata Standardization

Turning unstructured product descriptions into filterable facets, without letting the model invent new keys.

Period: 2025 · Badho. Stack: n8n, Gemma 12B, OpenAI Batch API, PostgreSQL.

## Headline numbers

- **25,000+ → ~5,000** — legacy keys → canonical keys

## Detail

A two-step, schema-first flow: generate a strict category schema, then inject it as context so the extraction model cannot hallucinate new keys. Normalised 25,000+ fragmented legacy keys into about 5,000 canonical ones.

