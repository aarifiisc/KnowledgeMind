# SPEC — Cross-Signal Intelligence

---

## 0. How to run this stream separately

```bash
# from the repo root
git checkout -b cross-signal

.venv/bin/pip install -r requirements.txt          # already installed in the project venv
cd frontend && npm install && cd ..                # for the UI piece

# the loop you'll use while building:
.venv/bin/python -m proactive.insights             # the new module's offline smoke (you create it)
.venv/bin/python benchmark.py --mode static        # must stay 100% (don't touch routing)
cd frontend && npm run build && cd ..              # UI compiles
.venv/bin/python -m api.main                        # serve :8000, then curl /api/insights
```
Everything must work **offline** (no Ollama, no keys) — the connectors return mock signals and
record real snapshots, so the whole stream is exercisable on the bundled data.

---

## 1. Goal & user value
Turn the Hermes **signals** (sleep/recovery, task-load, fitness, mood) and the **commitment
timeline** into a single **readiness-vs-load** read so the app can say, deterministically:

> *"You have 5 commitments today (1 conflict) but slept 5.2 h and recovery is low — consider
> deferring the soft ones."*

This is the capability the merged briefing only *hints* at today. It makes the product feel like it
understands the user's day, not just their calendar.

---

## 2. Current state — what already exists (do NOT rebuild)
- **Connector snapshots are already persisted** to `connectors.db` by each Hermes tool. Read them
  with `kg.connector_store.get_latest(name)` / `get_history(name, limit)` for
  `name ∈ {todoist, apple_health, strava, spotify, discord}`. Fields available per connector:
  - `apple_health`: `sleep_quality, sleep_hours, recovery_status, low_hrv, high_rhr, steps`
  - `todoist`: `total, overdue_count, due_today_count, heavy_day, clear_day, top_tasks`
  - `spotify`: `mood, avg_valence, avg_energy, deep_work_session, session_minutes`
  - `strava`: `days_since_last_activity, weekly_run_km, weekly_vs_4w_avg, gap_threshold_exceeded`
- **The briefing already gathers signals + does *light* correlation.** `proactive/briefing.py` has
  `_gather_signals()` (loops `connector_store.get_latest(...)`), `_task_load()`, `_readiness()` — but
  they're **flat passthroughs** displayed in the digest; there is **no combined score**, no
  commitment-load coupling, and **no API**. Extend this, don't duplicate it.
- **Commitments** live in the KG (`kg.schema.get_db_connection(cfg.db_path)`, `commitments` table,
  now with a `status` column — filter `status='active'`). Conflicts via `kg.queries.conflict_edges(conn, days=1)`.
- **`GET /api/insights` does not exist yet** — this stream adds it.
- Connectors are **already LOCAL-pinned** in `routing/router.py` — privacy is handled; don't touch routing.

**Design implication:** the snapshots already have history in `connectors.db`. So the P0 "bridge" is a
**read + correlation layer**, *not* a new storage table. (An in-KG `signals` table is an optional P1 —
see FR-1.5 — only if you want signals joined in the KG db for graph analytics.)

---

