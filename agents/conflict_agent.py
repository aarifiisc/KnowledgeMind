from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from graph.graph_store import (
    events_at_timeslot,
    get_timeslot_nodes,
    persons_at_timeslot,
)


@dataclass
class ConflictReport:
    time_slot: str              # TimeSlot node ID
    persons: list[str] = field(default_factory=list)   # Person node IDs
    events: list[str] = field(default_factory=list)    # Event node IDs
    message: str = ""           # Human-readable alert string


def scan() -> list[ConflictReport]:
    """
    Scan the shared knowledge graph for double-booking conflicts.

    A conflict is any TimeSlot node that has ≥ 2 distinct Person nodes
    connected to it via INVOLVES edges — meaning Alex has scheduled that
    slot with more than one person across any combination of conversations.

    Conflict detection is pure graph traversal (no LLM), so it runs in
    milliseconds and does not block the UI. It is called synchronously
    after each extraction cycle; threading is unnecessary at this scale.

    Returns:
        List of ConflictReport objects, one per conflicted TimeSlot.
        Also updates st.session_state['conflicts'] in place.
    """
    graph = st.session_state["graph"]
    reports: list[ConflictReport] = []

    for time_node in get_timeslot_nodes(graph):
        persons = persons_at_timeslot(time_node, graph)
        if len(persons) < 2:
            continue

        events = events_at_timeslot(time_node, graph)
        slot_label = graph.nodes[time_node].get("label", time_node)
        person_names = [graph.nodes[p].get("label", p) for p in persons]
        event_labels = [graph.nodes[e].get("label", e) for e in events]

        person_str = " and ".join(person_names)
        event_str = " / ".join(event_labels) if event_labels else "multiple events"
        message = (
            f"Conflict Detected: {person_str} are both scheduled "
            f"on {slot_label} ({event_str})"
        )

        reports.append(
            ConflictReport(
                time_slot=time_node,
                persons=persons,
                events=events,
                message=message,
            )
        )

    # Write alert strings into session state so the UI renders immediately
    # on the next rerun without needing to re-scan.
    st.session_state["conflicts"] = [r.message for r in reports]
    return reports
