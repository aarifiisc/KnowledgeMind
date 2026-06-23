# KnowledgeMind 🧠

> A privacy-aware hybrid AI agent with a personal knowledge graph and proactive commitment awareness.

**KnowledgeMind** runs on your laptop — no GPU, no paid services — and watches your Slack, Calendar, and Email to build a live knowledge graph of your commitments. It detects scheduling conflicts before you notice them, executes multi-step tasks with automatic replanning, and keeps all your personal data strictly on-device.



---

## What It Does

Most AI assistants wait to be asked. KnowledgeMind doesn't.

A background monitor loop continuously ingests your communication channels, extracts both **hard commitments** (calendar events) and **soft commitments** (informal agreements from Slack messages like *"see you at 4"*), and fuses them into a personal knowledge graph. When a conflict is detected — say, a Slack message overlapping a calendar event — the agent notifies you unprompted.

When you do give it a task, it reasons over the live knowledge graph as context, calls tools in sequence, and replans automatically if a step fails.

Everything personal — your graph, your messages, your calendar — stays local. Only non-sensitive tasks (web search, public lookups) are optionally routed to a free cloud model.

---

## Demo Scenarios

| # | You say | What happens |
|---|---------|--------------|
| 0 | *(nothing)* | Agent detects Slack message conflicts with 4 PM calendar event — alerts you unprompted |
| 1 | *"Book me a doctor at 4 PM today"* | KG finds conflict → replans to 5 PM → books via Calendar API. All LOCAL. |
| 2 | *"What did Priya say about the deadline?"* | KG returns Priya's commitment nodes from Slack with timestamps and confidence scores |
| 3 | *"What are the latest LLM papers this week?"* | Router scores privacy=0.1 → routes CLOUD. Tavily search via Groq. |
| 4 | *"Do I have any conflicts this week?"* | KG temporal overlap query returns all conflict edges across channels for 7 days |
| 5 | *"Send my calendar data to ChatGPT"* | Router scores privacy=0.9 → refused. System explains why and offers local alternative. |

---

## Architecture

```
Communication Channels
  Slack · Calendar · WhatsApp · Email
          │
          ▼  (every 15 min)
┌─────────────────────────┐
│   Background Monitor    │  IDLE → POLL → EXTRACT → UPDATE → CHECK → ALERT
│   FSM (LangGraph)       │
└───────────┬─────────────┘
            │  spaCy + few-shot LLM
            ▼
┌─────────────────────────┐
│   Personal Knowledge    │  Person → Commitment → TimeSlot
│   Graph (SQLite+NetworkX│  Hard (Calendar) + Soft (Chat)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   Privacy Router        │  privacy score + complexity score
└────────┬────────────────┘
    ┌────┴────┐
    ▼         ▼
 LOCAL      CLOUD
 Qwen2.5   Groq
 -3B        Llama-3.3-70B
 (Ollama)   (free tier)
    │         │
    └────┬────┘
         ▼
┌─────────────────────────┐
│   ReAct Planner         │  Reason → Act → Observe → Replan
│   (LangGraph)           │
└─────────────────────────┘
         │
         ▼
  Tools: query_kg · web_search · find_free_slots
         book_slot · calendar_read · send_message
```

### Privacy Routing Rules

| Condition | Decision | Examples |
|-----------|----------|---------|
| Privacy score ≥ 0.65 | **LOCAL** (always) | KG queries, calendar, Slack, email |
| Complexity ≥ 0.6 + low privacy | **CLOUD** | Web research, multi-hop summaries |
| Default | **LOCAL** | Conservative fallback |

