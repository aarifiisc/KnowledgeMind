# SPEC: Team Management Chatbot

## Problem Statement

Project teams lose alignment over time. Discussions drift, features creep in, and sprint plans diverge from the original Statement of Work. This system gives the team a persistent, AI-driven advisor that was "present at the SoW" and can flag drift in real time.

---

## Core Flows

### 1. Project Initialization

```
User uploads SoW (PDF or text)
  → LLM extracts entities, relationships, goals, constraints
  → Knowledge Graph is built and persisted
  → LLM generates DRL rules from scope boundaries and constraints
  → DRL rules are stored and rendered in the UI
```

### 2. Team Chat Session

```
Team member sends a message (feature idea, sprint plan, discussion note)
  → Message is attributed to the sender (name/handle)
  → Tags are applied — manually inline (#tag) or AI-suggested and confirmed
  → Chat handler embeds the message
  → Origin Plane KG is queried for semantically relevant nodes
  → DRL rules are evaluated against the message content
  → LLM produces:
      - Alignment score (0–100)
      - List of in-scope / out-of-scope components detected
      - Deviation flags (which rules are violated or at risk)
      - Coverage delta (which SoW goals this message addresses)
      - Architecture recommendations
      - Extracted User Plane entities (topics, decisions, work items) with
        proposed cross-plane links to Origin Plane nodes
  → User Plane KG is updated with extracted entities and cross-plane edges
  → Response is streamed to the chat UI
```

### 3. Viewers

- **KG Viewer**: Interactive dual-plane graph. Origin Plane nodes (SoW-derived) and User Plane nodes (conversation-derived) are visually distinct. Cross-plane edges show how discussions trace to project goals. Plane toggle lets users isolate or overlay both planes. Clickable nodes show details and source (SoW excerpt or chat message).
- **DRL Viewer**: Rendered list of business rules. Each rule shows: condition, action, source excerpt from SoW, and current violation status.

---

## Knowledge Graph Planes

The KG is split into two distinct planes that coexist in the same graph store and are rendered together in the viewer.

### Origin Plane

- **Source**: SoW document only
- **Mutability**: Effectively read-only after initialization. Coverage status on nodes is the only field that updates.
- **Node types**: `goal`, `feature`, `component`, `constraint`, `actor`, `milestone`
- **Edge types**: `depends_on`, `implements`, `constrains`, `owned_by`, `delivers`
- **Role**: Ground truth of project scope. Everything is measured against this plane.

### User Plane

- **Source**: Team chat messages (incrementally built as the project evolves)
- **Mutability**: Append-only; new nodes and edges are added per message, never deleted
- **Node types**: `decision`, `work_item`, `proposed_feature`, `concern`, `discussion_topic`, `blocker`
- **Edge types (intra-plane)**: `relates_to`, `blocks`, `leads_to`, `supersedes`
- **Role**: Living record of what the team has actually discussed and decided

### Cross-Plane Edges

Edges that connect the User Plane to the Origin Plane. These are the primary mechanism for alignment scoring and coverage tracking.

| Relation | Direction | Meaning |
|---|---|---|
| `addresses` | User → Origin goal | Discussion topic / decision works toward this goal |
| `implements` | User proposed_feature → Origin feature | Proposed feature elaborates an SoW feature |
| `violates` | User decision → Origin constraint | Decision contradicts a constraint |
| `extends` | User work_item → Origin component | Work item lives under this component |
| `out_of_scope` | User → (no Origin node) | No traceable link to any Origin Plane node |

**Coverage** = fraction of Origin Plane goal nodes that have at least one incoming `addresses` cross-plane edge.  
**Deviation** = User Plane nodes with no outgoing cross-plane edge of any type.

### Plane Identifiers on Nodes and Edges

Every node and edge carries a `plane` field: `"origin"` or `"user"`. Cross-plane edges carry `plane: "cross"`.

---

## Chat Tagging

Messages carry tags that serve two purposes: surfacing information in the chat UI and driving User Plane KG extraction.

### Tag Types

| Tag | Meaning | User Plane node type created |
|---|---|---|
| `#decision` | The team has locked a choice | `decision` |
| `#feature` | A new feature is being proposed or discussed | `proposed_feature` |
| `#concern` | A risk, question, or worry about the project | `concern` |
| `#sprint` | Sprint planning content | `work_item` |
| `#architecture` | Architecture-level discussion | `discussion_topic` |
| `#blocker` | Something blocking progress | `blocker` |
| `#out-of-scope` | Explicit acknowledgment that a topic is out of scope | — (triggers deviation flag) |

