# SPEC.md — KnowledgeMind Technical Specification

> Authoritative reference for architecture, data models, module contracts, and behaviour.
> When this document and the code disagree, the code is correct — open a PR to reconcile this
> file. `CLAUDE.md` is the short operational guide; this is the long-form design rationale.
>
> Scope note: this spec describes the **current** React + FastAPI build. The original design
> (Gradio UI, single-process `main.py`) has been superseded; where the two differ, this document
> reflects what ships today.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Repository Layout](#2-repository-layout)
3. [Data Models](#3-data-models)
4. [Module Specifications](#4-module-specifications)
   - 4.1 [Config & Launcher](#41-config--launcher)
   - 4.2 [API Layer (FastAPI)](#42-api-layer-fastapi)
   - 4.3 [Connectors](#43-connectors)
   - 4.4 [Commitment Extractor](#44-commitment-extractor)
   - 4.5 [Knowledge Graph](#45-knowledge-graph)
   - 4.6 [Monitor FSM](#46-monitor-fsm)
   - 4.7 [Privacy Router](#47-privacy-router)
   - 4.8 [Agent / Orchestrator](#48-agent--orchestrator)
   - 4.9 [Tools](#49-tools)
   - 4.10 [Memory & RAG](#410-memory--rag)
   - 4.11 [Proactive Runtime](#411-proactive-runtime)
   - 4.12 [Eval Harness](#412-eval-harness)
   - 4.13 [Front-end (React)](#413-front-end-react)
   - 4.14 [Project Advisor (projmgmt)](#414-project-advisor-projmgmt)
5. [Agency Level System](#5-agency-level-system)
6. [LLM Configuration](#6-llm-configuration)
7. [Privacy Contract](#7-privacy-contract)
8. [Error Handling Policy](#8-error-handling-policy)
9. [Configuration System](#9-configuration-system)
10. [Packaging & Distribution](#10-packaging--distribution)
11. [Evaluation & Benchmarks](#11-evaluation--benchmarks)

---

## 1. System Overview

KnowledgeMind is a privacy-aware personal AI agent. A FastAPI backend serves a React SPA and
wraps an engine organised into interacting layers:

```
┌──────────────────────────────────────────────────────────────────────┐
│  ENTRY POINT                                                          │
│  launcher.py  →  uvicorn api.main:app  →  opens browser at :8000      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  access-key auth (X-Access-Key / cookie)
┌──────────────────────────────▼───────────────────────────────────────┐
│  INGESTION LAYER                                                      │
│  Connectors (Slack · Calendar · Gmail · Mock)                        │
│       │  poll                                                         │
│       ▼                                                               │
│  Commitment Extractor  (spaCy NER + few-shot local LLM + timeparse)  │
│       │                                                               │
│       ▼                                                               │
│  Knowledge Graph  (SQLite + NetworkX)                                 │
│       │  conflict edge auto-created on temporal overlap (≥ 5 min)     │
│       ▼                                                               │
│  Monitor FSM  POLL → EXTRACT → UPDATE → CHECK → ALERT (LangGraph)    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  KG context summary (structured, not raw)
┌──────────────────────────────▼───────────────────────────────────────┐
│  ROUTING LAYER                                                        │
│  Privacy Router  (privacy score × complexity score → LOCAL | CLOUD)  │
└────────────────┬──────────────────────────┬──────────────────────────┘
          ┌──────▼──────┐           ┌────────▼───────┐
          │    LOCAL    │           │     CLOUD      │
          │  Qwen2.5    │           │ Groq Llama-3.x │
          │  (Ollama)   │           │  (free tier)   │
          └──────┬──────┘           └────────┬───────┘
┌────────────────▼───────────────────────────▼─────────────────────────┐
│  AGENT LAYER                                                          │
│  HybridMindAgent — L1 (augmented) · L2 (workflow) · L3 (ReAct)       │
│  Tools: query_kg · find_free_slots · conflict_edges · web_search ·   │
│         code_execution · rag_query · google_calendar · gmail ·       │
│         send_message · strava · apple_health · todoist · spotify     │
└────────────────┬─────────────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────────────┐
│  PROACTIVE LAYER (optional, off by default)                          │
│  hermes_jobs + hermes_skills → cron scheduler → runner → nudges +    │
│  daily briefing (LLM-free)                                           │
└──────────────────────────────┬───────────────────────────────────────┘
┌──────────────────────────────▼───────────────────────────────────────┐
│  UI LAYER                                                             │
│  React SPA (frontend/dist) served by FastAPI · Project Advisor iframe │
└──────────────────────────────────────────────────────────────────────┘
```

**Core invariant.** All personal data — KG nodes, messages, calendar events, email bodies, Slack
content, Hermes biometric/activity signals — is processed locally at all times. The cloud model
receives only anonymised task descriptions, structured KG summaries, and non-sensitive public
queries. This invariant must never be violated (see §7).

**Degradation.** The app runs CPU-only and degrades to mock data when no API keys are set. If
Ollama is unreachable, LOCAL calls may fall back to Groq **except** for privacy-pinned steps,
which stay local and use heuristic fallbacks.

---

## 2. Repository Layout

```
KnowledgeMind/
├── launcher.py              # Entry point: runs uvicorn api.main:app on :8000, opens browser
├── launch_windows.bat       # Windows run-from-source: venv + deps + npm build + launcher.py
├── build_linux.sh           # Linux run-from-source: venv + deps + npm build + launcher.py
├── build_windows.spec       # PyInstaller spec (bundles api.main + frontend/dist + assets)
├── build_exe.bat            # Runs npm build then PyInstaller on Windows
├── requirements.txt
├── SPEC.md                  # ← this file
├── CLAUDE.md                # Operational guide for Claude Code
│
├── api/
│   ├── main.py              # FastAPI app: auth + CORS + endpoints + serves frontend/dist
│   ├── smoke.py             # Offline TestClient smoke check (CI)
│   └── simchat_routes.py    # SimChat endpoints
├── frontend/                # React (Vite) SPA — App.jsx, views.jsx, Login.jsx, api.js → dist/
│
├── config/
│   ├── store.py             # AppConfig dataclass + load/save; env > config.json > default
│   └── models.py            # Ollama model discovery via /api/tags
│
├── kg/
│   ├── schema.py            # SQLite DDL + init_db() + dataclasses (CommitmentNode, ConflictEdge)
│   ├── graph.py             # NetworkX builder + person-agnostic conflict detection
│   ├── queries.py           # query_kg(), find_free_slots(), conflict_edges()
│   ├── janitor.py           # Archive stale commitments + prune old turns
│   ├── connector_schema.py  # Separate connectors.db schema (Hermes snapshots)
│   └── connector_store.py   # Read/write Hermes signal snapshots
│
├── extraction/
│   ├── ner.py               # spaCy NER (Person, Date/Time entities)
│   ├── commitment.py        # Few-shot LLM soft-commitment extractor
│   ├── timeparse.py         # Relative-time resolver ("tomorrow", "EOD" → ts)
│   └── prompts.py           # Extraction prompt templates
│
├── monitor/fsm.py           # LangGraph FSM: POLL → EXTRACT → UPDATE → CHECK → ALERT
├── routing/router.py        # Privacy + complexity classifier → LOCAL/CLOUD
│
├── agent/
│   ├── orchestrator.py      # HybridMindAgent — L1/L2/L3
│   ├── tools.py             # TOOL_REGISTRY + dispatch_tool + tool implementations
│   ├── prompts.py           # L1/plan/execute/critique/replan prompts
│   └── token_tracker.py     # Per-session token accounting
│
├── connectors/              # base.py + slack/calendar/gmail + mock + factory
│                            # + strava/spotify/todoist/apple_health (Hermes signal sources)
├── hermes_tools/            # Hermes connectors wrapped as agent tools
├── tools/rag.py             # ChromaDB RAG over local documents
├── memory/memory_manager.py # Per-session turn history
├── guardrails/audit.py      # Privacy/audit trail
│
├── proactive/               # loader + scheduler + runner + briefing + outbox + insights
├── hermes_jobs/*.json       # Proactive job specs (cron + skill binding)
├── hermes_skills/*.md       # Proactive skill definitions
│
├── eval/                    # runner + judge + metrics + tracer (Stream-4 eval harness)
├── simchat/                 # Simulated-conversation extractor/personas/visualizer
├── projmgmt/                # Standalone "Project Advisor" sub-app, mounted at /projmgmt
│
├── benchmark.py             # Offline routing/privacy contract test (target 100%)
├── demo_conflicts.py        # End-to-end conflict demo (offline)
├── mcp_serve.py             # Optional: expose Hermes tools over MCP
└── data/                    # Mock data for offline/demo mode
```

---

## 3. Data Models

### 3.1 SQLite schema (`kg/schema.py`)

The primary database (`knowledgemind.db`, path from `AppConfig.db_path`). DDL is idempotent —
`init_db()` is safe to call on an existing DB and runs an additive migration for the `status`
column. Hermes signal snapshots live in a **separate** `connectors.db` (`kg/connector_schema.py`).

```sql
CREATE TABLE persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, aliases TEXT, embedding BLOB, created_at REAL NOT NULL
);

CREATE TABLE commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES persons(id),
    description TEXT NOT NULL,
    start_ts REAL NOT NULL, end_ts REAL,
    source TEXT NOT NULL,             -- 'calendar'|'slack'|'email'|'whatsapp'|'mock'
    commitment_type TEXT NOT NULL,    -- 'HARD'|'SOFT'|'TENTATIVE'
    confidence REAL NOT NULL DEFAULT 1.0,
    raw_text TEXT, channel_id TEXT, external_id TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'   -- 'active'|'archived' (janitor)
);

CREATE TABLE conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commitment_a_id INTEGER REFERENCES commitments(id),
    commitment_b_id INTEGER REFERENCES commitments(id),
    overlap_minutes REAL NOT NULL, detected_at REAL NOT NULL,
    alerted INTEGER DEFAULT 0          -- 0=pending, 1=user notified
);

CREATE TABLE turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
    timestamp REAL NOT NULL, tool_name TEXT, routing_decision TEXT,
    token_estimate INTEGER DEFAULT 0
);

CREATE TABLE rag_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL, content_hash TEXT NOT NULL UNIQUE,
    chunk_count INTEGER NOT NULL, indexed_at REAL NOT NULL
);

CREATE TABLE nudges (                  -- proactive runtime outbox
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL, skill TEXT NOT NULL, message TEXT NOT NULL,
    signals_json TEXT NOT NULL, generated_at REAL NOT NULL,
    dismissed INTEGER NOT NULL DEFAULT 0
);
```

Indices: `(start_ts,end_ts)`, `(status,start_ts)`, `(session_id,timestamp)`,
`(alerted,detected_at)`, `(generated_at DESC, dismissed)`.

Connection: `get_db_connection(path)` returns a `Row`-factory connection with
`busy_timeout=3000ms` and foreign keys ON. If `path` is not writable (read-only cloud FS), it
falls back to a shared **in-memory** SQLite singleton (data resets on restart) so the app never
crashes on a locked filesystem.

### 3.2 Core dataclasses

```python
@dataclass
class CommitmentNode:
    id: int; person_name: str; description: str
    start_ts: float; end_ts: float | None
    source: str; commitment_type: str; confidence: float; raw_text: str | None

@dataclass
class ConflictEdge:
    id: int; commitment_a: CommitmentNode; commitment_b: CommitmentNode
    overlap_minutes: float; alerted: bool

@dataclass
class RoutingResult:
    decision: RoutingDecision   # LOCAL | CLOUD
    privacy_score: float; complexity_score: float
    reason: str; tool_name: str | None; escalated: bool = False
```

### 3.3 AppConfig (`config/store.py`)

`AppConfig` is the single source of truth. Highlights (see file for the full set, including the
Hermes connector credentials and proactive-runtime toggles):

```python
local_model = "qwen2.5:3b"; ollama_base_url = "http://localhost:11434"
cloud_model = "llama-3.3-70b-versatile"; cloud_model_fast = "llama-3.1-8b-instant"
complexity_threshold = 0.6; max_local_retries = 2
allow_cloud_fallback = True        # False = personal work never leaves the device
monitor_interval_minutes = 15
db_path, connector_db_path, alerts_log_path, chroma_persist_dir  # → platform config dir
proactive_runtime_enabled = False  # background cron OFF by default
```

Storage lives in the platform config dir (§9), not in the repo.

---

## 4. Module Specifications

### 4.1 Config & Launcher

**`config/store.py`** — `get_config()` (singleton), `save_config()`, `update_config(**kwargs)`,
`reload_config()`. Priority: **env var override > config.json > hardcoded default**. A local
`.env` is loaded first (dev convenience); unfilled `your_...`/`...` placeholders are ignored so a
copied template never clobbers a working config.

**`config/models.py`** — `list_ollama_models(base_url)` queries `/api/tags`;
`get_recommended_models()` returns a curated order led by `qwen2.5:3b`.

**`launcher.py`** — starts `uvicorn api.main:app` on `127.0.0.1:8000`, polls until the server
responds, then opens the browser. Configuration (model + keys) is done in-app via the Settings
view; there is no separate setup process or restart step.

### 4.2 API Layer (FastAPI)

**`api/main.py`** mounts the engine and serves the SPA. Every `/api/*` route — **and the
`/projmgmt` sub-app** — is gated by `ACCESS_KEY` when it is set; the static SPA at `/` stays open
so the login screen can load.

**Access-key auth.** The key is accepted as an `X-Access-Key` header (KM's fetch calls) or a
`km_access` cookie (the projmgmt iframe, which cannot set headers; mirrored from localStorage at
login). Unset key → fully open (local dev).

**Endpoints (each `/api/*` gated):**
`GET /api/status` · `POST /api/scan` · `GET /api/commitments` · `GET /api/conflicts` ·
`POST /api/chat` · `GET|POST /api/documents` · `POST /api/rag/query` · `GET|POST /api/config` ·
`GET /api/connectors` · `GET /api/briefing` · `GET /api/nudges` · `POST /api/nudges/{id}/dismiss` ·
`GET /api/nudges/jobs` · `POST /api/nudges/run/{job}` · `POST /api/kg/janitor` · `GET /api/audit` ·
`GET /api/privacy/report` · `GET /api/eval/{report,traces,metrics}` · `POST /api/eval/run`.

The built React SPA is mounted last (`StaticFiles(..., html=True)`) so API routes take priority;
if `frontend/dist` is missing, `/` returns a "Frontend not built" hint instead of 500.

### 4.3 Connectors

**`connectors/base.py`** — `BaseConnector` ABC with `fetch_recent(since_ts) -> list[RawMessage]`
and `health_check() -> bool`. `connectors/factory.py` selects live vs mock per source.

| File | Source | Auth | Scope |
|------|--------|------|-------|
| `slack.py` | Slack API | `SLACK_BOT_TOKEN` | Read configured channels |
| `calendar.py` | Google Calendar | OAuth 2.0 | Read + create events + free/busy |
| `gmail.py` | Gmail API | OAuth 2.0 | Read + draft (send is blocked, see §4.9) |
| `mock.py` | `data/mock_*.json` | None | Offline/demo fallback |

**Hermes signal sources** (`strava`, `spotify`, `todoist`, `apple_health`) derive *signals*
(fitness/sleep/tasks/mood), **not** messages or commitments. They are wired as **agent tools**
(via `hermes_tools/`), **not** into the monitor. Each derives locally, records a snapshot to the
separate `connectors.db` (`kg/connector_store.py`), and falls back to mock data without keys.
`GET /api/connectors` surfaces them.

**Fallback rule.** A failed `health_check()` → use mock/cached data for that source and log a
warning. The system must never crash on a missing connector.

### 4.4 Commitment Extractor

- **`extraction/ner.py`** — spaCy `en_core_web_sm`: extracts `PERSON` and date/time entities into
  `(person_name, time_expression)` candidates.
- **`extraction/timeparse.py`** — resolves relative expressions ("tomorrow", "EOD", "next week")
  to absolute timestamps; falls back to the message timestamp when unresolved (`start_ts` is NOT
  NULL).
- **`extraction/commitment.py`** — few-shot local LLM. Output JSON only:
  `{is_commitment, confidence, time_expression, normalized_ts, commitment_type}`. On JSON parse
  failure after retries → return `None` (never crash).

**Classification:** confidence ≥ 0.85 → `HARD`; 0.60–0.85 → `SOFT`; < 0.60 → `TENTATIVE`.
TENTATIVE commitments are **not** alert-eligible.

### 4.5 Knowledge Graph

**`kg/graph.py`**
- `build_graph(conn) -> nx.DiGraph` — rebuilt from SQLite each cycle; not persisted.
- `detect_new_conflicts(conn, new_commitment_id)` — incremental check after insert.
- `find_conflicts(conn, window_hours=24)` — unalerted conflicts in window.
- `get_or_create_person`, `insert_commitment`, `get_person_commitments`.

**Conflict detection is person-agnostic.** Two commitments conflict if their half-open intervals
`[start, end)` overlap **≥ 5 minutes** (`MIN_OVERLAP_MINUTES`) anywhere on the user's personal
timeline — there is **no** same-person requirement (this is the deliberate "cross-signal" change
from the original person-scoped logic). Candidates are filtered to
`commitment_type != 'TENTATIVE' AND status = 'active'`. TENTATIVE commitments never raise
conflicts.

**`kg/queries.py`** (tool-callable): `query_kg`, `find_free_slots` (working hours 08:00–20:00),
`conflict_edges`.

**`kg/janitor.py`** — memory management run at startup and via `POST /api/kg/janitor`: archives
stale commitments (`status='archived'`) and prunes old turns.

### 4.6 Monitor FSM

**`monitor/fsm.py`** — a LangGraph `StateGraph`. Nodes: `polling → extracting → updating →
checking → alerting`, with an `error` node that logs, backs off, and returns to idle. A daemon
thread drives the loop on `monitor_interval_minutes`.

`MonitorState` carries `last_poll_ts`, `new_messages`, `new_commitments`, `new_conflicts`,
`alerts_fired`, `cycle_count`, `error`. Alerts are appended to `alerts.jsonl` (one JSON per line)
and surfaced to the UI; firing an alert sets `conflicts.alerted = 1`.

### 4.7 Privacy Router

**`routing/router.py`** — the most critical invariant. Inputs `task_text` + optional `tool_name`,
output `RoutingResult`. **PRIVACY-CRITICAL: do not add a `force_cloud` override or remove a tool
from `ALWAYS_LOCAL_TOOLS` without explicit approval.**

```python
PREFER_CLOUD_TOOLS  = {"web_search"}                 # may go CLOUD when privacy is low

ALWAYS_LOCAL_TOOLS  = {"query_kg", "find_free_slots", "conflict_edges",
                       "google_calendar", "gmail", "send_message", "code_execution",
                       "strava", "apple_health", "todoist", "spotify"}

PRIVACY_LOCAL_THRESHOLD = 0.65
```

**Tool privacy floors** (minimum privacy regardless of task text):

| Tool | Floor | | Tool | Floor |
|------|-------|---|------|-------|
| `query_kg` / `find_free_slots` / `conflict_edges` | 0.95 | | `apple_health` | 0.98 |
| `gmail` | 0.95 | | `strava` / `spotify` | 0.95 |
| `send_message` | 0.90 | | `todoist` | 0.90 |
| `google_calendar` | 0.85 | | `code_execution` / `rag_query` | 0.70 |
| `web_search` | 0.05 | | | |

**Decision logic (in order):**

```
if tool ∈ ALWAYS_LOCAL_TOOLS                          → LOCAL
elif tool ∈ PREFER_CLOUD_TOOLS and privacy < 0.65     → CLOUD
elif privacy >= 0.65                                  → LOCAL
elif complexity >= threshold and privacy < 0.65       → CLOUD
else                                                  → LOCAL  (conservative default)
```

Scores are heuristic: privacy from personal-signal keyword hits floored by the tool floor;
complexity from step-word hits + length. Privacy always wins.

### 4.8 Agent / Orchestrator

**`agent/orchestrator.py`** — `HybridMindAgent.run(user_input, agency_level)`. Three agency
levels (§5). Cloud planning/critique use Groq; tool-call dispatch and lightweight steps prefer the
local model. KG context is injected as **structured summaries**, never raw message text.

| Node | Model | Responsibility |
|------|-------|----------------|
| inject_kg_context | Python | Build structured KG summary for the relevant window |
| plan | Groq | Decompose task into steps (L2/L3) |
| route | Python | Apply the router per step |
| execute | local / Groq | Parse tool-call parameters |
| dispatch | Python | Call the tool via `dispatch_tool` |
| critique | Groq | Verdict: complete / incomplete / failed |
| replan | Groq | Revised plan on incomplete (L3, bounded) |

### 4.9 Tools

**`agent/tools.py`** — `TOOL_REGISTRY: dict[str, Callable[[dict], dict]]`. Registered tools:

```
query_kg · find_free_slots · conflict_edges · web_search · code_execution ·
rag_query · google_calendar · gmail · send_message · strava · apple_health · todoist · spotify
```

**Contract.** Every tool takes a `dict` and returns a `dict` with at least `{"success": bool}`
plus `"formatted"` (str for the LLM) or `"error"`. Tools **never raise** — `dispatch_tool` is the
catch-all that converts exceptions into `{"success": False, "error": ...}`.

Notable behaviours:
- `web_search` → Tavily, falling back to DuckDuckGo. The only `PREFER_CLOUD` tool.
- `code_execution` → local subprocess sandbox, syntax-validated, `CODE_TIMEOUT_SECONDS` timeout,
  no network.
- `gmail action="send"` is **blocked** — it returns an error directing the caller to draft; real
  sending requires an explicit, confirmed UI action.
- `google_calendar action="create"` requires live Google credentials and ISO start/end.

### 4.10 Memory & RAG

**`memory/memory_manager.py`** — per-session short-term history in the `turns` table:
`add_turn(...)`, `get_recent_turns(session_id, max_tokens)` (fills from most recent, drops oldest
past budget), `format_for_llm(...)`, `clear_session(...)`.

**`tools/rag.py`** — ChromaDB `PersistentClient` at `chroma_persist_dir`, embeddings via
`SentenceTransformerEmbeddingFunction` (`all-MiniLM-L6-v2`, CPU). PDF/TXT/MD ingestion with
content-hash dedup (`rag_documents`); queries return top-k chunks with scores. ChromaDB
unavailable → `rag_query` disabled, all other tools continue.

### 4.11 Proactive Runtime

**`proactive/`** — loader parses `hermes_jobs/*.json` + `hermes_skills/*.md`; the runner derives
signals on-device and composes a nudge into the `nudges` table; `briefing.py` composes an LLM-free
daily briefing from `status='active'` nudges. A hand-rolled cron `scheduler` (daemon thread, no
new dependency) fires due jobs but is **off by default** (`proactive_runtime_enabled`) so the
no-Ollama deployment never runs an unattended cron→Groq loop and exhausts the free tier.
`POST /api/nudges/run/{job}` fires a job manually; nudges are dismissable
(`POST /api/nudges/{id}/dismiss`).

### 4.12 Eval Harness

**`eval/`** — Stream-4 agent-quality harness. `runner.py` scores a golden set; `judge.py` is a
stub or Groq LLM-as-judge; `metrics.py` computes routing accuracy, latency, and TPR/TNR;
`tracer.py` emits canonical `run()` trace records (additive to the tool contract). Run offline
with `python -m eval.runner`, live with `--live`, Groq judge with `--judge groq`, a single case
with `--case G3 -v`. Surfaced via `GET /api/eval/{report,traces,metrics}` and `POST /api/eval/run`.

### 4.13 Front-end (React)

**`frontend/`** — a Vite SPA built to `frontend/dist`, served by FastAPI. `App.jsx` shells the
views in `views.jsx`; `Login.jsx` captures the access key (mirrored to a `km_access` cookie for
the projmgmt iframe); `api.js` wraps fetch with the `X-Access-Key` header. Views cover the
Dashboard, Knowledge Graph, Assistant (chat with per-step routing badges), Documents (RAG),
Connectors (Hermes signals), Proactive (jobs + nudges + briefing), Project Advisor (iframe), and
Settings. Build with `cd frontend && npm install && npm run build`; dev with `npm run dev` on
:5173 (proxies `/api` → :8000).

### 4.14 Project Advisor (projmgmt)

**`projmgmt/`** — a self-contained FastAPI app (own backend, vanilla-JS frontend, `pm_config`,
tests) **mounted at `/projmgmt`** as an ASGI sub-app. The import is wrapped in try/except so a
missing key just disables it without breaking KM. It ingests a Statement of Work → builds a
project KG + rules → a chat advisor that rates alignment and flags deviations. It uses the shared
`GROQ_API_KEY`, sits behind the same access-key lock (via the cookie), and keeps its `data/`
persistence separate from KM's KG. It does not share code or runtime with the KM engine — read
`projmgmt/CLAUDE.md` before working inside it.

---

## 5. Agency Level System

Three levels of orchestration, selectable per request. `AgencyLevel(str, Enum)` in
`agent/orchestrator.py`:

```python
L1_AUGMENTED  = "L1"   # Augmented LLM — single call + optional tool + synthesis
L2_WORKFLOW   = "L2"   # Workflow — plan → execute × N → critique (engineer-defined flow)
L3_AUTONOMOUS = "L3"   # Autonomous — ReAct loop (thought→action→observation) + bounded replan
```

| Dimension | L1 Augmented | L2 Workflow (default) | L3 Autonomous |
|-----------|--------------|-----------------------|---------------|
| Autonomy | Low | Medium | High |
| Predictability | High | Medium | Low |
| Token cost | Low | Medium | High |
| Control flow | Engineer-defined | Engineer-defined | LLM-directed |
| Replanning | None | None | Bounded |
| Best for | Lookup / Q&A | Structured multi-step | Open-ended / ambiguous |

**`agent/token_tracker.py`** records per-call token events (`node`, `model`, prompt/completion
tokens, agency level) and produces a per-session summary. Counts come from Groq
(`response.usage.*`) and Ollama (`prompt_eval_count` / `eval_count`).

---

## 6. LLM Configuration

| Role | Model | Called from |
|------|-------|-------------|
| NER assist + tool-call dispatch | `local_model` (Ollama) | extraction, `execute` |
| Soft commitment extraction | `local_model` (Ollama) | `extraction/commitment.py` |
| Planning / critique / replan | `cloud_model` (Groq) | orchestrator nodes |
| Fast cloud path (planning helper, fallback) | `cloud_model_fast` (Groq) | orchestrator |

**Ollama fallback.** If Ollama is unreachable, LOCAL calls fall back to `cloud_model_fast` via
Groq and log a warning — **except** privacy-pinned steps (§7), which stay local and use heuristic
fallback params. `allow_cloud_fallback = False` makes personal work fail closed instead.

---

## 7. Privacy Contract

Violations are critical bugs, not style issues.

1. **Raw personal data never reaches cloud.** The planner receives structured KG summaries
   (description, start/end, source type, commitment_type, confidence) — never raw Slack messages,
   email bodies, or calendar descriptions verbatim.
2. **`ALWAYS_LOCAL_TOOLS` is fixed.** Every tool in that set (KG tools, calendar, gmail,
   send_message, code_execution, and all four Hermes signal tools) routes LOCAL unconditionally.
   Removing an entry is a breaking change requiring explicit approval.
3. **Privacy score ≥ 0.65 → LOCAL, always.** No override flag, no bypass path.
4. **Privacy-pinned steps may not escalate.** A LOCAL-forced step that fails parsing uses
   heuristic fallback params — it does not escalate to cloud.
5. **`knowledgemind.db`, `connectors.db`, `alerts.jsonl`, `config.json` stay local.**
6. **Gmail send requires explicit UI confirmation** — `gmail action="send"` is blocked at the tool
   layer; the agent may only draft.
7. **Hermes signals are personal biometrics/activity** — pinned LOCAL with floors 0.90–0.98 and
   recorded only to the local `connectors.db`.

`GET /api/privacy/report` and `GET /api/audit` (`guardrails/audit.py`) expose the routing/privacy
trail for inspection.

---

## 8. Error Handling Policy

| Situation | Required behaviour |
|-----------|--------------------|
| LLM JSON parse fail | Retry with stricter prompt; then heuristic fallback params (log WARNING) |
| Non-privacy step still failing | May escalate to cloud (`escalated=True`) |
| Privacy-pinned step failing | Use fallback params, stay LOCAL, return degraded result |
| Tool raises | Caught by `dispatch_tool` → `{"success": False, "error": str(e)}`; continue |
| Connector fetch fails | Use mock/cached data; log; continue |
| Ollama unreachable | Fall back to `cloud_model_fast` (non-private only); log WARNING |
| Groq 429 / 401 | Back off / surface a Settings-level key error to the UI |
| Monitor FSM exception | Transition to `error`, log, back off, return to idle |
| SQLite locked / path unwritable | `busy_timeout` retry; then shared in-memory fallback |
| ChromaDB unavailable | Disable `rag_query`; all other tools continue |
| `code_execution` timeout | `{"success": False, "error": "Timed out after Ns"}` |

No single component failure may crash the FastAPI process.

---

## 9. Configuration System

All user configuration is stored as `config.json` in the platform config directory. There is no
`.env` in production; a local `.env` is a dev convenience. Priority: **env var > config.json >
default**.

**Platform config dir** (`config/store.py`):
- Windows: `%APPDATA%\KnowledgeMind\`
- Linux: `~/.config/KnowledgeMind/`
- macOS: `~/Library/Application Support/KnowledgeMind/`

**Files in the config dir:** `config.json`, `knowledgemind.db`, `connectors.db`, `alerts.jsonl`,
`google_token.json`, `chroma_db/`.

**Key environment variables:**

| Variable | Purpose |
|----------|---------|
| `ACCESS_KEY` | Locks the app (`X-Access-Key` / cookie); unset = open |
| `GROQ_API_KEY` | Cloud LLM (L2/L3 + cloud-routed tasks); shared with projmgmt |
| `TAVILY_API_KEY` | Web search (falls back to DuckDuckGo) |
| `SLACK_BOT_TOKEN`, `GOOGLE_CREDENTIALS_PATH` | Live Slack / Calendar / Gmail (else mock) |
| `STRAVA_*`, `TODOIST_API_TOKEN`, `SPOTIFY_*` | Hermes connectors (else mock) |
| `ALLOWED_ORIGINS` | CORS (only if the front-end is served from a different origin) |
| `KM_DB_PATH`, `KM_LOCAL_MODEL`, `KM_OLLAMA_URL`, `KM_CONNECTOR_DB_PATH` | Overrides |

The `KM_*` names are kept for backward compatibility; the plain names match `.env.example`.

---

## 10. Packaging & Distribution

### Run from source
- **Windows:** `launch_windows.bat` — checks Python + Ollama, creates `.venv`, installs deps,
  downloads the spaCy model, builds `frontend/dist` (if Node is present), runs `launcher.py`
  (`:8000`).
- **Linux/macOS:** `build_linux.sh` — same flow; `--run` skips install on subsequent launches and
  installs a `.desktop` shortcut.
- Both serve the React SPA from `frontend/dist`, so Node 20+ is required to build the UI.

### Standalone Windows .exe (PyInstaller)
`build_exe.bat` builds `frontend/dist` (npm) then runs `pyinstaller build_windows.spec --clean
--noconfirm` → `dist/KnowledgeMind/KnowledgeMind.exe`. The spec bundles the FastAPI app
(`api.main`, loaded via the uvicorn **string** target — forced in via `collect_submodules`), the
built `frontend/dist`, `hermes_jobs/`, `hermes_skills/`, `data/`, chromadb assets, and the
dynamically-imported `projmgmt/` tree. All asset paths resolve relative to each module's
`__file__`, so the bundle mirrors the source layout. Ollama is **not** bundled — users install it
from ollama.com.

### Cloud (Hugging Face Spaces)
`infra/` holds the Dockerfile (port 7860) + deploy guide; `.github/workflows/` runs CI and the HF
Spaces deploy. Set `ACCESS_KEY` + `GROQ_API_KEY` as Space secrets. With no Ollama in the Space,
the proactive cron stays off by default and cloud-routed tasks use Groq.

---

## 11. Evaluation & Benchmarks

### Offline contract tests (CI)
- `python benchmark.py --mode static` — routing/privacy contract (target **100%**): every KG /
  calendar / gmail / Hermes step must route LOCAL.
- `python demo_conflicts.py` — end-to-end conflict detection (offline).
- Per-module smoke tests — each module runs standalone (`python -m kg.graph`, etc.); the full list
  is in `.github/workflows/ci.yml`, plus `python -m api.smoke` (offline TestClient).

### Agent-quality eval (`eval/`)
`python -m eval.runner` scores a golden set offline (stub agent + stub judge); `--live` uses the
live agent (Ollama/Groq); `--judge groq` uses an LLM judge. Metrics: routing accuracy, latency,
and conflict-detection TPR/TNR.

### Target metrics

| Metric | Target |
|--------|--------|
| Routing accuracy (personal-data steps stay LOCAL) | 100% |
| Proactive alert precision | > 80% |
| Soft commitment recall | > 70% |
| Replan success (L3) | resolves within the bounded retry budget |
| End-to-end latency (CPU, i5-class) | < ~15s typical |
