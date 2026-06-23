# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Run the application (handles setup vs main UI automatically)
python launcher.py
# UI available at http://localhost:7860

# Benchmark suite
python benchmark.py                          # static routing check (offline, no LLM)
python benchmark.py --mode ablation          # compare local/hybrid/cloud routing strategies
python benchmark.py --mode live --level L2 --limit 5 -v  # live agent run (needs Ollama + Groq)

# Per-module smoke tests (no external services required for most)
python kg/schema.py
python routing/router.py
python monitor/fsm.py
python agent/tools.py
```

## Architecture

```
launcher.py               → entry point; routes to ui/setup.py (first run) or ui/app.py (main UI)
config/store.py           → AppConfig singleton; priority: env var > config.json > default
routing/router.py         → privacy + complexity classifier → LOCAL (Ollama) or CLOUD (Groq)
agent/orchestrator.py     → HybridMindAgent with 3 agency levels (L1/L2/L3)
agent/tools.py            → tool registry; all tools return {success, formatted}, never raise
monitor/fsm.py            → LangGraph FSM: POLL → EXTRACT → UPDATE → CHECK → ALERT
kg/schema.py              → SQLite schema; init_db() is idempotent; used by all KG modules
kg/graph.py, queries.py   → NetworkX graph + conflict detection + KG queries
extraction/               → spaCy NER (ner.py) + few-shot LLM soft commitment extractor (commitment.py)
connectors/               → Slack, Google Calendar, Gmail all implement BaseConnector; mock.py is the fallback
memory/memory_manager.py  → per-session conversation history stored in SQLite (turns table)
tools/rag.py              → ChromaDB-backed RAG for local documents
```

### Config storage (platform-aware)
- Windows: `%APPDATA%\KnowledgeMind\config.json`
- Linux: `~/.config/KnowledgeMind/config.json`
- DB, alerts, chroma dir are co-located. Use `get_config()` for paths; never hardcode them.
- `get_config()` returns a singleton. Call `reload_config()` after saving new config from the UI.

### Agency levels (agent/orchestrator.py)
- **L1** — single LLM call + one optional tool + synthesis
- **L2** — Groq plans steps → local LLM dispatches tools → Groq critiques (default)
- **L3** — ReAct loop (thought → action → observe) with automatic replan on critique failure

### Privacy routing (routing/router.py)
The privacy contract is the most critical invariant in the codebase:
- `ALWAYS_LOCAL_TOOLS` is a frozenset that is **never routed to cloud**, regardless of scores. Do not add an `override` or `force_cloud` flag and do not remove a tool from this set without explicit approval.
- Privacy score ≥ 0.65 → LOCAL (always). Complexity + low privacy → CLOUD.
- Privacy always wins: personal data tasks stay LOCAL even when complexity is high.
- `TOOL_PRIVACY_FLOORS` sets minimum privacy scores per tool (floors are enforced even if task text scores lower).

### Tool contract (agent/tools.py)
- Every tool takes `dict[str, Any]` and returns `{"success": bool, "formatted": str, ...}`.
- Tools must never raise. `dispatch_tool()` is the single catch-all boundary.
- `gmail` tool with `action="send"` is blocked — sending requires the UI confirmation gate in `ui/app.py`.
- Connector-backed tools (calendar, gmail, slack) degrade gracefully to mock data when credentials are absent.

### Monitor FSM (monitor/fsm.py)
- States: POLL → EXTRACT → UPDATE → CHECK → ALERT → (IDLE or ERROR)
- On error: sleeps `ERROR_SLEEP_SECONDS` (300s) before next cycle.
- Alerts written to `alerts.jsonl` (one JSON object per line); `alert_event` threading.Event signals the UI.
- `monitor_runner` is a shared singleton started as a daemon thread by `launcher.py` after the main UI loads.

### Knowledge Graph
- SQLite schema: `persons`, `commitments`, `conflicts`, `turns`, `rag_documents`
- Commitment types: `HARD` (calendar, confidence=1.0), `SOFT` (chat, 0.4–0.9), `TENTATIVE` (<0.6, no hard alerts)
- Conflict edges are auto-created on temporal overlap; `alerted` flag prevents re-alerting on re-poll.
- Always open the DB via `get_db_connection(cfg.db_path)` — it calls `init_db()` which is idempotent.

## Environment variables

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq cloud LLM (required for L2/L3) |
| `TAVILY_API_KEY` | Web search (falls back to DuckDuckGo if absent) |
| `SLACK_BOT_TOKEN` | Slack connector (falls back to mock) |
| `GOOGLE_CREDENTIALS_PATH` | OAuth credentials for Calendar/Gmail (defaults to `./credentials.json`) |
| `KM_DB_PATH` | Override SQLite path (used by smoke tests) |
| `KM_LOCAL_MODEL` | Override local Ollama model |
| `KM_OLLAMA_URL` | Override Ollama base URL |
| `MAX_REACT_ITERATIONS` | Cap L3 ReAct loop iterations (default 5) |
