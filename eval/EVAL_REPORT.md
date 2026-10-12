# RAG A/B evaluation — 2026-09-17_1934

Mode: **in-process (5 parallel processes, one per config, identical index copies)** · questions: 30 curated + 60 synthetic + 16 adversarial · embed `gemini-embedding-001`@768d · answer `gemini-3.5-flash` · light `gemini-3.5-flash-lite` · judge `gemini-3.5-flash`

| config | score | correctness | faithfulness | citations | hit@final | recall@cand | mrr@final | adversarial_pass | t_total_p50 | t_total_p95 | t_retrieve_p50 | t_rerank_p50 | gemini_calls_per_q | n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A-norerank** | 0.987 | 0.987 | 1.0 | 0.992 | 0.989 | 1 | 0.866 | 0.938 | 2291 | 3145 | 546 | 0 | 2 | 106 |
| **A** | 0.932 | 0.982 | 1.0 | 0.992 | 0.989 | 1 | 0.869 | 0.938 | 3592 | 4573 | 541 | 1140 | 3 | 106 |
| **B** | 0.931 | 0.987 | 0.992 | 0.988 | 0.989 | 0.989 | 0.862 | 0.938 | 3615 | 4332 | 548 | 1130 | 3 | 106 |
| **A+qx** | 0.892 | 1.0 | 1.0 | 0.992 | 0.989 | 1 | 0.858 | 0.938 | 4716 | 5856 | 1598 | 1203 | 4 | 106 |
| **B+qx** | 0.889 | 0.993 | 0.998 | 1.0 | 0.989 | 1 | 0.872 | 0.938 | 4719 | 5760 | 1656 | 1164 | 4 | 106 |

**Winner: A-norerank** (score = 0.35·correctness + 0.25·faithfulness + 0.20·hit@final + 0.10·adversarial + 0.10·latency).

Notes
- `hit@final` = ground-truth section/doc is among the sections handed to the answerer; `recall@cand` = it was in the candidate set before reranking (a reranker cannot recover what retrieval missed).
- Latencies are end-to-end wall-clock per question (retrieval + rerank + answer), single request at a time; see load_test for concurrency.
- Judge scores are model-graded; the adversarial column combines regex checks with the judge.
