#!/usr/bin/env bash
# One-shot Railway provisioning for portfolio-rag using the Railway CLI with an ACCOUNT token, so the
# CLI's stored login (a different account on this machine) is never touched.
#
#   RAILWAY_API_TOKEN=<personal account token>  ./scripts/railway_setup.sh
#
# Creates project "portfolio-rag" with two services:
#   qdrant   — image qdrant/qdrant, volume at /qdrant/storage, API key
#   rag-api  — this repo (Dockerfile), public domain, non-secret variables
# It does NOT set GEMINI_API_KEY: paste that in the Railway dashboard → rag-api → Variables.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${RAILWAY_API_TOKEN:?set RAILWAY_API_TOKEN to a token from railway.com/account/tokens (personal account)}"
export RAILWAY_API_TOKEN

echo "== account =="; railway whoami

QDRANT_KEY="$(openssl rand -hex 24)"
ADMIN_TOKEN="$(openssl rand -hex 24)"

echo "== project =="
railway init --name portfolio-rag
railway environment production >/dev/null 2>&1 || true

echo "== qdrant service =="
railway add --image qdrant/qdrant:latest --service qdrant \
  --variables "QDRANT__SERVICE__API_KEY=${QDRANT_KEY}" \
  --variables "QDRANT__STORAGE__STORAGE_PATH=/qdrant/storage" \
  --variables "QDRANT__SERVICE__HOST=::"
railway volume add --mount /qdrant/storage --service qdrant

echo "== rag-api service =="
railway add --service rag-api \
  --variables "QDRANT_URL=http://qdrant.railway.internal:6333" \
  --variables "QDRANT_API_KEY=${QDRANT_KEY}" \
  --variables "ADMIN_TOKEN=${ADMIN_TOKEN}" \
  --variables "ACTIVE_PIPELINE=a" \
  --variables "QUERY_EXPANSION=false" \
  --variables "PUBLIC_DOCS=false" \
  --variables "CORS_ORIGINS=https://adityamukhopadhyay.vercel.app,http://localhost:3000" \
  --variables "RATE_LIMIT_PER_MIN=20" \
  --variables "RATE_LIMIT_PER_DAY=400"
railway service rag-api
railway up --service rag-api --detach
railway domain --service rag-api || true

cat <<EOF

== done ==
ADMIN_TOKEN (keep it; needed for /admin/ingest):  ${ADMIN_TOKEN}
Next:
  1. Railway dashboard → rag-api → Variables → add GEMINI_API_KEY (paste it there; it is not set by this script).
  2. Wait for the deploy, then:  curl -X POST -H "Authorization: Bearer ${ADMIN_TOKEN}" https://<rag-api domain>/admin/ingest
EOF
