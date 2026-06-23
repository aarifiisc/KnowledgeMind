# KnowledgeMind — Project Summary

> **Document version:** 3.0 — updated to reflect the Connector DB, UI overhaul, and Demo mode additions.
> Sections and items marked **`[NEW]`** or **`[CHANGED]`** did not exist or were different in the previous version.
> v1.0 → v2.0 delta is preserved below; v2.0 → v3.0 delta is added at the top.

---

## What Changed from v2.0 → v3.0 `[NEW]`

| Area | v2.0 | v3.0 |
|---|---|---|
| Connector data storage | Signals computed in-memory, not persisted | **`connectors.db`** — separate SQLite DB with 7 tables storing every connector poll |
| UI tabs | 5 tabs (Chat, KG, Monitor, Documents, Settings) | **8 tabs** — added 🔌 Connectors, 🗄️ DB Records, 🎬 Demo |
| Connector observability | No UI for connector state | **Connectors tab**: live status badges, per-connector signal cards, history tables, credential config |
| Database inspection | No raw DB view | **DB Records tab**: all 7 `connectors.db` tables, paginated, newest-first, one-click refresh |
| Demo / explainability | No walkthrough mode | **Demo tab**: interactive query-mode and preemptive-mode walkthroughs using mock data only |
| Mock data support | Connectors fell back silently | All 4 connectors expose explicit `health_check()` → `load_mock()` path; UI shows 🟡 mock badge |
| Nudge audit trail | No record of generated nudges | `preemptive_nudges` table — every generated nudge logged with type, message, surfaced flag, platform |
| Test coverage | No mode-specific test suite | `test_modes.py` — smoke tests for query routing (10 cases) and preemptive mode (4 connectors + fusion) |

---

## What Changed from v1.0 → v2.0

| Area | v1.0 | v2.0 |
|---|---|---|
| Orchestrator | KnowledgeMind's own `HybridMindAgent` (LangGraph) | **Hermes Agent** wraps KnowledgeMind via MCP |
| Communication channel | Slack (commitment extraction only) | **Discord** (bidirectional: query + delivery of preemptive alerts) |
| New data sources | None | **Strava, Apple Health, Todoist, Spotify** |
| Preemptive mode | Calendar/Slack conflict alerts via Gradio only | **Cross-app signal engine** delivered to Discord via Hermes cron |
| Local model | Qwen2.5-3B (all local tasks) | **Nous Hermes 3 (8B)** for personal data reasoning; Qwen2.5-3B retained for lightweight tasks |
| Cloud model policy | Groq for planning/critique (many task types) | **Groq opt-in only for web search** — all personal data stays on Ollama |
| Memory | Flat `turns` table (conversation history) | Turns table + **Hermes `USER.md`** (user modeling) + **learned baselines** (HRV, activity gap, etc.) |

---

## What It Is

KnowledgeMind is a privacy-aware personal AI agent that runs entirely on a laptop. It monitors your communication channels and life signals, builds a live personal knowledge graph of your commitments, and proactively surfaces the right nudge at the right time — without waiting to be asked.

**`[CHANGED]`** The original system watched Slack, Calendar, and Email, and alerted only on scheduling conflicts. The extension adds fitness (Strava, Apple Health), task management (Todoist), mood signals (Spotify), and bidirectional Discord communication — and introduces a genuinely autonomous preemptive mode powered by Hermes Agent.

The defining design choice is unchanged: **all personal data stays on-device**. The extension strengthens this — the new local model (Nous Hermes 3 via Ollama) handles all reasoning over personal data. Cloud models are now opt-in only for web search on public-data questions.

---

## Two Operating Modes `[CHANGED]`

| Mode | Trigger | Channel | Example |
|---|---|---|---|
| **Query** | User sends a message | Discord DM or Gradio UI | "How's my fitness been this week?" |
| **Preemptive** | Hermes cron fires on schedule | Discord DM | "PR comment from Arif 4h ago. You have a 3pm meeting — want to reply before?" |

In v1.0 only the Gradio UI existed, and preemptive alerts were limited to calendar conflict detection. Query mode now works from Discord in addition to the local UI.

---

## Core Concepts

### Hard vs Soft Commitments *(unchanged)*

