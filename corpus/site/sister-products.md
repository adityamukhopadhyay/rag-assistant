---
title: "Sister Products Clustering"
slug: "site-sister-products"
kind: "portfolio"
site_slug: "sister-products"
page_url: "https://adityamukhopadhyay.vercel.app/#work"
source: "site/projects.ts"
themes: ["Retrieval & matching"]
---
# Sister Products Clustering

Grouping same-brand, different-size products across 85,000+ SKUs with an algorithm that switches itself by brand size.

Period: 2025 · Badho. Stack: Python, FastAPI, scikit-learn, HDBSCAN, K-Means, all-MiniLM-L6-v2, Docker, Nginx.

## Headline numbers

- **85,000+** — SKUs clustered
- **40% → 60%** — sister-product conversion

## Detail

HDBSCAN finds density blobs on small and medium brands; above ~1,000 SKUs it switches to K-Means to hold sub-second latency. Similarity is a hybrid of semantic (Euclidean over MiniLM embeddings) and string (Levenshtein) distance. Impact: the sister-product modal opened 5× more often and conversion through it rose from 40% to 60%.

