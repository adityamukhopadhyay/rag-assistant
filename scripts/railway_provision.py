#!/usr/bin/env python3
"""
Provision the Railway project through the public GraphQL API (works with a workspace/team token,
which the CLI's `link`/`whoami` reject). Idempotent: re-running updates variables and leaves existing
services alone.

Reads RAILWAY_API_TOKEN, GEMINI_API_KEY from .env. Secrets are forwarded straight from the file to
the API — they are never printed.

    .venv/bin/python scripts/railway_provision.py            # create/update everything
    .venv/bin/python scripts/railway_provision.py --status   # just print what exists
"""
from __future__ import annotations
import argparse, json, os, secrets, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID", "")
API = "https://backboard.railway.com/graphql/v2"

def env() -> dict:
    d = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); d[k.strip()] = v.strip().strip('"').strip("'")
    return d

E = env()
TOKEN = E["RAILWAY_API_TOKEN"]

def gql(query: str, variables: dict | None = None):
    r = httpx.post(API, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                   json={"query": query, "variables": variables or {}}, timeout=60)
    r.raise_for_status(); d = r.json()
    if d.get("errors"):
        raise RuntimeError(json.dumps(d["errors"])[:500])
    return d["data"]

def project():
    return gql("""query($id:String!){ project(id:$id){ id name
        environments{ edges{ node{ id name } } }
        services{ edges{ node{ id name serviceInstances{ edges{ node{ environmentId domains{ serviceDomains{ domain } } } } } } } } } }""",
               {"id": PROJECT_ID})["project"]

def ensure_service(p, name: str, source: dict | None):
    for e in p["services"]["edges"]:
        if e["node"]["name"] == name:
            return e["node"]["id"], False
    inp = {"projectId": PROJECT_ID, "name": name}
    if source: inp["source"] = source
    sid = gql("mutation($i:ServiceCreateInput!){ serviceCreate(input:$i){ id } }", {"i": inp})["serviceCreate"]["id"]
    return sid, True

def set_vars(env_id: str, sid: str, variables: dict):
    gql("mutation($i:VariableCollectionUpsertInput!){ variableCollectionUpsert(input:$i) }",
        {"i": {"projectId": PROJECT_ID, "environmentId": env_id, "serviceId": sid, "variables": variables, "replace": False}})

def ensure_volume(env_id: str, sid: str, mount: str):
    vols = gql("""query($id:String!){ project(id:$id){ volumes{ edges{ node{ id name volumeInstances{ edges{ node{ serviceId mountPath environmentId } } } } } } } }""",
               {"id": PROJECT_ID})["project"]["volumes"]["edges"]
    for v in vols:
        for vi in v["node"]["volumeInstances"]["edges"]:
            if vi["node"]["serviceId"] == sid and vi["node"]["mountPath"] == mount:
                return v["node"]["id"], False
    vid = gql("mutation($i:VolumeCreateInput!){ volumeCreate(input:$i){ id } }",
              {"i": {"projectId": PROJECT_ID, "environmentId": env_id, "serviceId": sid, "mountPath": mount}})["volumeCreate"]["id"]
    return vid, True

def ensure_domain(env_id: str, sid: str):
    p = project()
    for e in p["services"]["edges"]:
        if e["node"]["id"] == sid:
            for si in e["node"]["serviceInstances"]["edges"]:
                if si["node"]["environmentId"] == env_id and si["node"]["domains"]["serviceDomains"]:
                    return si["node"]["domains"]["serviceDomains"][0]["domain"], False
    d = gql("mutation($i:ServiceDomainCreateInput!){ serviceDomainCreate(input:$i){ domain } }",
            {"i": {"environmentId": env_id, "serviceId": sid}})["serviceDomainCreate"]["domain"]
    return d, True

