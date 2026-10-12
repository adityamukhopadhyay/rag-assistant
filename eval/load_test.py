"""
Concurrency soak against a running API. Mixed real questions, N concurrent workers, M total requests,
both endpoints. Reports latency percentiles, status-code mix, SSE first-token time, and whether the
rate limiter and cache behave.

    .venv/bin/python -m eval.load_test --url https://<api> --concurrency 25 --total 200
"""
from __future__ import annotations
import argparse, asyncio, json, random, statistics as st, time
from pathlib import Path
import httpx, os
ADMIN = os.environ.get("ADMIN_TOKEN", "")
HDR = {"Authorization": f"Bearer {ADMIN}"} if ADMIN else {}

HERE = Path(__file__).parent

def _p(xs, q): xs = sorted(xs); return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else 0

async def one_sync(client: httpx.AsyncClient, url: str, q: str, res: list):
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{url}/chat/sync", json={"question": q}, headers=HDR, timeout=120)
        res.append({"ep": "sync", "status": r.status_code, "ms": (time.perf_counter() - t0) * 1000,
                    "cached": None, "len": len(r.text)})
    except Exception as e:  # noqa: BLE001
        res.append({"ep": "sync", "status": -1, "ms": (time.perf_counter() - t0) * 1000, "err": type(e).__name__})

async def one_sse(client: httpx.AsyncClient, url: str, q: str, res: list):
    t0 = time.perf_counter(); first = None; cached = None; status = 0; n = 0
    try:
        async with client.stream("POST", f"{url}/chat", json={"question": q}, headers=HDR, timeout=120) as r:
            status = r.status_code
            async for line in r.aiter_lines():
                if line.startswith("event: token") and first is None:
                    first = (time.perf_counter() - t0) * 1000
                if line.startswith("data:") and '"cached"' in line:
                    cached = '"cached": true' in line
                n += 1
        res.append({"ep": "sse", "status": status, "ms": (time.perf_counter() - t0) * 1000, "first_ms": first, "cached": cached, "lines": n})
    except Exception as e:  # noqa: BLE001
        res.append({"ep": "sse", "status": -1, "ms": (time.perf_counter() - t0) * 1000, "err": type(e).__name__})

async def main(url: str, concurrency: int, total: int, sse_share: float):
    qs = [x["question"] for x in json.loads((HERE / "curated.json").read_text())]
    syn = HERE / "golden_synthetic.json"
    if syn.exists():
        qs += [x["question"] for x in json.loads(syn.read_text())][:60]
    res: list[dict] = []
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        async def task(i):
            async with sem:
                q = random.choice(qs)
                if random.random() < sse_share:
                    await one_sse(client, url, q, res)
                else:
                    await one_sync(client, url, q, res)
        t0 = time.perf_counter()
        await asyncio.gather(*(task(i) for i in range(total)))
        wall = time.perf_counter() - t0
    ok = [r for r in res if r["status"] == 200]
    codes = {}
    for r in res: codes[r["status"]] = codes.get(r["status"], 0) + 1
    lat = [r["ms"] for r in ok]
    first = [r["first_ms"] for r in ok if r.get("first_ms")]
    out = {"url": url, "concurrency": concurrency, "total": total, "wall_s": round(wall, 1), "rps": round(total / wall, 2),
           "status_codes": codes, "ok": len(ok), "errors": [r for r in res if r["status"] not in (200, 429)][:5],
           "latency_ms": {"p50": round(_p(lat, .5)), "p90": round(_p(lat, .9)), "p95": round(_p(lat, .95)), "max": round(max(lat)) if lat else 0},
           "sse_first_token_ms": {"p50": round(_p(first, .5)), "p95": round(_p(first, .95))} if first else None,
           "cache_hits": sum(1 for r in ok if r.get("cached")), "rate_limited_429": codes.get(429, 0)}
    print(json.dumps(out, indent=1))
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"load_{time.strftime('%Y-%m-%d_%H%M')}.json").write_text(json.dumps(out, indent=1))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--total", type=int, default=150); ap.add_argument("--sse-share", type=float, default=0.5)
    a = ap.parse_args()
    asyncio.run(main(a.url.rstrip("/"), a.concurrency, a.total, a.sse_share))