The UI shows every routing decision live — LOCAL (green) / CLOUD (yellow) — making the privacy architecture visible and auditable.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Local LLM | Qwen2.5-3B via [Ollama](https://ollama.com) |
| Cloud LLM (free) | Groq — Llama 3.3-70B (`llama-3.3-70b-versatile`) |
| Knowledge Graph | SQLite + NetworkX |
| NER / Extraction | spaCy + few-shot LLM prompting |
| Embeddings | `all-MiniLM-L6-v2` (sentence-transformers, 80 MB, CPU) |
| Orchestration | [LangGraph](https://langchain-ai.github.io/langgraph/) |
| Connectors | Slack SDK · Google Calendar API · Gmail · Hermes signal sources (Strava/Spotify/Todoist/Apple Health) |
| Web Search | Tavily (free tier) + DuckDuckGo fallback |
| Backend | FastAPI + Uvicorn (`api/main.py`), served on `:8000` |
| UI | React + Vite SPA (`frontend/`), built to `frontend/dist` and served by FastAPI |
| Language | Python 3.11+ · Node 20+ (front-end build) |

---

## Hardware Requirements

| | Minimum | Tested on |
|--|---------|-----------|
| CPU | Any modern x64 | Intel i5-1235U |
| RAM | 8 GB | 16 GB |
| GPU | **Not required** | None |
| OS | Windows 10/11, Ubuntu 22.04+ | Windows 11 |
| Cost | **Free** | All open-source + free-tier APIs |

---

## Setup

### 1. Install Ollama and pull the model

```bash
# Download Ollama from https://ollama.com/download
ollama pull qwen2.5:3b
```

### 2. Clone and install dependencies

```bash
git clone https://github.com/your-username/knowledgemind.git
cd knowledgemind
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 3. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
# Required
GROQ_API_KEY=your_groq_api_key        # free at https://console.groq.com
TAVILY_API_KEY=your_tavily_api_key    # free at https://tavily.com
SLACK_BOT_TOKEN=xoxb-...              # from https://api.slack.com/apps

# Optional (for live Calendar integration)
GOOGLE_CREDENTIALS_PATH=./credentials.json
```

> **Getting Groq:** Sign up at [console.groq.com](https://console.groq.com) → API Keys → Create key. Free tier gives 14,400 requests/day.

> **Getting Tavily:** Sign up at [tavily.com](https://tavily.com) → free tier gives 1,000 searches/month.

### 4. Google Calendar setup (optional but recommended)

1. Go to [Google Cloud Console](https://console.cloud.google.com) → Create project
2. Enable **Google Calendar API**
3. Create **OAuth 2.0 credentials** (Desktop app) → Download as `credentials.json`
4. Set `GOOGLE_CREDENTIALS_PATH=./credentials.json` in `.env`
5. First run will open a browser for OAuth consent — token auto-saved

If you skip this, the system uses mock calendar data for the demo.

### 5. Build the front-end

```bash
cd frontend && npm install && npm run build && cd ..
```

### 6. Run

```bash
# Entry point: runs uvicorn api.main:app on :8000 and opens the browser
python launcher.py
```

Open `http://127.0.0.1:8000` for the UI (log in with `ACCESS_KEY` if it is set).

**Dev with hot reload** (two terminals):

```bash
uvicorn api.main:app --reload      # backend on :8000
cd frontend && npm run dev          # Vite on :5173 (proxies /api → :8000)
```

**Offline checks** (no API keys needed):

```bash
python benchmark.py --mode static   # routing/privacy contract (target 100%)
python demo_conflicts.py            # end-to-end conflict demo
python -m eval.runner               # agent-quality eval (stub agent + stub judge)
```

---

## Project Structure

```
knowledgemind/
├── launcher.py              # Entry point — runs uvicorn api.main:app on :8000, opens browser
├── requirements.txt
├── .env.example
│
├── api/main.py              # FastAPI: access-key auth + CORS + endpoints + serves frontend/dist
├── frontend/                # React (Vite) SPA — App.jsx, views.jsx, Login.jsx, api.js
│
├── routing/router.py        # Privacy + complexity classifier → LOCAL (Ollama) / CLOUD (Groq)
├── agent/
│   ├── orchestrator.py      # HybridMindAgent — 3 agency levels (L1/L2/L3)
│   ├── tools.py             # Tool registry (dispatch_tool); every tool returns {success, formatted}
│   └── prompts.py           # Planner + executor system prompts
│
├── monitor/fsm.py           # LangGraph FSM: POLL → EXTRACT → UPDATE → CHECK → ALERT
├── proactive/               # Jobs/skills loader + cron scheduler + runner + briefing + nudge outbox
│
├── kg/                      # SQLite + NetworkX KG; person-agnostic conflict detection; janitor.py
├── extraction/              # spaCy NER + few-shot commitment extractor + timeparse.py
├── connectors/              # Slack/Calendar/Gmail (BaseConnector) + Hermes signal sources
├── hermes_tools/            # Strava/Spotify/Todoist/Apple Health wired as agent tools
├── tools/rag.py             # ChromaDB RAG over local documents
├── memory/memory_manager.py # Per-session history (turns table)
├── config/store.py          # Single source of truth for config (env > config.json > default)
├── eval/                    # Agent-quality eval harness: runner + judge + metrics + tracer
│
└── projmgmt/                # Standalone "Project Advisor" sub-app, mounted at /projmgmt
```

> See `CLAUDE.md` for the authoritative architecture reference, API endpoint list, and the privacy-routing invariants.

---

## Key Concepts

### Soft vs Hard Commitments

| Type | Source | Example | Confidence |
|------|--------|---------|-----------|
| **Hard** | Google Calendar | "Team standup 10:00–10:30" | 1.0 |
| **Soft** | Slack / Chat | *"see you at 4"*, *"I'll send it by EOD"* | 0.4–0.9 |
| **Tentative** | Soft, low confidence | *"maybe lunch tomorrow?"* | < 0.6 |

Soft commitments are extracted using spaCy for entity detection and a few-shot prompted local LLM for intent classification. Commitments with confidence < 0.6 are stored as `TENTATIVE` and do not trigger hard conflict alerts.

### Knowledge Graph Schema

```
Person ──has_commitment──► Commitment ──at_time──► TimeSlot
                               │
                               ├──source──► Channel (slack/calendar/email)
                               ├──confidence──► Float
                               └──conflicts_with──► Commitment  (auto-created on temporal overlap)
```

Conflict edges are inserted automatically when two commitments occupy overlapping TimeSlots. The monitor loop queries these edges every cycle.

### Privacy Router

Every subtask is scored on two axes before execution:

- **Privacy score** [0–1]: keyword + pattern matching on task content and tool type. KG queries, calendar, Slack → ≥ 0.65 → LOCAL.
- **Complexity score** [0–1]: structural heuristics (multi-step keywords, sentence count, word count). High complexity + low privacy → CLOUD.

Privacy always wins. A high-complexity task involving personal data stays LOCAL regardless of reasoning demand.

---

## Evaluation

| Metric | Target |
|--------|--------|
| Proactive alert precision | > 80% genuine conflicts |
| Soft commitment recall | > 70% on held-out Slack test set |
| Routing accuracy | 100% of personal data tasks stay LOCAL |
| Demo task completion | All 6 scenarios complete without error |
| End-to-end latency | < 10s per task on i5-1235U |
| Replan success rate | Conflict-triggered replan resolves in ≤ 1 retry |

---

## Limitations

- **Soft commitment extraction** degrades on highly ambiguous phrasing. Confidence scoring mitigates false alerts but is not a complete solution.
- **CPU inference** on Qwen2.5-3B averages 5–15s per call. Monitor loop uses batched extraction to reduce call frequency.
- **WhatsApp** connector is not implemented (unofficial API concerns). Add your own adapter in `connectors/` following the `BaseConnector` interface.
- **Entity deduplication** uses name-exact matching. Embedding-based dedup (planned for v2) would handle aliases and name variations.
- **Groq free tier** has rate limits (~30 req/min). Heavy evaluation may require pacing.

---

## Roadmap

- [x] RAG over local documents (notes, PDFs) as an additional source — `tools/rag.py` (ChromaDB)
- [x] Gmail read connector — `connectors/gmail.py` (send is blocked; requires confirmed UI action)
- [x] Hermes signal connectors (Strava, Spotify, Todoist, Apple Health) wired as agent tools
- [ ] Embedding-based entity deduplication across channels
- [ ] WhatsApp connector via official Business API
- [ ] Quantitative benchmark suite (30 tasks, 5 categories)
- [ ] Mobile-first UI (React Native or Flutter)
- [ ] On-device fine-tuning of commitment extractor on personal data

---

## References

1. Yao, S. et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models.* ICLR 2023.
2. Pan, S. et al. (2024). *Unifying Large Language Models and Knowledge Graphs: A Roadmap.* IEEE TKDE.
3. [Ollama](https://ollama.com) — local LLM inference
4. [LangGraph](https://langchain-ai.github.io/langgraph/) — agent orchestration
5. [Qwen2.5 Technical Report](https://arxiv.org/abs/2412.15115) — Alibaba Cloud, 2024
6. [spaCy](https://spacy.io) — industrial-strength NLP
7. [NetworkX](https://networkx.org) — graph analysis

---

## License

MIT License. See [LICENSE](LICENSE).

---

*IISc Bengaluru · AI Engineering & Deep Learning · 2026*
