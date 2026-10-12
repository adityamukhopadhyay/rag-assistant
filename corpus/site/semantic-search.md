---
title: "Semantic Search Engine"
slug: "site-semantic-search"
kind: "portfolio"
site_slug: "semantic-search"
page_url: "https://adityamukhopadhyay.vercel.app/#work"
source: "site/projects.ts"
themes: ["Retrieval & matching"]
---
# Semantic Search Engine

Sub-100 ms product search combining semantic, phonetic and exact matching for Indian-English spelling variation.

Period: 2025 · Badho. Stack: Python, Flask, FAISS, Ollama, PostgreSQL, Docker, EC2.

## Headline numbers

- **<100 ms** — query latency

## Detail

An in-memory FAISS index with query embeddings computed on the fly by a local Ollama container (`nomic-embed-text`), fused with Postgres full-text search and `dmetaphone` so that "parle", "parley" and "paarle" land on the same product. Multi-container Docker on EC2.

