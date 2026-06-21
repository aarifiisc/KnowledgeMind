# DL Hybrid Agent Project — Implementation Plan

## Goal
Build a Streamlit personal-chat simulator where Alex holds three separate one-on-one DM conversations with Bob, Annie, and Cindy. An LLM-backed extraction agent converts scheduling dialogue from all conversations into a single live NetworkX knowledge graph, and a conflict-detection agent flags calendar overlaps across conversations in real time.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        Streamlit App                         │
│  ┌─────────────────────┐   ┌───────────────────────────────┐ │
│  │    Chat Panel (L)   │   │  Graph + Alert Panel (R)      │ │
│  │  - Message thread   │   │  - NetworkX → pyvis render    │ │
│  │  - Persona selector │   │  - Conflict alert sidebar     │ │
│  │  - CURRENT_DATE tag │   │                               │ │
│  └─────────────────────┘   └───────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
         │                             ▲
         ▼                             │
┌─────────────────┐         ┌──────────────────────┐
│  Persona Agent  │         │   Graph Store        │
│  (LangChain)    │         │  st.session_state    │
│  Bob/Annie/     │         │  NetworkX DiGraph    │
│  Cindy LLM      │         └──────────────────────┘
└─────────────────┘                   ▲
         │                            │
         ▼                            │
