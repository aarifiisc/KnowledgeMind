# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is
KnowledgeMind — a privacy-aware personal AI agent. A **FastAPI** backend (`api/main.py`) serves a **React** front-end (`frontend/`) and wraps the engine: a SQLite + NetworkX personal knowledge graph, a LangGraph background monitor, a privacy router (LOCAL vs CLOUD), an L1/L2/L3 ReAct agent, and a set of connectors. Runs CPU-only and degrades to mock data when no API keys are set.

## Commands
```bash
# Python deps (use the project venv)
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m spacy download en_core_web_sm

# Build the React front-end (FastAPI serves frontend/dist)
cd frontend && npm install && npm run build && cd ..

# Run the app  → http://127.0.0.1:8000  (login with ACCESS_KEY if it is set)
.venv/bin/python launcher.py

# Dev with hot reload (two terminals)
.venv/bin/uvicorn api.main:app --reload      # backend on :8000
cd frontend && npm run dev                    # Vite on :5173 (proxies /api → :8000)

# Tests
.venv/bin/python benchmark.py --mode static   # offline routing/privacy contract (target 100%)
.venv/bin/python demo_conflicts.py            # end-to-end conflict demo (offline)
.venv/bin/python -m kg.graph                  # per-module smoke test (each module has one;
                                               # see .github/workflows/ci.yml for the full list)

# Eval harness (Stream 4 — agent quality/routing/latency)
.venv/bin/python -m eval.runner                          # offline stub agent + stub judge
.venv/bin/python -m eval.runner --live                   # live agent (Ollama/Groq), stub judge
.venv/bin/python -m eval.runner --live --judge groq       # live agent + Groq judge
.venv/bin/python -m eval.runner --case G3 -v               # single golden case, verbose
```

## Architecture
```
launcher.py            → entry point; runs uvicorn api.main:app on :8000, opens the browser
api/main.py            → FastAPI: access-key auth + CORS + endpoints + serves frontend/dist
frontend/              → React (Vite) SPA: App.jsx, views.jsx, Login.jsx, api.js
routing/router.py      → privacy + complexity classifier → LOCAL (Ollama) or CLOUD (Groq)
agent/orchestrator.py  → HybridMindAgent, 3 agency levels (L1/L2/L3)
agent/tools.py         → tool registry (dispatch_tool); every tool returns {success, formatted}
monitor/fsm.py         → LangGraph FSM: POLL → EXTRACT → UPDATE → CHECK → ALERT
proactive/             → Proactive runtime: loader (jobs/skills) + cron scheduler + runner
                         + briefing composer + dismissable nudge outbox
kg/                    → SQLite + NetworkX KG; person-agnostic conflict detection
kg/janitor.py          → memory mgmt: archive stale commitments + prune old turns
extraction/            → spaCy NER + few-shot commitment extractor + timeparse.py resolver
connectors/            → Slack/Calendar/Gmail (BaseConnector) + Hermes signal sources (below)
tools/rag.py           → ChromaDB RAG over local documents
memory/memory_manager.py → per-session history (turns table)
config/store.py        → single source of truth for user config; priority is
                         env var override > config.json > hardcoded default (no .env in prod)
eval/                  → Stream-4 eval harness: runner (golden-set scoring) + judge
                         (stub/Groq LLM-as-judge) + metrics (routing accuracy, latency, TPR/TNR)
                         + tracer (canonical run() trace records, additive to Contract 2)
projmgmt/              → mounted sub-app at /projmgmt ("Project Advisor": SOW → KG + rules → chat)
```

### API endpoints (every `/api/*` is gated by `ACCESS_KEY` when set)
`GET /api/status` · `POST /api/scan` · `GET /api/commitments` · `GET /api/conflicts` ·
`POST /api/chat` · `GET|POST /api/documents` · `POST /api/rag/query` · `GET|POST /api/config` ·
`GET /api/connectors` · `GET /api/briefing` · `GET /api/nudges` · `POST /api/nudges/{id}/dismiss` ·
`GET /api/nudges/jobs` · `POST /api/nudges/run/{job}` · `POST /api/kg/janitor` · `GET /api/audit` ·
`GET /api/privacy/report` · `GET /api/eval/{report,traces,metrics}` · `POST /api/eval/run`. The static
SPA is served at `/` (not gated, so the login screen can load); the **projmgmt** sub-app is mounted
at `/projmgmt` (gated too — see below).

### Proactive runtime (`proactive/`)
Loader parses `hermes_jobs/*.json` + `hermes_skills/*.md`; the runner derives signals on-device and
composes a nudge into the `nudges` table. A hand-rolled cron `scheduler` (daemon thread, no new dep)
fires due jobs, but is **off by default** (`proactive_runtime_enabled`) so the no-Ollama Space never
runs an unattended cron→Groq loop. `POST /api/nudges/run/{job}` fires a job manually; the React
**Proactive** view lists jobs + nudges + a daily **briefing** (`proactive/briefing.py`, LLM-free,
`status='active'` only). `kg/janitor.py` (run at startup + `POST /api/kg/janitor`) archives stale
commitments + prunes turns. (The earlier `runtime/` package was the first cut of this and has been
retired in favour of `proactive/`.)