| Type | Source | Example | Confidence |
|---|---|---|---|
| **Hard** | Google Calendar | "Team standup 10:00–10:30" | 1.0 |
| **Soft** | Slack / Chat | "see you at 4", "I'll send it by EOD" | 0.4–0.9 |
| **Tentative** | Soft, low confidence | "maybe lunch tomorrow?" | < 0.6 |

Hard commitments are ingested directly from calendar APIs. Soft commitments are extracted from free-text messages using spaCy NER + a few-shot prompted local LLM. Tentative commitments (confidence < 0.6) are stored but do not trigger conflict alerts.

### Privacy Routing `[CHANGED]`

The core routing logic is unchanged: every task is scored on privacy and complexity before any model call. What changed is the model assignment.

Decision logic (privacy always wins):
1. Tool in `ALWAYS_LOCAL_TOOLS` → **LOCAL**, unconditionally.
2. Privacy score ≥ 0.65 → **LOCAL**.
3. Complexity ≥ 0.6 AND privacy < 0.65 → **CLOUD** (opt-in, web search only).
4. Default → **LOCAL**.

**`[CHANGED]`** "LOCAL" now means Nous Hermes 3 via Ollama (upgraded from Qwen2.5-3B) for all personal-data reasoning. The cloud model (Groq) is restricted to a single tool type: `web_search`. Previously Groq handled planning, critiquing, and parameter parsing for many task types.

**`[NEW]`** Extended `ALWAYS_LOCAL_TOOLS` — new connectors are permanently pinned LOCAL:

| Tool (new) | Privacy floor |
|---|---|
| `strava_summary` | 0.95 |
| `apple_health_summary` | 0.98 |
| `todoist_summary` / `todoist_tasks` | 0.90 |
| `spotify_mood` | 0.95 |

---

## System Architecture `[CHANGED]`

The v2.0 architecture adds Hermes Agent as an orchestration layer above KnowledgeMind. KnowledgeMind exposes its KG tools as a local MCP server; Hermes connects to it as a dynamic tool backend alongside the four new connectors.

```
┌──────────────────────────────────────────────────────────────┐  [NEW]
│                  Hermes Agent (orchestrator)                  │
│                                                               │
│  Discord Gateway     Cron Scheduler      Skills / USER.md     │
│  (query mode)        (preemptive mode)   (user modeling)      │
│        │                   │                                  │
│        └──────────┬────────┘                                  │
│                   ▼                                           │
│          AIAgent  ·  ToolRegistry                             │
│          ├── strava_tool.py          [NEW]                    │
│          ├── apple_health_tool.py    [NEW]                    │
│          ├── todoist_tool.py         [NEW]                    │
│          ├── spotify_tool.py         [NEW]                    │
│          └── MCP → KnowledgeMind ───────────────────────┐    │
└────────────────────────────────────────────────────────┼─┘   │
                        Nous Hermes 3 (Ollama) ◄─────────┘     │
                        handles ALL personal data               │
                                                                │
              ┌─────────────────────────────────────┐  [CHANGED]
              │  KnowledgeMind MCP Server            │
              │  (mcp_serve.py)  [NEW]               │
              │                                      │
              │  km_query_kg · km_conflict_edges      │
              │  km_find_free_slots · km_calendar     │
              │  km_gmail                            │
              │                                      │
              │  Privacy Router enforces LOCAL        │
              │  inside MCP before tool dispatch     │
              └──────────────┬──────────────────────┘
                             │
         ┌───────────────────┴─────────────────────┐
         │                                         │
┌────────▼────────────────────────────────────────▼─────────┐
│   Monitor FSM (LangGraph)      Personal Knowledge Graph    │
│   Slack · Calendar · Email     SQLite + NetworkX           │
│   POLL→EXTRACT→UPDATE→CHECK    persons · commitments       │
│   →ALERT  (unchanged)          conflicts · turns           │
└────────────────────────────────────────────────────────────┘
```

**v1.0 architecture** (for comparison) had `HybridMindAgent` as the sole orchestrator, talking directly to all tools, with Groq handling planning and Qwen2.5-3B handling local tasks. There was no Hermes layer, no MCP server, and no external app connectors beyond Slack/Calendar/Gmail.

---

## Component Walkthrough