┌─────────────────────────────────────────────────┐
│          Graph Extraction Agent                 │
│  Gemma (google/gemma-4-E2B-it) via HuggingFace  │
│  Strict JSON schema → {person, activity,        │
│  date_str, time_str, action}                    │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│         Conflict Detection Agent                │
│  Async scan of graph topology                   │
│  Detects time-node with degree > 1              │
│  Emits conflict payload → st.session_state      │
└─────────────────────────────────────────────────┘
```

**Single source of truth:** `st.session_state["graph"]` — a `nx.DiGraph` object shared across all three conversation threads. `st.session_state["conversations"]` holds a separate message list per persona.

---

## Project Structure

```
DL_Project/
├── app.py                  # Streamlit entry point
├── agents/
│   ├── persona_agent.py    # LangChain chains for Bob, Annie, Cindy
│   ├── extraction_agent.py # Gemma-backed entity extractor
│   └── conflict_agent.py   # Graph topology conflict scanner
├── graph/
│   ├── graph_store.py      # CRUD helpers for the NetworkX graph
│   └── visualizer.py       # pyvis/matplotlib renderer → HTML component
├── utils/
│   ├── date_resolver.py    # Relative-date anchoring ("tomorrow", "next Monday")
│   └── schema.py           # Pydantic model for extracted entities
├── config.py               # Model paths, persona prompts, constants
├── requirements.txt
├── spec.md
└── plan.md
```

---

## Implementation Phases

### Phase 1 — Project Scaffold & Config
**Goal:** Runnable skeleton with no logic.

- [ ] Create the directory structure above.
- [ ] `requirements.txt`: `streamlit`, `networkx`, `pyvis`, `langchain`, `langgraph`, `transformers`, `torch`, `pydantic`, `matplotlib`.
- [ ] `config.py`: define `CURRENT_DATE` (simulated, user-adjustable), model ID `google/gemma-4-E2B-it`, persona system prompts.

**Persona tone definitions:**
| Persona | Tone |
|---------|------|
| Bob     | Short, informal sentences. Minimal punctuation. |
| Annie   | Formal, full sentences, professional. |
| Cindy   | Casual, uses emoji and contractions. |

---

### Phase 2 — Streamlit Layout
**Goal:** Two-panel UI with per-conversation state wiring; no AI yet.

- [ ] `app.py`: Two-column layout — `col_chat` (left, 55%) and `col_graph` (right, 45%).
- [ ] `col_chat`: Conversation switcher using `st.tabs(["Bob", "Annie", "Cindy"])`. Inside each tab, render that persona's message history as styled DM bubbles — Alex's messages right-aligned, persona's messages left-aligned. Include a `CURRENT_DATE` badge in the panel header. Add a text input + Send button per tab.
- [ ] `col_graph`: Placeholder for the unified graph HTML component and a conflict alert box (`st.warning`).
- [ ] Initialize `st.session_state`: `conversations = {"Bob": [], "Annie": [], "Cindy": []}`, `graph = nx.DiGraph()`, `conflicts = []`.

---

### Phase 3 — Persona Agent
**Goal:** Alex's message in a conversation tab triggers a contextually appropriate reply from that tab's persona.

- [ ] `agents/persona_agent.py`: Build a LangChain `ChatPromptTemplate` per persona using system prompts from `config.py`. Pass the last N messages from **that persona's conversation only** as context (rolling window, default 10).
- [ ] Load Gemma via `transformers` pipeline (or `langchain_community.llms.HuggingFacePipeline`).
- [ ] Return the persona's reply as a string; append both Alex's message and the persona reply to `st.session_state["conversations"][persona]`.
- [ ] No Auto mode needed — the active tab determines which persona replies.

---

### Phase 4 — Graph Extraction Agent
**Goal:** Parse each new message pair and update the knowledge graph.

- [ ] `utils/schema.py`: Pydantic model `EventEntity`:
  ```python
  class EventEntity(BaseModel):
      person: str
      activity: str
      date_str: str        # normalized absolute date (YYYY-MM-DD)
      time_str: str        # HH:MM 24h
      action: Literal["add", "remove", "update"]
  ```
- [ ] `utils/date_resolver.py`: Convert relative expressions ("tomorrow", "next Friday", "this Monday") to absolute dates using `CURRENT_DATE` as the anchor. Use `dateutil` or manual delta logic.
- [ ] `agents/extraction_agent.py`:
  - Craft a few-shot prompt instructing Gemma to output **only** a JSON array of `EventEntity` objects.
  - On LLM output: parse with `json.loads`, validate with Pydantic, discard invalid entries.
  - Call `graph_store.apply_entities(entities)` to mutate the graph.
- [ ] Run extraction after every new message (not just persona replies) to capture Alex's own scheduling intent. The extractor always knows which persona's conversation the message came from, so `person` in the entity can be inferred from context.

---

### Phase 5 — Graph Store & Node Schema
**Goal:** Deterministic, queryable graph state.

- [ ] `graph/graph_store.py`:
  - **Node types:** `Person`, `Event` (activity label), `TimeSlot` (YYYY-MM-DD HH:MM).
  - **Edge types:** `ATTENDS`, `SCHEDULED_AT`, `INVOLVES`.
  - `add_event(entity)`: upsert `Person` node, `TimeSlot` node, `Event` node; draw edges.
  - `remove_event(entity)`: find matching edges/nodes and drop them.
  - `update_event(old, new)`: call `remove_event(old)` then `add_event(new)`.
  - All mutations operate on `st.session_state["graph"]` directly — the single graph is shared across all three conversations.

**Node naming convention:**
- Person node id: `person:<name>` (lowercase)
- TimeSlot node id: `time:<YYYY-MM-DD>T<HH:MM>`
- Event node id: `event:<activity_slug>:<YYYY-MM-DD>T<HH:MM>`

---

### Phase 6 — Conflict Detection Agent
**Goal:** Flag double-bookings without blocking the UI.

- [ ] `agents/conflict_agent.py`:
  - Iterate all `TimeSlot` nodes in the graph.
  - For each `TimeSlot`, collect all `Person` nodes reachable via `ATTENDS` edges.
  - If a `TimeSlot` has ≥ 2 distinct `Person` nodes connected to it, it is a conflict.
  - Also check `Person` nodes: if a single person is connected to ≥ 2 `TimeSlot` nodes at the same time, flag it.
  - Return list of `ConflictReport(time_slot, persons, events)`.
- [ ] Store results in `st.session_state["conflicts"]`.
- [ ] Invoke via `st.fragment` or `threading` to avoid blocking keystrokes. If using threads, use a mutex around graph reads.

---

### Phase 7 — Graph Visualization
**Goal:** Live-rendered graph in the right panel.

- [ ] `graph/visualizer.py`: Convert `nx.DiGraph` → `pyvis.network.Network`. Color-code node types:
  - Person nodes: blue
  - Event nodes: green
  - TimeSlot nodes: orange
- [ ] Export to an HTML string, render with `st.components.v1.html(html, height=500)`.
- [ ] Re-render on every Streamlit rerun (after each message submission).
- [ ] Highlight conflict nodes in red when `st.session_state["conflicts"]` is non-empty.

---

### Phase 8 — Conflict Alert UI
**Goal:** Surface warnings immediately after detection.

- [ ] In `col_graph`, below the graph: iterate `st.session_state["conflicts"]` and render each as `st.warning(f"Conflict Detected: {persons} double-booked on {time_slot}")`.
- [ ] Clear `st.session_state["conflicts"]` at the start of each rerun before re-running detection so stale alerts don't persist.

---

### Phase 9 — Edge Cases & Hardening
**Goal:** Handle relative dates and rescheduling correctly.

- [ ] **Relative date anchoring:** Ensure `date_resolver.py` covers: "today", "tomorrow", "this [weekday]", "next [weekday]", "in N days/hours".
- [ ] **Rescheduling detection:** If extraction returns `action: "update"`, the prompt must include the old date/time. Extract both old and new from context window before updating the graph.
- [ ] **Duplicate suppression:** Before adding a node/edge, check existence to prevent duplicate entries.
- [ ] **Graceful LLM failures:** If Gemma returns malformed JSON, log the raw output and skip graph update without crashing the app.

---

### Phase 10 — Verification & Acceptance Testing
**Goal:** Validate against spec acceptance criteria.

- [ ] **Critical Path 1 — Persona tone test:** Open each of the three conversation tabs and exchange a 5-turn dialogue. Assert each persona maintains its unique tone (manual review).
- [ ] **Critical Path 2 — Extraction pipeline test:** Feed 10 messages spread across multiple conversation tabs with complex/relative dates into the extraction agent standalone. Assert all 10 produce valid `EventEntity` JSON with correct absolute dates.
- [ ] **Conflict detection test:** Script the Annie-coffee / Bob-sync double-booking scenario across two separate conversation tabs. Assert `st.session_state["conflicts"]` is non-empty after the second message.
- [ ] **Conversation isolation test:** Verify that switching tabs preserves each thread's full independent message history.
- [ ] **Graph update speed test:** Measure time from message submit to graph rerender; assert < 1 second for the graph update step (excluding LLM inference time).

---

## Dependency Order

```
    → Phase 1 (scaffold)
    → Phase 2 (UI layout)
    → Phase 3 (persona agent)    ← depends on config + layout
    → Phase 4 (extraction agent) ← depends on schema + date resolver
    → Phase 5 (graph store)      ← depends on extraction schema
    → Phase 6 (conflict agent)   ← depends on graph store
    → Phase 7 (visualization)    ← depends on graph store
    → Phase 8 (alert UI)         ← depends on conflict agent + layout
    → Phase 9 (edge cases)       ← hardening pass across all phases
    → Phase 10 (tests)           ← end-to-end validation
```

---

## Key Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Gemma inference too slow for < 1s graph update | Run extraction async / in a background thread; update graph state separately from LLM response |
| Malformed JSON from LLM | Strict few-shot examples + Pydantic validation with fallback to no-op |
| Relative date ambiguity | Anchor all resolution to explicit `CURRENT_DATE` in session state; surface it in UI header |
| Thread safety on shared graph state | Use `threading.Lock` around all `st.session_state["graph"]` reads/writes |
| pyvis rendering flicker | Cache rendered HTML keyed on graph hash; only regenerate on structural change |