## 3. Scope / files
- **Create** `proactive/insights.py` — signal gather (reuse the briefing's pattern) + the
  deterministic `compute_readiness()` + a `compose_insights(db_path)` entry point + a `__main__` smoke.
- **Edit** `api/main.py` — add `GET /api/insights` (thin wrapper over `compose_insights`).
- **Edit** `frontend/src/views.jsx` + `App.jsx` — an **Insights** view + nav item.
- **Optional** `proactive/briefing.py` — have the briefing reuse `compute_readiness()` so the digest
  and the Insights view agree.
- **Do not** modify `routing/`, the `run()` contract, or existing commitment rows (additive only).

---

## 4. Design

### 4.1 Signal gather
Factor the briefing's `_gather_signals()` into `proactive/insights.py` (or import it) so both call one
implementation: `gather_signals() -> {name: snapshot|None}` via `connector_store.get_latest(name)`.

### 4.2 Readiness correlation (pure function, no LLM)
`compute_readiness(signals: dict, load: dict) -> dict`. Deterministic, start at 100, subtract
penalties, clamp [0,100], attach the factors that fired:

| Signal | Condition | Impact |
|---|---|---|
| apple_health | `sleep_hours < 6` / `< 7` | −20 / −10 |
| apple_health | `recovery_status == 'low'` / `'moderate'` | −18 / −6 |
| apple_health | `low_hrv` / `high_rhr` | −8 / −6 |
| todoist | `overdue_count` | −3 each, capped −18 |
| todoist | `heavy_day` | −8 |
| load | `commitments_today > 6` / `> 4` | −15 / −8 |
| load | `conflicts > 0` | −6 |
| spotify | `mood == 'low'` or `avg_valence < 0.4` | −5 |

Label: `>=75 fresh · 45–74 ok · <45 strained`. Return
`{score, label, factors:[{signal, detail, impact}], recommendation}` where `recommendation` is a
**rule-based** string (no LLM), e.g. *strained + (heavy_day or commitments>4)* →
"Heavy day on low recovery — consider deferring soft/tentative commitments." Keep the table in one
place so it's tunable; the exact numbers are a starting point, not sacred.

### 4.3 `GET /api/insights`
```json
{
  "date": "2026-06-23",
  "readiness": { "score": 58, "label": "ok",
    "factors": [{"signal":"apple_health","detail":"slept 5.2h","impact":-20},
                {"signal":"todoist","detail":"6 overdue","impact":-18}],
    "recommendation": "Heavy day on low recovery — consider deferring soft commitments." },
  "signals": { "apple_health": {...}, "todoist": {...}, "spotify": {...}, "strava": {...} },
  "load": { "commitments_today": 5, "conflicts": 1, "next": [{"description":"...", "at":"16:00"}] }
}
```
Gate is automatic (`/api/*` is behind the access key). Uses `get_config().db_path` (the demo DB at runtime).

### 4.4 Insights view (React)
A new **Insights** nav item (reuse the `shield`/a new icon). Render: a **readiness gauge** (score +
label, color by `local`/`warn`/`danger` tokens), the **factor list** (what's helping/hurting), the
**signal cards** (sleep, recovery, task-load, mood, fitness), and **today's load** (commitments +
conflicts). Follow the existing view pattern in `views.jsx` (KPI row + `card` + design tokens).

---

## 5. Functional requirements

### Core (P0) — the runnable stream
- **FR-1.1 — Signal gather layer** (`proactive/insights.py`, reuse `connector_store.get_latest`).
- **FR-1.2 — `compute_readiness()`** per §4.2 (deterministic, factors + recommendation, unit-smoke-tested).
- **FR-1.3 — `GET /api/insights`** per §4.3.
- **FR-1.4 — Insights React view** + nav.

### Extended (P1)
- **FR-1.5 — Signal history in the KG (optional).** An additive `signals` table in `kg/schema.py`
  `(source, kind, value, derived_labels, ts)` populated from snapshots — only if you want graph-level
  joins/trends beyond `connectors.db`’s own history. Justify before adding (avoid duplicate storage).
- **FR-1.6 — Rolling baselines.** Compute the config-reserved baselines
  (`apple_health_hrv_baseline`, `…_rhr_baseline`, `strava_weekly_km_avg`) from `get_history(...)` and
  feed them into the readiness deltas (low_hrv relative to *your* baseline, not a constant).
- **FR-1.7 — Briefing reuse.** `proactive/briefing.py` calls `compute_readiness()` so the digest and
  Insights agree (one source of truth).
- **FR-1.8 — Trend sparklines** in the view from `get_history(name, 14)`.

### Stretch (P2)
- Cross-source event **de-dup** (Slack "lunch 12:30" + calendar "Lunch with Lena" → one event) and
  commitment **lifecycle** (`done/cancelled/missed`). *(These are data-quality, only loosely
  "cross-signal" — split into a separate effort if it grows.)*
- Semantic KG search; per-node provenance.

---

## 6. Non-goals
- Nudge delivery / the cron scheduler (that's `proactive/` runtime — already built).
- Privacy routing of signals (already LOCAL-pinned in `routing/router.py`).
- Any LLM call in the correlation — it must be deterministic + offline.
- Changing `run()` (Contract 2) or existing commitment/connector schemas non-additively.

---

## 7. Acceptance criteria
- **Given** the bundled mock signals + commitments, **then** `GET /api/insights` returns a readiness
  block whose `label`/`score` **changes with the inputs** — e.g. low sleep + heavy day + >4
  commitments ⇒ `strained` with the right `factors`; a clear day ⇒ `fresh`.
- **Given** `compute_readiness(signals, load)` called directly with crafted inputs, **then** each
  penalty row in §4.2 is exercised by the `__main__` smoke (assert score + label + factor presence).
- **Given** the app running offline, **then** the **Insights** view renders the gauge, factors,
  signal cards, and today's load with no console errors.
- **Regression:** `benchmark.py --mode static` still **100%**; existing smoke tests still pass.

---

## 8. Testing (all offline)
- `proactive/insights.py` `__main__`: feed 3 crafted signal/load fixtures (strained, ok, fresh) and
  assert the label + a key factor — same stub pattern as `proactive/briefing.py`'s `__main__`.
- Live check: `python -m api.main`, then
  `curl -s localhost:8000/api/insights | python -m json.tool` (run a scan / open Connectors first so
  snapshots exist).
- Hand the readiness fixtures to **Stream 4** (`eval/`) as a small golden set so insight quality is tracked.

---

## 9. Definition of done
`proactive/insights.py` (gather + `compute_readiness` + `compose_insights`) with an offline smoke;
`GET /api/insights` live; the **Insights** React view + nav; briefing optionally reusing the
correlation; benchmark still 100%; additive-only (no schema/contract breakage); a short reflection on
the readiness model + what you'd calibrate with real data.

---

## 10. Progress — P0 complete (2026-06-23)

**Status: all four P0 functional requirements (FR-1.1 … FR-1.4) shipped and verified offline.**

### Branch
Built on **`cross-signal`**, cut from **`origin/main`** (`8c42fce`). Note the deviation from §0's
literal `git checkout -b cross-signal`: local `main` was 55 commits behind and is missing *everything*
this stream reuses (`proactive/`, `kg/connector_store.py`, `hermes_jobs/`, `hermes_skills/`, the
`status` column). `origin/main` is the superset (it contains all of `data-knowledge` + 1 merge commit),
so branching there satisfies "from main" **and** makes the reuse-not-rebuild design viable. Confirmed
`origin/main` carries `proactive/briefing.py`, `connector_store`, the connectors, and
`commitments.status` before branching.

### What was built (additive only)
| FR | File | Change |
|---|---|---|
| FR-1.1 | `proactive/insights.py` | `gather_signals()` — one signal-read impl (reuses `connector_store.get_latest`), returns `{name: snapshot\|None}` for `{todoist, apple_health, strava, spotify}`. |
| FR-1.2 | `proactive/insights.py` | `compute_readiness(signals, load)` — deterministic, no LLM. Penalty weights are module constants (`P_*`) so the §4.2 table lives in one tunable place. `+ _recommendation()` (rule cascade) `+ _compute_load()` (today's count + conflicts + next 3) `+ compose_insights()`. |
| FR-1.3 | `api/main.py` | `GET /api/insights` — thin wrapper over `compose_insights`; returns the §4.3 shape at top level. `_ensure_connector_snapshots()` lazily seeds `connectors.db` (only for connectors with no snapshot) so the view works on first load. Wrapped in try/except → `JSONResponse` 500, never crashes the UI. Gated automatically by the access key (`/api/*`). |
| FR-1.4 | `frontend/src/views.jsx` + `App.jsx` | **Insights** view + nav item/icon. Readiness donut gauge (colour by `local`/`warn`/`danger`), recommendation, factor list, today's-load KPIs + `next` timeline, and 4 signal cards (sleep/recovery, task-load, mood, fitness). Reuses existing `card`/`kpi`/`conn-card`/`badge` classes + design tokens. |
| §4.1 | `proactive/briefing.py` | `_default_signals()` now delegates to `insights.gather_signals()` (filters to present-only) — one signal-read implementation, briefing + Insights agree. Readiness *shape* deliberately **not** swapped (would break the Proactive view's `briefing.readiness.recovery_status/.low_hrv/.sleep_hours`); see TODO FR-1.7. |
| tests | `api/smoke.py` (new) | Offline API-layer smoke (TestClient): `/api/insights` deep shape, `/api/briefing`, `/api/status`. The repo's first endpoint test. |
| tests | `proactive/insights.py` `__main__` | Extended: `gather_signals()` contract + default `compose_insights` path (`signals=None`, empty-KG degrade). |
| — | `.github/workflows/ci.yml` · `requirements.txt` | Added `proactive.insights` + a `python -m api.smoke` step to the offline backend job; added `httpx` (TestClient dep). |

### Verification (all offline, no Ollama / no keys)
- `python -m proactive.insights` → **PASS**. Smoke exercises **every** §4.2 penalty row (13 isolated
  per-row impact assertions + overdue-scaling-below-cap), the three narrative labels
  (`strained=0 · ok=71 · fresh=100`), `compose_insights` end-to-end on a seeded KG, **plus** the
  `gather_signals()` contract and the default `compose_insights` path (empty-KG graceful degrade).
- `python -m api.smoke` → **PASS** (new). `/api/insights` 200 (deep shape + label↔score-band agreement
  + the 4 seeded signals), `/api/briefing` 200 (the `_default_signals → gather_signals` path), `/api/status` 200.
- `python -m proactive.briefing` → **PASS** (gather refactor didn't regress the digest).
- `benchmark.py --mode static` → **100% (30/30)** — routing/privacy contract intact.
- **Full offline sweep (37 entry points)** → 35 PASS; the 2 non-passes are pre-existing and untouched by
  this stream (`proactive.runner` is a `--job`-required CLI; `proactive.scheduler` runs the daemon loop
  forever → timeout). CI module-smoke list (14) + `demo_conflicts.py` + `demo_privacy.py` + `eval.runner`
  (offline) all green. Simulated CI `backend` job (smokes + benchmark + demo + `api.smoke`) → **GREEN**.
- `cd frontend && npm run build` → **builds clean** (39 modules).
- Live: `python -m api.main` → `GET /api/insights` **HTTP 200** with `{date, readiness{score,label,
  factors,recommendation}, signals{4}, load{commitments_today,conflicts,next}}`; `/` serves the SPA 200.

### Reflection on the readiness model + what I'd calibrate with real data
The model is intentionally a transparent, deterministic **subtractive scorecard** (start at 100, each
condition fires a fixed penalty, clamp to [0,100], surface the factors that fired). Strengths: fully
explainable (every point lost is a labelled factor), offline, unit-testable, and tunable from one block
of constants. Honest limitations and what real data would change:
- **The weights are guesses.** `−20` for `<6 h` sleep vs `−18` for low recovery is a hand-set ordering,
  not learned. With real history I'd fit the weights to an outcome signal (e.g. self-rated day quality,
  or commitments actually completed vs deferred) rather than asserting them.
- **Thresholds should be personal, not constant.** `low_hrv`/`high_rhr` are booleans the connector
  already derives against config-reserved baselines (`apple_health_hrv_baseline`, `…_rhr_baseline`,
  `strava_weekly_km_avg`) that are currently `0.0`. FR-1.6 (rolling baselines from `get_history`) is the
  first real-data win: penalise HRV relative to *your* 30-day median, not an absolute flag.
- **Penalties are additive + independent; reality has interactions.** Low sleep *and* a heavy day is
  likely worse than the sum suggests. A small interaction term (or a multiplicative "compounding"
  factor) is the natural next iteration once there's data to justify it.
- **No positive factors yet.** The score only ever subtracts, so "what's helping" is always empty. Great
  recovery / a clear day could *add* headroom; I'd add credit terms once weights are calibrated.
- **`strained` cut-off (`<45`) is unvalidated.** I'd move the fresh/ok/strained boundaries to wherever
  they best separate good-vs-bad days in real outcome data.

---

## 11. TODO

### Done (P0)
- [x] FR-1.1 — `gather_signals()` (shared with briefing)
- [x] FR-1.2 — `compute_readiness()` per §4.2 (deterministic, factors + recommendation, every row smoke-tested)
- [x] FR-1.3 — `GET /api/insights` (+ lazy connector seed, never-500 wrapper)
- [x] FR-1.4 — **Insights** React view + nav
- [x] §4.1 — briefing reuses the shared `gather_signals()`
- [x] Regression: benchmark 100%, full offline sweep green, frontend builds
- [x] CI: `proactive.insights` + a `python -m api.smoke` step added to the backend job
- [x] Tests: `api/smoke.py` (new API-layer smoke) + extended `insights` smoke (gather + default path); `httpx` added to requirements

### Remaining (P1)
- [ ] **FR-1.5 — Signal history in the KG (optional).** Additive `signals` table in `kg/schema.py`.
      *Justify before adding* — `connectors.db` already has history, so only do this if graph-level joins
      are actually needed (avoid duplicate storage).
- [ ] **FR-1.6 — Rolling baselines.** Compute `apple_health_hrv_baseline` / `…_rhr_baseline` /
      `strava_weekly_km_avg` from `get_history(...)` and feed them into the deltas (relative, not constant).
- [ ] **FR-1.7 — Full briefing reuse.** Have `briefing.py` call `compute_readiness()` for its readiness
      block too. **Blocked by a UI contract:** the Proactive view reads
      `briefing.readiness.recovery_status/.low_hrv/.sleep_hours`. Either add the `{score,label,factors}`
      block under a *new* key, or migrate the Proactive view first. (Gather is already shared.)
- [ ] **FR-1.8 — Trend sparklines** in the Insights view from `get_history(name, 14)`.
- [ ] Hand the readiness fixtures to **Stream 4** (`eval/`) as a small golden set (§8).

### Remaining (P2 / stretch)
- [ ] Cross-source event **de-dup** (Slack "lunch 12:30" + calendar "Lunch with Lena" → one event).
- [ ] Commitment **lifecycle** (`done/cancelled/missed`).
- [ ] Semantic KG search; per-node provenance.