### 1. Launcher (`launcher.py`) *(unchanged)*
Entry point. On first launch shows the Gradio setup UI; on subsequent launches goes directly to the main UI and starts the background monitor FSM.

### 2. Config (`config/store.py`) `[CHANGED]`
`AppConfig` dataclass — single source of truth. Now includes new fields for all four connectors, learned behavioral baselines, and the MCP server port.

New fields (selected):
```python
local_model_reasoning: str = "nous-hermes3"   # upgraded from qwen2.5:3b for personal data
km_mcp_port: int = 6789
strava_access_token: str = ""
strava_weekly_km_avg: float = 0.0             # learned baseline
apple_health_export_path: str = "~/Library/Mobile Documents/..."
apple_health_hrv_baseline: float = 0.0        # learned baseline
todoist_api_token: str = ""
spotify_access_token: str = ""
preemptive_quiet_hours_start: int = 22
preemptive_quiet_hours_end: int = 8
```

### 3. KnowledgeMind MCP Server (`mcp_serve.py`) `[NEW]`
A lightweight MCP server that wraps KnowledgeMind's existing KG tools and exposes them to Hermes. The privacy router (`routing/router.py`) runs **inside this process** — before any tool executes, the router checks the routing decision and asserts LOCAL. No KG data passes through Hermes's model context; tool results are returned as structured responses directly to the calling tool invocation.

Exposed tools: `km_query_kg`, `km_find_free_slots`, `km_conflict_edges`, `km_calendar`, `km_gmail`.

Run alongside the main app: `python mcp_serve.py --port 6789`

### 4. Hermes Agent `[NEW]`
The new orchestration layer. `AIAgent` receives a user message (via Discord DM or cron prompt), assembles a system prompt from skills + USER.md, resolves available tools (MCP backend + Hermes-registered tools), and runs the agent loop.

Configured in `cli-config.yaml`:
- Default model: `ollama/nous-hermes3` — all personal data reasoning stays local
- Cloud model: Groq, permitted only for `web_search` tool calls (opt-in)
- Discord gateway: `dm_only: true`, restricted to the user's Discord ID

### 5. Background Monitor (`monitor/fsm.py`) *(unchanged)*
LangGraph FSM polling every 15 minutes. POLL → EXTRACT → UPDATE → CHECK → ALERT. Handles Slack and Calendar commitment extraction into the KG. Errors sleep 5 minutes before retry. Unchanged from v1.0.

### 6. Commitment Extraction (`extraction/`) *(unchanged)*
spaCy NER → few-shot local LLM → `CommitmentNode` records. Unchanged from v1.0.

### 7. Knowledge Graph (`kg/`) *(unchanged)*
SQLite schema: `persons`, `commitments`, `conflicts`, `turns`, `rag_documents`. NetworkX graph for conflict detection. All access via `get_db_connection()` / `init_db()` (idempotent). Unchanged from v1.0.

### 8. Privacy Router (`routing/router.py`) `[CHANGED]`
Core logic unchanged. `ALWAYS_LOCAL_TOOLS` and `TOOL_PRIVACY_FLOORS` extended with the four new connectors. The router now also runs inside the MCP server to enforce LOCAL constraints on incoming Hermes tool calls, in addition to its existing role in the KnowledgeMind agent loop.

### 9. Agent Orchestrator (`agent/orchestrator.py`) *(unchanged — now secondary)*
`HybridMindAgent` with L1/L2/L3 agency levels remains intact and powers the **Gradio UI** for local chat. Hermes Agent is the orchestrator for the Discord gateway and cron-based preemptive mode. The two orchestrators do not conflict — they share the KG via the MCP server.

### 10. New Connector Tools (`hermes_tools/`) `[NEW]`

All four tools are registered with Hermes's `ToolRegistry` via `registry.register()` at module import. All are pinned LOCAL (Nous Hermes 3, Ollama). Raw personal data is never passed to a cloud model.

**Strava (`strava_tool.py`)**
Fetches recent activities via Strava API v3 (OAuth2). Derives signals locally: days since last activity, weekly km vs 4-week average, activity streak. Raw GPS routes and timestamps never leave the device.