def main(status_only: bool):
    p = project()
    env_id = next(e["node"]["id"] for e in p["environments"]["edges"] if e["node"]["name"] == "production")
    print(f"project {p['name']} ({PROJECT_ID}) env production={env_id}")
    if status_only:
        for e in p["services"]["edges"]:
            n = e["node"]; doms = [d["domain"] for si in n["serviceInstances"]["edges"] for d in si["node"]["domains"]["serviceDomains"]]
            print(f"  service {n['name']:10} {n['id']}  domains={doms}")
        return

    state_p = ROOT / ".railway_state.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {}
    qdrant_key = state.get("qdrant_key") or secrets.token_hex(24)
    admin_token = state.get("admin_token") or secrets.token_hex(24)
    dashboard_token = state.get("dashboard_token") or secrets.token_hex(20)

    # --- qdrant
    q_sid, created = ensure_service(p, "qdrant", {"image": "qdrant/qdrant:latest"})
    print(f"qdrant service {q_sid} ({'created' if created else 'exists'})")
    set_vars(env_id, q_sid, {"QDRANT__SERVICE__API_KEY": qdrant_key, "QDRANT__STORAGE__STORAGE_PATH": "/qdrant/storage",
                             "QDRANT__SERVICE__HOST": "::", "QDRANT__TELEMETRY_DISABLED": "true"})
    vid, vcreated = ensure_volume(env_id, q_sid, "/qdrant/storage")
    print(f"qdrant volume {vid} ({'created' if vcreated else 'exists'})")

    # --- winner of the A/B evaluation, if it has been run
    # DEPLOY_DEFAULTS.json wins over the eval outcome: the deployed configuration is a product decision
    # (Aditya chose pipeline A — the A/B winner — with expansion and rerank ON so visitors see the full pipeline).
    dep_p = ROOT / "eval" / "DEPLOY_DEFAULTS.json"; win_p = ROOT / "eval" / "WINNER.json"
    win = json.loads(dep_p.read_text()) if dep_p.exists() else json.loads(win_p.read_text()) if win_p.exists() else {"pipeline": "a", "qx": False, "rerank": True}
    print(f"pipeline settings from {dep_p.name if dep_p.exists() else win_p.name}: {win}")

    # --- rag-api (source attached later: GitHub repo if connected, else `railway up`)
    a_sid, created = ensure_service(project(), "rag-api", None)
    print(f"rag-api service {a_sid} ({'created' if created else 'exists'})")
    set_vars(env_id, a_sid, {
        "GEMINI_API_KEY": E["GEMINI_API_KEY"],
        "QDRANT_URL": "http://qdrant.railway.internal:6333", "QDRANT_API_KEY": qdrant_key,
        "ADMIN_TOKEN": admin_token, "DASHBOARD_TOKEN": dashboard_token, "ACTIVE_PIPELINE": win["pipeline"], "QUERY_EXPANSION": str(win["qx"]).lower(),
        "RERANK": str(win["rerank"]).lower(), "PUBLIC_DOCS": "true",
        "CORS_ORIGINS": "https://adityamukhopadhyay.vercel.app,http://localhost:3000",
        "RATE_LIMIT_PER_MIN": "20", "RATE_LIMIT_PER_DAY": "400", "RATE_LIMIT_PER_USER": "5", "PORT": "8000",
    })
    avid, avcreated = ensure_volume(env_id, a_sid, "/data")
    print(f"rag-api volume {avid} ({'created' if avcreated else 'exists'}) at /data")
    set_vars(env_id, a_sid, {"QUESTION_LOG": "/data/questions.jsonl", "BOOKING_LOG": "/data/bookings.jsonl", "VISITOR_LOG": "/data/visitors.jsonl", "QUESTION_LOG_DAYS": "7"})
    domain, dcreated = ensure_domain(env_id, a_sid)
    print(f"rag-api domain https://{domain} ({'created' if dcreated else 'exists'})")

    state.update({"project_id": PROJECT_ID, "env_id": env_id, "qdrant_service_id": q_sid, "api_service_id": a_sid,
                  "qdrant_key": qdrant_key, "admin_token": admin_token, "dashboard_token": dashboard_token, "api_domain": domain})
    state_p.write_text(json.dumps(state, indent=1))
    print(f"state → {state_p.name} (git-ignored; holds ADMIN_TOKEN and the Qdrant key)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--status", action="store_true")
    main(ap.parse_args().status)
