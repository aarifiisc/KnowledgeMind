# Evaluation runs backing the paper

Curated, immutable copies of the eval-harness outputs that the paper's numbers
were computed from. The live `eval/reports/` and `eval/traces/` directories are
gitignored (regenerated on every run); these copies are the frozen provenance.

Hardware: Intel Core i5-1235U (10C/12T), CPU-only. Local model `qwen2.5:3b` via
Ollama; cloud model `llama-3.3-70b-versatile` via Groq. Judge: stub.

## Reports (`reports/`)

| File | Mode | Agency level | n | Mean latency | Used for |
|------|------|--------------|---|--------------|----------|
| `report_20260624T011622.json` | live | L1 | 13 | 25.7 s | Per-level latency (App. D) |
| `report_20260624T005852.json` | live | L2 | 13 | 26.5 s | Main eval latency + App. D |
| `report_20260624T012730.json` | live | L3 | 13 | 50.9 s | Per-level latency (App. D) |

The offline stub run (`...T004952`, mean 0.0 s) is intentionally excluded: it
backs no number in the paper.

## Traces (`traces/`)

39 per-case `run()` traces (3 live runs x 13 golden cases). Each carries
`agency_level`, `elapsed` (seconds), `routing_log`, and `token_summary`. The
per-agency-level medians in the paper are computed by grouping these by
`agency_level`:

| Level | Median | Mean | Max |
|-------|--------|------|-----|
| L1 | 21.0 s | 25.7 s | 79.9 s |
| L2 | 11.0 s | 26.5 s | 155.6 s |
| L3 | 23.5 s | 50.9 s | 323.5 s |

(L3 returned empty answers on 3/13 cases due to replanning exhaustion; see the
`silent_failures` field of the L3 report.)

## Numbers produced outside this folder

- **Routing accuracy 100% (30/30):** `python benchmark.py --mode static`
  (offline contract test; prints to stdout, no JSON artifact).
- **Conflict detection (all found, 0 false alerts):** `python demo_conflicts.py`
  (offline mock-data demo).

## Reproduce

```bash
python benchmark.py --mode static            # routing contract
python demo_conflicts.py                      # conflict detection
python -m eval.runner --live --level L1        # L1 latency
python -m eval.runner --live --level L2        # L2 latency (default)
python -m eval.runner --live --level L3        # L3 latency
```