### Tagging Mechanics

- **Inline manual**: team member types `#tag` anywhere in the message
- **AI-suggested**: the assistant reads the message and proposes tags as part of its response; the sender can confirm or dismiss before the message is committed to history
- A single message can carry multiple tags
- Tags are indexed and filterable in the chat history

---

## Technology Choices

| Concern | Choice | Rationale |
|---|---|---|
| LLM | Claude (Anthropic SDK) | Best reasoning quality for structured extraction and alignment tasks |
| Backend | FastAPI (Python) | Simple, async, auto-docs |
| KG Store | NetworkX in-memory + JSON persistence | No infra, sufficient for project-scale graphs |
| KG Visualization | Cytoscape.js | Standalone JS, rich graph layout, no build step needed |
| DRL (rules) | Custom JSON-based rule objects, rendered as pseudo-DRL | True Drools requires JVM; JSON rules evaluated in Python are equivalent for this scale |
| Embeddings | `sentence-transformers` (local) or Claude embeddings | For KG node similarity queries |
| Frontend | Single HTML + vanilla JS (no build step) | Standalone, simple, no toolchain friction |
| Persistence | JSON files under `data/projects/{project_id}/` | No DB needed at this scale |

### Note on DRL

True Drools Rule Language (DRL) targets a JVM rules engine (Drools/Kogito). For this project:
- Rules are authored in a structured JSON format that mirrors DRL semantics (when/then, salience, agenda-group)
- The UI renders them in DRL-like syntax for readability
- Evaluation is done in Python using the same when/then logic
- If the project requires actual Drools integration, a thin Java sidecar can be added later

---

## Data Models

### Project

```json
{
  "project_id": "uuid",
  "name": "string",
  "sow_text": "string",
  "created_at": "iso8601",
  "kg": {
    "nodes": [],
    "edges": []
  },
  "rules": [],
  "members": []
}
```

### Team Member

```json
{
  "member_id": "uuid",
  "handle": "string",
  "display_name": "string"
}
```

### KG Node

```json
{
  "id": "string",
  "label": "string",
  "plane": "origin | user",
  "type": "goal | feature | component | constraint | actor | milestone | decision | work_item | proposed_feature | concern | discussion_topic | blocker",
  "description": "string",
  "source": {
    "type": "sow | chat_message",
    "ref": "sow_excerpt string | message_id"
  },
  "coverage_status": "unaddressed | partial | covered"
}
```

### KG Edge

```json
{
  "id": "string",
  "source": "node_id",
  "target": "node_id",
  "plane": "origin | user | cross",
  "relation": "depends_on | implements | constrains | owned_by | delivers | relates_to | blocks | leads_to | supersedes | addresses | violates | extends | out_of_scope"
}
```

### Rule (pseudo-DRL)

```json
{
  "rule_id": "string",
  "name": "string",
  "salience": 10,
  "when": "string (natural language condition)",
  "then": "string (natural language action / flag)",
  "sow_excerpt": "string",
  "violation_status": "ok | at_risk | violated"
}
```

### Chat Message

```json
{
  "message_id": "uuid",
  "role": "user | assistant",
  "author": {
    "member_id": "uuid",
    "handle": "string"
  },
  "content": "string",
  "tags": ["#decision", "#feature"],
  "timestamp": "iso8601",
  "metadata": {
    "alignment_score": 0,
    "in_scope": [],
    "out_of_scope": [],
    "deviations": [],
    "coverage_delta": [],
    "recommendations": [],
    "suggested_tags": [],
    "user_plane_nodes_created": [],
    "cross_plane_edges_created": []
  }
}
```

---

## API Endpoints

```
# Project
POST /projects                              # Create project (upload SoW text)
GET  /projects/{id}                         # Get project metadata

# Knowledge Graph
GET  /projects/{id}/kg                      # Full KG (both planes + cross edges)
GET  /projects/{id}/kg?plane=origin         # Origin Plane only
GET  /projects/{id}/kg?plane=user           # User Plane only
GET  /projects/{id}/kg/coverage             # Coverage summary (Origin goals vs. addressed)

# Rules
GET  /projects/{id}/rules                   # All DRL rules with current violation status

# Team Members
POST /projects/{id}/members                 # Add a team member
GET  /projects/{id}/members                 # List team members

# Chat
POST /projects/{id}/chat                    # Send message (with author + optional tags)
GET  /projects/{id}/chat/history            # Full chat history
GET  /projects/{id}/chat/history?tag=       # Filter history by tag
GET  /projects/{id}/chat/history?author=    # Filter history by member handle
PATCH /projects/{id}/chat/{msg_id}/tags     # Update tags on a message (confirm AI suggestions)
```

