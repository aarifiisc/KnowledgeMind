## Overview & Outcomes

**Vision:**
- Build a simulated personal chat application where an AI orchestrates individual one-on-one conversations between a user (Alex) and three distinct virtual personalities (Bob, Annie, Cindy) — each in a separate DM-style thread.
- The system dynamically translates casual scheduling dialogue into a mathematical graph network to proactively resolve calendar conflicts across all conversations.

## Success Metrics:
- 100% precision in extracting event entities (Date, Time, Person, Activity) from chat strings.
- Graph nodes and edges update deterministically within 1 second of text submission.
- The reasoning agent flags 100% of overlapping time frames or double-bookings, even when the conflicting commitments originate from different conversations.

## Scope & Features

**In-Scope:**
- Streamlit Chat Interface: A cohesive UI with a conversation switcher that lets Alex move between three separate one-on-one threads (Alex ↔ Bob, Alex ↔ Annie, Alex ↔ Cindy).
- Each conversation thread maintains its own independent message history. Alex always appears on the right; the active persona always appears on the left.
- Graph Extraction Agent: An LLM-backed utility that parses every new message across all conversations for planned commitments and maps them to a shared NetworkX graph.
- Visual Knowledge Graph: A live-rendered network visualization displaying nodes (People, Events, Times) and their structural relationships, unified across all conversations.
- Asynchronous Reasoning Agent: A background processor that scans the unified network topology for temporal overlaps or conflicting geographic locations, regardless of which conversation the commitments came from.

**Out-of-Scope:**
- Persistent calendar synchronization with external production providers (e.g., Google Calendar API, Microsoft Outlook).
- Multi-user production deployment over standard user auth protocols.
- Voice-to-text or localized native push notifications.

## User Scenarios & Behavior

**User Stories:**
- As Alex, I want to open my conversation with Annie and propose lunch tomorrow at 1:00 PM, then switch to my conversation with Bob and propose a meeting at the same time, so that the system warns me of the overlap before I finalize plans.
- As Alex, I want to look at a visual graph diagram so that I can clearly see which person is tied to which calendar commitment across all my conversations.

**User Flows:**

- *Adding an Event:* Alex opens the Annie conversation tab and types: "Let's grab coffee Friday at 3 PM." → Message posts to Annie's thread → Graph Builder Agent extracts variables → NetworkX graph draws new nodes: [Annie], [Coffee], [Friday 3:00 PM] → Graph visualizer redraws.

- *Conflict Detection:* Alex switches to the Bob conversation tab and types: "Let's do a sync this Friday at 3 PM." → Message posts to Bob's thread → Graph updates → Reasoning agent discovers that Friday 3:00 PM has connections to two distinct event blocks (one from Annie's conversation, one from Bob's) → Streamlit alert panel flashes an amber warning: "Conflict Detected: Double-booked with Annie and Bob on Friday at 3:00 PM!"

## Constraints & Dependencies

**Tech Stack:**
- Frontend & Layout: Streamlit for chat layouts and component state.
- Graph Engine: NetworkX for programmatic graph generation.
- Visualization: matplotlib or pyvis for interactive node manipulation.
- Agent Orchestration: LangChain or LangGraph to coordinate memory across personas and the background extractor.
- Core LLM: Local Gemma **(google/gemma-4-E2B-it)** for entity extraction and persona responses.

**Enterprise/Design Constraints:**
- The single-page layout must stay strictly divided into a Chat Panel (left) and a Knowledge Graph/Alert Panel (right).
- The left panel shows one conversation at a time; a conversation switcher (tabs or sidebar list) lets Alex navigate between the three threads.
- The execution of the conflict agent must not block user keystrokes or UI interactions.

## Technical Decisions & Architecture Principles:

**Single-Source-of-Truth Graph:**
- The Streamlit session state stores a single master NetworkX object shared across all conversations.
- The UI elements and reasoning agents rely entirely on this model.

**Per-Conversation Message Store:**
- `st.session_state["conversations"]` is a dict: `{"Bob": [...], "Annie": [...], "Cindy": [...]}`.
- Each persona agent receives only its own conversation history as context.
- The extraction agent processes messages from all conversations into the unified graph.

**Deterministic Schema Extraction:**
- The entity extractor enforces a strict JSON validation schema to prevent format variances.

**Architecture & Edge Cases:**
- Edge Case (Relative Time Mapping): Expressions like "tomorrow" or "next Monday" require anchoring against a fixed reference date token. The application will track a simulated CURRENT_DATE field in the UI header.
- Edge Case (Rescheduling): If Alex says "Let's move our Tuesday meeting to Wednesday," the graph agent must drop the old relationship edges before painting the new coordinates.

## Verification & Acceptance Criteria Tests:

**Critical Path 1:**
- Open each of the three conversation tabs and exchange a multi-turn dialogue. Verify that each persona maintains its unique communication tone (Annie is formal, Bob uses short sentences, Cindy is casual).

**Critical Path 2:**
- Feed a 10-message conversational string spread across multiple conversation tabs containing complex dates to verify the extraction performance of the underlying pipeline.

**Acceptance Criteria:**
- The chat interface renders three distinct conversation threads; Alex's messages are visually right-aligned and persona messages are left-aligned in each thread.
- Switching between conversation tabs preserves each thread's full message history.
- The application adds nodes and edges to the visual graph window automatically when scheduling text is sent in any conversation.
- The evaluation script lists a conflict warning immediately whenever an overlap event occurs across any two conversations.
