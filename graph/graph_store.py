from __future__ import annotations

import streamlit as st
import networkx as nx

from utils.schema import EventEntity


# ── Node ID helpers ───────────────────────────────────────────────────────────

def _person_id(name: str) -> str:
    return f"person:{name.strip().lower()}"


def _slot_suffix(date_str: str, time_str: str) -> str:
    """Build the shared date-time suffix used in both time and event node IDs."""
    return f"{date_str}T{time_str}" if time_str != "TBD" else date_str


def _time_id(date_str: str, time_str: str) -> str:
    return f"time:{_slot_suffix(date_str, time_str)}"


def _event_id(activity: str, date_str: str, time_str: str) -> str:
    return f"event:{activity}:{_slot_suffix(date_str, time_str)}"


# ── Core CRUD ─────────────────────────────────────────────────────────────────

def add_event(entity: EventEntity, graph: nx.DiGraph) -> None:
    """
    Upsert Person, TimeSlot, and Event nodes and draw the three edge types.

    Node IDs follow the plan's naming convention:
      person:<name>                      (Person)
      time:<YYYY-MM-DD>T<HH:MM>         (TimeSlot)
      event:<activity>:<YYYY-MM-DD>T<HH:MM>  (Event)
    """
    pid = _person_id(entity.person)
    tid = _time_id(entity.date_str, entity.time_str)
    eid = _event_id(entity.activity, entity.date_str, entity.time_str)

    if not graph.has_node(pid):
        graph.add_node(pid, type="Person", label=entity.person.title())

    if not graph.has_node(tid):
        slot_label = (
            f"{entity.date_str} {entity.time_str}"
            if entity.time_str != "TBD"
            else entity.date_str
        )
        graph.add_node(tid, type="TimeSlot", label=slot_label)

    if not graph.has_node(eid):
        graph.add_node(eid, type="Event", label=entity.activity)

    # ATTENDS: Person → Event
    if not graph.has_edge(pid, eid):
        graph.add_edge(pid, eid, type="ATTENDS")

    # SCHEDULED_AT: Event → TimeSlot
    if not graph.has_edge(eid, tid):
        graph.add_edge(eid, tid, type="SCHEDULED_AT")

    # INVOLVES: Person → TimeSlot  (direct link; enables fast conflict detection)
    if not graph.has_edge(pid, tid):
        graph.add_edge(pid, tid, type="INVOLVES")


def remove_event(entity: EventEntity, graph: nx.DiGraph) -> None:
    """
    Drop the three edges for this entity, then prune any now-isolated
    Event or TimeSlot nodes. Person nodes are never auto-removed.
    """
    pid = _person_id(entity.person)
    tid = _time_id(entity.date_str, entity.time_str)
    eid = _event_id(entity.activity, entity.date_str, entity.time_str)

    for u, v in [(pid, eid), (eid, tid), (pid, tid)]:
        if graph.has_edge(u, v):
            graph.remove_edge(u, v)

    # Prune orphaned Event and TimeSlot nodes (not Person nodes)
    for node in (eid, tid):
        if graph.has_node(node) and graph.degree(node) == 0:
            graph.remove_node(node)


# ── Batch entry point called by extraction_agent ─────────────────────────────

def apply_entities(entities: list[EventEntity]) -> None:
    """
    Apply a list of extracted EventEntity objects to the shared knowledge graph
    stored in st.session_state['graph'].

    action == "add" | "update" → add_event()
    action == "remove"         → remove_event()
    """
    graph: nx.DiGraph = st.session_state["graph"]
    for entity in entities:
        if entity.action in ("add", "update"):
            add_event(entity, graph)
        elif entity.action == "remove":
            remove_event(entity, graph)


# ── Query helpers (used by conflict_agent in Phase 6) ────────────────────────

def get_timeslot_nodes(graph: nx.DiGraph) -> list[str]:
    """Return all TimeSlot node IDs in the graph."""
    return [n for n, d in graph.nodes(data=True) if d.get("type") == "TimeSlot"]


def persons_at_timeslot(time_node: str, graph: nx.DiGraph) -> list[str]:
    """Return all Person node IDs that have an INVOLVES edge to this TimeSlot."""
    return [
        u for u, v, d in graph.in_edges(time_node, data=True)
        if d.get("type") == "INVOLVES"
    ]


def events_at_timeslot(time_node: str, graph: nx.DiGraph) -> list[str]:
    """Return all Event node IDs that have a SCHEDULED_AT edge to this TimeSlot."""
    return [
        u for u, v, d in graph.in_edges(time_node, data=True)
        if d.get("type") == "SCHEDULED_AT"
    ]