---

## UI Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  [Project Name]                 [Origin] [User] [Both]  [New Project]│
├───────────────────┬────────────────────────────┬─────────────────────┤
│  KNOWLEDGE GRAPH  │  CHAT                       │  RULES (DRL)        │
│                   │                             │                     │
│  [plane toggle]   │  [tag filter: all ▼]        │  rule 1 ✓           │
│                   │  [author filter: all ▼]     │  rule 2 ⚠           │
│  Origin nodes     │                             │  rule 3 ✗           │
│  ● goal           │  @alice [#decision]         │                     │
│  ■ feature        │    "We're locking auth to   │  Coverage: 42%      │
│  ▲ constraint     │     OAuth2 only"            │                     │
│                   │    [score: 88] [addresses:  │  ── Deviations ──   │
│  ─ ─ ─ ─ ─ ─ ─   │     goal:auth-security]     │  2 messages out     │
│                   │                             │  of scope           │
│  User nodes       │  assistant                  │                     │
│  ◆ decision       │    "Aligned. This addresses │                     │
│  ◇ work_item      │     goal #auth-security.    │                     │
│  ◈ concern        │     Suggested tags: ..."    │                     │
│                   │                             │                     │
│                   │  [@handle] [message...    ] │                     │
│                   │  [#tag picker]   [Send]     │                     │
└───────────────────┴────────────────────────────┴─────────────────────┘
```

- **Left panel — KG Viewer**: Cytoscape.js dual-plane graph. Origin Plane nodes use solid shapes; User Plane nodes use hollow/outlined shapes. Cross-plane edges are dashed. Plane toggle in toolbar isolates or overlays planes. Clicking a node shows its source (SoW excerpt or linked chat message).
- **Center panel — Chat**: Multi-author chat. Each user message shows `@handle` and tag chips. Assistant messages show alignment score badge and the Origin Plane nodes addressed. Tag picker below the input lets users apply or confirm suggested tags before sending.
- **Right panel — Rules/DRL Viewer**: Rules list with live violation status. Coverage percentage and a deviation count summary at the bottom.

---

## LLM Prompt Strategy

### SoW Extraction Prompt

Extract from the SoW:
1. Goals (what success looks like)
2. Features / deliverables
3. Components / subsystems
4. Constraints (budget, timeline, tech, regulatory)
5. Actors / stakeholders
6. Milestones

Return structured JSON matching the KG node/edge schema.

### DRL Rule Generation Prompt

From the SoW and extracted KG, generate rules of the form:
- "When a feature is proposed that is not linked to any goal node, flag as out-of-scope"
- "When a timeline is mentioned that exceeds milestone X, raise a deviation"

### User Plane Extraction Prompt

Given a tagged team chat message and the current Origin Plane KG:
- Extract entities from the message as User Plane nodes (type guided by tags: `#decision` → `decision`, `#feature` → `proposed_feature`, etc.)
- For each extracted node, propose cross-plane edges to Origin Plane nodes
- If no cross-plane edge can be drawn, mark the node as `out_of_scope`
- Return new nodes and edges as structured JSON matching the KG schema

### Tag Suggestion Prompt

Given a message before it is sent:
- Infer which tags from the defined set best describe the content
- Return suggested tags with a brief rationale for each
- Do not invent tags outside the defined set

### Alignment Scoring Prompt

Given the Origin Plane KG, User Plane KG, active rules, and the current message:
- Identify which Origin Plane nodes are referenced (directly or semantically)
- Check each rule's `when` condition against the message
- Produce alignment score, in/out-of-scope lists, deviation flags, coverage delta (new Origin nodes now addressed), and architecture recommendations

---

## Open Questions

1. Should the chatbot maintain a conversation history that influences future alignment scores (session memory)?
2. Should KG nodes be updated dynamically as the project progresses (e.g., mark a goal as "covered" when chat confirms it)?
3. Multi-project support in v1, or single active project?
4. Authentication needed, or single-user local tool?
5. Should recommendations be prescriptive (specific architecture patterns) or descriptive (observations only)?
6. Should AI-suggested tags be auto-applied (optimistic) and editable after, or require explicit confirmation before the message is committed?
7. Should User Plane nodes be created per-message (fine-grained) or merged/deduplicated across messages (coarser, cleaner graph)?
8. Should cross-plane edges be proposed by the LLM and always accepted, or should users be able to reject/override a proposed link?
9. In the KG Viewer, should cross-plane edges be always visible or only shown when a node is selected (to reduce visual clutter)?