### Access-key auth (api/main.py)
Set `ACCESS_KEY` to lock the app: every `/api/*` **and `/projmgmt`** request must carry the key — as an `X-Access-Key` header (KM's fetch calls) or a `km_access` cookie (the projmgmt iframe, which can't set headers; mirrored from localStorage at login). Unset → open (local dev). The static SPA at `/` stays open so the login screen can load.

### Privacy routing (routing/router.py) — the most critical invariant
- `ALWAYS_LOCAL_TOOLS` is never routed to cloud. Do NOT add a force_cloud flag or remove a tool without approval.
- Privacy ≥ 0.65 → LOCAL. Low privacy + high complexity → CLOUD. Privacy always wins.
- `TOOL_PRIVACY_FLOORS` pins per-tool minimum privacy (KG/calendar/gmail ≥ 0.90; Hermes signal tools 0.90–0.98).

### Agency levels (agent/orchestrator.py)
**L1** one call + one optional tool + synthesis · **L2** Groq plan → local dispatch → Groq critique (default) · **L3** ReAct loop with replan.

### Tool contract (agent/tools.py)
Every tool: `dict -> {"success": bool, "formatted": str, ...}`, never raises (`dispatch_tool` is the catch-all). `gmail action="send"` is blocked — sending requires an explicit confirmed UI action.

### Hermes connectors (signal sources)
`connectors/{strava,spotify,todoist,apple_health}.py` derive **signals** (fitness/sleep/tasks/mood) — not messages or commitments — so they are wired as **agent tools** (`strava`, `apple_health`, `todoist`, `spotify` in `agent/tools.py`, via `hermes_tools/`), NOT into the monitor. Each derives locally, records a snapshot to `kg/connector_store.py` (a separate `connectors.db`), and falls back to mock data without keys. `GET /api/connectors` surfaces them; the React **Connectors** view renders them. `mcp_serve.py` optionally exposes the tools over MCP as a separate process (`python mcp_serve.py`). `hermes_skills/*.md` + `hermes_jobs/*.json` drive the **proactive runtime** (`proactive/`, above).

### Project Advisor (projmgmt sub-app)
`projmgmt/` is a self-contained FastAPI app (own `backend/`, vanilla-JS frontend, `pm_config`, tests) **mounted at `/projmgmt`** by `api/main.py` (ASGI sub-app; the import is wrapped in try/except so a missing key just disables it without breaking KM). It ingests a Statement of Work → builds a project KG + rules → a chat advisor that rates alignment and flags deviations. It uses the **shared `GROQ_API_KEY`** (resolved in `projmgmt/backend/pm_config.py`), is surfaced in the React UI as the **Project Advisor** iframe view, and sits behind the same access-key lock (via the cookie). Its `data/` persistence is separate from KM's KG.

### Knowledge graph
Tables: `persons`, `commitments`, `conflicts`, `turns`, `rag_documents`. Commitment types HARD/SOFT/TENTATIVE. Conflict detection is **person-agnostic** (the user's whole timeline) and skips TENTATIVE. Open the DB via `get_db_connection(cfg.db_path)` (idempotent `init_db`).

### Unrelated subproject (`projmgmt/`)
`projmgmt/` is a separate, standalone app (a SoW-driven team-management chatbot) with its own
`CLAUDE.md`/`SPEC.md`, FastAPI backend, and frontend. It does not share code or runtime with the
KnowledgeMind engine above — read `projmgmt/CLAUDE.md` before working inside it.

## Deployment
`infra/` holds the Dockerfile (HF Spaces, port 7860) + a deploy guide; `.github/workflows/` has CI + the HF Spaces deploy. Set `ACCESS_KEY` + `GROQ_API_KEY` as Space secrets.

## Environment variables
| Variable | Purpose |
|---|---|
| `ACCESS_KEY` | Locks the app (X-Access-Key); unset = open |
| `GROQ_API_KEY` | Cloud LLM (L2/L3 + cloud-routed tasks) |
| `TAVILY_API_KEY` | Web search (falls back to DuckDuckGo) |
| `SLACK_BOT_TOKEN`, `GOOGLE_CREDENTIALS_PATH` | Live Slack / Calendar / Gmail (else mock) |
| `STRAVA_*`, `TODOIST_API_TOKEN`, `SPOTIFY_*` | Hermes connectors (else mock) |
| `ALLOWED_ORIGINS` | CORS origins (only if the front-end is served from a different origin) |
| `KM_DB_PATH`, `KM_LOCAL_MODEL`, `KM_OLLAMA_URL` | Overrides |