**Apple Health (`apple_health_tool.py`)**
Reads a daily JSON export dropped by an iOS Shortcut into iCloud Drive (`~/Library/Mobile Documents/.../HealthExport/`). Parses sleep hours, HRV, resting HR, steps, active energy. Computes derived labels ("sleep: poor", "recovery: low") against learned baselines. No external API call — purely file-based.

**Todoist (`todoist_tool.py`)**
Calls Todoist REST API v2 with a developer token (no OAuth). Returns full task titles, descriptions, due dates, and priorities — all processed by the local Hermes model, never cloud. Signals: overdue count, due-today count, heavy-day flag.

**Spotify (`spotify_tool.py`)**
Fetches `audio_features` (valence, energy, tempo) from Spotify Web API (PKCE OAuth). Derives mood label locally from numeric vectors — track names and artist names are never passed to any model. Signals: current mood, session duration, deep-work session detection.

### 11. Hermes Skills (`hermes_skills/`) `[NEW]`
Markdown context files attached to cron jobs. Each skill encodes domain rules and suppression logic. The AIAgent reads the skill as part of its volatile prompt tier before deciding whether to surface a signal.

| Skill | Attached to | Key rule |
|---|---|---|
| `morning_brief_skill.md` | Morning cron (08:00) | Max 3 bullets; fuse sleep + task load |
| `fitness_skill.md` | Fitness check (17:00) | Don't push activity if HRV/RHR suggests rest |
| `communication_skill.md` | Discord check (every 3h) | Only flag if unreplied > 4h AND not in meetings |
| `tasks_skill.md` | Evening wrap-up (18:30) | List max 3 overdue; ask to reschedule in evening |
| `mood_skill.md` | Mood check (every 30m, 09–21) | Only alert if deep work + meeting < 30 min |

### 12. Hermes Cron (`jobs.json`) `[NEW]`
Five scheduled agent tasks. Each fires a fresh `AIAgent` with no conversation history, injects the relevant skill as context, calls the appropriate tools, and delivers output to the user's Discord DM. The agent self-suppresses if nothing is worth flagging.

| Job | Schedule | Tools called |
|---|---|---|
| `morning_brief` | 08:00 daily | Strava + Apple Health + Todoist + `km_conflict_edges` |
| `fitness_check` | 17:00 daily | Strava + Apple Health |
| `discord_unread_check` | Every 3h | Discord (via gateway) + `km_calendar` |
| `evening_tasks` | 18:30 daily | Todoist |
| `mood_check` | Every 30m (09–21) | Spotify + `km_conflict_edges` |

### 13. Memory `[CHANGED]`

| Layer | v1.0 | v2.0 |
|---|---|---|
| Conversation history | `turns` SQLite table | `turns` table (unchanged) |
| User modeling | None | **Hermes `USER.md`** — agent-curated, updated across sessions |
| Procedural knowledge | None | **Hermes skills** (`.md` files attached to cron) |
| Behavioral baselines | None | **`AppConfig` learned fields** — HRV baseline, weekly km avg, typical activity gap; updated by weekly cron |

### 14. Tools (`agent/tools.py`) *(unchanged)*
All existing tools share the contract: accept `dict`, return `{"success": bool, "formatted": str}`, never raise. `dispatch_tool()` is the single catch-all boundary. Unchanged from v1.0.

### 15. RAG (`tools/rag.py`) *(unchanged)*
ChromaDB + `all-MiniLM-L6-v2` embeddings. User-uploaded PDFs chunked and indexed locally.

### 16. UI (`ui/`) `[CHANGED]`

Gradio. `ui/setup.py` (onboarding, unchanged) + `ui/app.py` (main UI, extended from 5 to **8 tabs**).

| Tab | Content |
|---|---|
| 💬 Chat | Message input, agency level selector (L1/L2/L3), routing log, token panel, email gate |
| 🕸️ Knowledge Graph | Live pyvis KG render, refresh button |
| 📡 Monitor | FSM state, manual poll trigger, alert feed |
| 📄 Documents | RAG file upload, indexed doc list |
| 🔌 Connectors *(new)* | Status overview table, per-connector signal cards + history tables + credential inputs, nudge history, quiet hours config |
| 🗄️ DB Records *(new)* | Raw rows from all 7 `connectors.db` tables; "Refresh all tables" re-reads live |
| 🎬 Demo *(new)* | Interactive query-mode and preemptive-mode walkthroughs using mock data |
| ⚙️ Settings | Model, API keys, OAuth connect, complexity threshold |

