"""Merge per-config row files (from `run_eval --tag`) into one summary + EVAL_REPORT.md, optionally persisting the winner.

    .venv/bin/python -m eval.merge --persist
"""
from __future__ import annotations
import argparse, glob, json, time
from pathlib import Path
from .run_eval import Row, summarise, report, CONFIGS, HERE, RESULTS
from rag.config import ROOT

def main(persist: bool):
    rows: list[Row] = []
    for f in sorted(glob.glob(str(RESULTS / "rows_*.json"))):
        for d in json.loads(Path(f).read_text()):
            r = Row(**{k: v for k, v in d.items() if k in Row.__dataclass_fields__})
            for k in ("_rec", "_hit", "_rr"):
                setattr(r, k, d.get(k, 0))
            rows.append(r)
    if not rows:
        raise SystemExit("no rows_*.json found")
    ts = time.strftime("%Y-%m-%d_%H%M")
    summary = summarise(rows)
    kinds = {k: len({r.qid for r in rows if r.kind == k}) for k in ("curated", "synthetic", "adversarial")}
    meta = {"ts": ts, "mode": "in-process (5 parallel processes, one per config, identical index copies)",
            "n_curated": kinds["curated"], "n_synthetic": kinds["synthetic"], "n_adversarial": kinds["adversarial"]}
    (RESULTS / f"{ts}_merged.json").write_text(json.dumps({"meta": meta, "summary": summary,
        "rows": [{k: v for k, v in r.__dict__.items() if not k.startswith("_")} for r in rows]}, indent=1, ensure_ascii=False))
    rep = report(summary, meta)
    (HERE / "EVAL_REPORT.md").write_text(rep)
    print(rep)
    if persist:
        best = max(summary.items(), key=lambda kv: kv[1]["score"] or 0)[0]
        cfg = CONFIGS[best]
        env = ROOT / ".env"
        lines = [l for l in (env.read_text().splitlines() if env.exists() else []) if not l.startswith(("ACTIVE_PIPELINE=", "QUERY_EXPANSION=", "RERANK="))]
        lines += [f"ACTIVE_PIPELINE={cfg['pipeline']}", f"QUERY_EXPANSION={'true' if cfg['qx'] else 'false'}", f"RERANK={'true' if cfg['rerank'] else 'false'}"]
        env.write_text("\n".join(lines) + "\n")
        (HERE / "WINNER.json").write_text(json.dumps({"config": best, **cfg, "ts": ts, "score": summary[best]["score"]}, indent=1))
        print(f"persisted winner {best} → .env and eval/WINNER.json")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--persist", action="store_true")
    main(ap.parse_args().persist)