**Connectors tab** — for each connector (Discord, Strava, Apple Health, Todoist, Spotify):
- Status badge: 🟢 live / 🟡 mock / 🔴 error
- Last poll timestamp and total poll count
- Latest signal card (rendered from the most recent `connector_runs` row)
- History table (last 10 snapshots from the connector's detail table)
- Credential inputs (tokens, OAuth secrets) with a shared Save button

**DB Records tab** — reads directly from `connectors.db` via `get_connector_db_connection()`. Shows up to 25 rows per table, newest first. Timestamps formatted as `YYYY-MM-DD HH:MM`. Tables: `connector_runs`, `strava_snapshots`, `apple_health_snapshots`, `todoist_snapshots`, `spotify_snapshots`, `discord_snapshots`, `preemptive_nudges`.

**Demo tab** — two sections, no credentials required:

*Query Mode:* dropdown of 6 preset queries (or type your own) → "Run Query Demo" → shows routing table (decision, privacy score, complexity score, reason) alongside all 4 connector signals polled live from mock fixtures, plus a synthesised mock answer indicating which model would handle it and why.

*Preemptive Mode:* "Run Preemptive Demo" → runs a full simulated Hermes cron cycle in three columns: Step 1 Collect Signals, Step 2 Cross-Source Fusion Rules (4 rules evaluated with ✅/⬜ per rule), Step 3 Nudge Delivered (type, platform, message). The nudge is written to `preemptive_nudges` so the audit row is immediately visible in the DB Records tab.

### 17. Connector Database (`kg/connector_schema.py`, `kg/connector_store.py`) `[NEW]`

A dedicated SQLite database (`connectors.db`, co-located with `knowledgemind.db` in the platform-specific config dir) stores every connector poll. Schema is applied idempotently via `init_connector_db()`.

**Tables:**

| Table | One row per… | Key columns |
|---|---|---|
| `connector_runs` | Every poll attempt | `connector`, `polled_at`, `source`, `success`, `summary` |
| `strava_snapshots` | Strava poll | `days_since_last_activity`, `weekly_run_km`, `weekly_vs_4w_avg`, `gap_threshold_exceeded` |
| `apple_health_snapshots` | Health poll | `health_date`, `sleep_quality`, `sleep_hours`, `recovery_status`, `low_hrv`, `high_rhr`, `steps` |
| `todoist_snapshots` | Todoist poll | `total`, `overdue_count`, `due_today_count`, `heavy_day`, `clear_day`, `top_tasks` (JSON) |
| `spotify_snapshots` | Spotify poll | `mood`, `avg_valence`, `avg_energy`, `deep_work_session`, `session_minutes` |
| `discord_snapshots` | Hermes gateway write | `unread_count`, `mention_count`, `oldest_unread_hours` |
| `preemptive_nudges` | Each generated nudge | `nudge_type`, `message`, `surfaced`, `platform` |

`connector_store.py` provides the write/read API used by both `hermes_tools/` and `ui/app.py`:
- `record_strava/apple_health/todoist/spotify/discord(signals)` — inserts a `connector_runs` row + detail snapshot row in one transaction
- `get_latest(connector)` — most recent snapshot dict
- `get_history(connector, limit=10)` — list of snapshot dicts
- `get_run_counts()` — `{connector: int}` poll totals
- `get_latest_run(connector)` — most recent `connector_runs` row
- `record_nudge(type, message, surfaced, platform)` — nudge audit write
- `get_nudge_history(limit=20)` — recent nudge rows

Each `hermes_tools/*.py` calls `record_*()` after every successful poll (errors are swallowed with `except Exception: pass` to keep tool output unaffected by storage failures).

### 18. Test Suite (`test_modes.py`) `[NEW]`

Smoke-test harness for both operating modes. No live credentials required — all connectors fall back to mock data.

**Query mode (10 routing cases):**

| Query | Expected decision | Privacy | Complexity |
|---|---|---|---|
| "What is attention in transformers?" | LOCAL | 0.10 | 0.13 |
| "What's on my calendar today?" | LOCAL | 0.90 | 0.13 |
| "How was my sleep last night?" | LOCAL | 0.98 | 0.13 |
| "What tasks are overdue?" | LOCAL | 0.90 | 0.10 |
| "How am I doing fitness-wise?" | LOCAL | 0.95 | 0.13 |
| "What music am I listening to?" | LOCAL | 0.95 | 0.13 |
| "Book a meeting tomorrow at 3pm" | LOCAL | 0.90 | 0.38 |
| "Research and compare the latest LLM benchmark papers" | CLOUD | 0.10 | 0.63 |
| "Search for recent papers on RAG" | CLOUD | 0.10 | 0.50 |
| "Personal fitness data analysis" | LOCAL | 0.95 | 0.10 |

**Preemptive mode tests:**
- All 4 connector tools execute and return `success=True`
- Sources are all `"mock"` (no live credentials)
- Domain-specific signal keys present (e.g. `gap_threshold_exceeded`, `sleep_quality`, `mood`, `heavy_day`)
- Cross-source fusion produces a nudge from at least one of 4 rules
- Privacy contract: no raw GPS, HRV values, track names, or step counts in tool return values
- MCP server import resolves (`mcp_serve.py` importable)
- `connector_store.py` polls written to `connectors.db` (verified via `get_run_counts()`)

---

## Data Flow for a User Query `[CHANGED]`

**Via Discord (new path):**
1. User DMs the Hermes Discord bot.
2. Discord adapter routes message to `GatewayRunner._handle_message()`.
3. `AIAgent` assembles prompt from USER.md + relevant skills.
4. Tool calls resolved: personal-data tools → Nous Hermes 3 (Ollama); web search → Groq (opt-in).
5. MCP call to KnowledgeMind → privacy router asserts LOCAL → KG query executes → result returned.
6. Hermes tool calls (Strava, Apple Health, Todoist, Spotify) execute locally.
7. AIAgent synthesises answer using local Hermes 3 model.
8. Response sent as Discord DM.

**Via Gradio UI (unchanged path):**
1. User types a message in the Gradio UI.
2. `HybridMindAgent.run()` is called with the message and selected agency level (L1/L2/L3).
3. KG context is fetched (local SQLite, zero tokens).
4. Steps routed and dispatched; Groq handles planning/critique for non-personal steps.
5. Answer, routing log, and token summary returned to the UI.

---

## Data Flow for Proactive Monitoring `[CHANGED]`

**Commitment monitoring (unchanged from v1.0):**
1. Monitor daemon wakes every 15 minutes.
2. Slack connector fetches new messages; spaCy + local LLM extracts soft commitments.
3. Calendar source yields hard commitments directly.
4. Commitments inserted to KG; temporal overlap detection creates conflict edges.
5. New conflicts written to `alerts.jsonl`; Gradio UI alert panel refreshes.

**Preemptive signal mode (new):**
1. Hermes cron fires a scheduled job (e.g. morning brief at 08:00).
2. Fresh `AIAgent` created with skill file injected as context.
3. Agent calls the relevant connector tools (all execute locally via Ollama).
4. Agent calls `km_conflict_edges` or `km_calendar` via MCP (executes inside KM MCP server).
5. Skill prompt instructs: "only surface if something is genuinely actionable."
6. If signal passes the bar → Hermes sends a Discord DM to the user.
7. If nothing notable → agent returns `{"surface": false}`, no DM sent.
8. USER.md updated over time as the agent learns which signals the user acts on.

---

## Model Routing Summary `[CHANGED]`

| Task | v1.0 model | v2.0 model |
|---|---|---|
| Personal data reasoning (KG, fitness, tasks, mood) | Qwen2.5-3B (Ollama) | **Nous Hermes 3 (Ollama)** |
| Discord conversations | N/A | **Nous Hermes 3 (Ollama)** |
| Preemptive signal evaluation (cron) | N/A | **Nous Hermes 3 (Ollama)** |
| Planning + critique (L2/L3 in Gradio) | Groq Llama-3.3-70B | Groq Llama-3.3-70B *(unchanged)* |
| Web search | Groq (routed by complexity) | **Groq — opt-in only** |
| Greetings / trivial inputs | Qwen2.5-3B | Qwen2.5-3B *(unchanged)* |

---

## Tech Stack `[CHANGED]`

| Component | v1.0 | v2.0 | v3.0 |
|---|---|---|---|
| Agent orchestrator | LangGraph (`HybridMindAgent`) | **Hermes Agent** + LangGraph (FSM) | *(unchanged)* |
| Local LLM — reasoning | Qwen2.5-3B | **Nous Hermes 3 (8B)** via Ollama | *(unchanged)* |
| Local LLM — lightweight | Qwen2.5-3B | Qwen2.5-3B | *(unchanged)* |
| Cloud LLM | Groq Llama-3.3-70B (many types) | **Groq — opt-in, web search only** | *(unchanged)* |
| Communication channel | Slack (ingestion only) | Slack + **Discord** (bidirectional) | *(unchanged)* |
| Connectors | — | Strava, Apple Health, Todoist, Spotify | *(unchanged)* |
| Connector persistence | — | — | **`connectors.db`** (SQLite, 7 tables) |
| Inter-process bridge | — | **MCP** (`mcp_serve.py`, FastMCP) | *(unchanged)* |
| User modeling | — | Hermes USER.md + MEMORY.md | *(unchanged)* |
| Scheduling | — | Hermes cron (`jobs.json`) | *(unchanged)* |
| KG storage | SQLite + NetworkX | SQLite + NetworkX | *(unchanged)* |
| NER | spaCy `en_core_web_sm` | spaCy | *(unchanged)* |
| Embeddings | all-MiniLM-L6-v2 | all-MiniLM-L6-v2 | *(unchanged)* |
| Vector store | ChromaDB | ChromaDB | *(unchanged)* |
| UI tabs | 5 | 5 | **8** (+ Connectors, DB Records, Demo) |
| UI framework | Gradio | Gradio | *(unchanged)* |
| Language | Python 3.11+ | Python 3.11+ | *(unchanged)* |

---

## Benchmark Suite (`benchmark.py`) *(unchanged)*

30 tasks across 5 categories (6 each). Three modes: static (routing check, offline), ablation (compare local/hybrid/cloud), live (requires models). Targets: TCR ≥ 85%, routing accuracy 100%, latency ≤ 15s simple / ≤ 30s compound.

Extension evaluation targets (from v2.0, separate from the base benchmark):

| Metric | Target |
|---|---|
| Preemptive signal precision | > 65% |
| False positives (dismissed signals) | < 25% |
| Raw biometric data reaching cloud | 0% |
| Morning brief accuracy | > 90% |
| Cron cycle latency (all tools + reasoning) | < 45s |
| Discord round-trip latency | < 15s |

## Smoke Test Suite (`test_modes.py`) `[NEW]`

Offline harness requiring no live credentials or running models. Covers both operating modes end-to-end using mock data. Run with `python test_modes.py`.

**Query mode (10 routing cases):** verifies privacy score, complexity score, and LOCAL/CLOUD decision for a representative spread of queries — personal calendar/health/fitness/mood queries (all LOCAL) and public research queries (CLOUD when complexity ≥ 0.6 and privacy < 0.65).

**Preemptive mode:** runs all 4 connector tools, verifies mock signals, exercises cross-source fusion, checks the privacy contract (no raw biometrics in return values), confirms MCP server is importable, and asserts that `connector_store.py` persisted poll rows to `connectors.db`.

---

## File Map (additions in v3.0)

```
kg/
  connector_schema.py     [NEW] — connectors.db SQLite schema + init_connector_db()
  connector_store.py      [NEW] — write/read API for all connector tables and nudge log

hermes_tools/
  strava_tool.py          [CHANGED] — calls record_strava() after each poll
  apple_health_tool.py    [CHANGED] — calls record_apple_health() after each poll
  todoist_tool.py         [CHANGED] — calls record_todoist() in todoist_summary()
  spotify_tool.py         [CHANGED] — calls record_spotify() after each poll

config/
  store.py                [CHANGED] — added connector_db_path, discord_bot_token,
                                       discord_allowed_user_ids, discord_dm_only fields

ui/
  app.py                  [CHANGED] — 5 → 8 tabs; added Connectors, DB Records, Demo;
                                       ~35 new helper functions and event handlers

test_modes.py             [NEW] — query-mode routing tests + preemptive-mode smoke tests
```

---

*IISc Bengaluru · AI Engineering & Deep Learning · 2026 · Document version 3.0*
