"""
api/simchat_routes.py
---------------------
FastAPI router for the SimChat feature (spec.md).

Session state is module-level (single-user demo). A dedicated in-memory SQLite
DB and per-thread message histories live for the lifetime of the FastAPI process
and are cleared via POST /api/simchat/reset or on server restart.

Endpoints:
  POST /api/simchat/message              — send a message, get reply + graph + conflicts
  GET  /api/simchat/history/{convo_id}   — full thread history
  GET  /api/simchat/graph                — current graph as JSON
  GET  /api/simchat/conflicts            — all detected conflicts
  POST /api/simchat/reset                — wipe session state
"""

from __future__ import annotations

import sqlite3

import networkx as nx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kg.graph import build_graph
from kg.schema import SCHEMA_SQL, ConflictEdge
from simchat.extractor import extract_and_update
from simchat.personas import PERSONAS

router = APIRouter(prefix="/api/simchat")

_BUSY_TIMEOUT_MS = 3000

# ---------------------------------------------------------------------------
# Session state (single user)
# ---------------------------------------------------------------------------

def _new_state() -> dict:
    """Create a fresh in-memory SQLite KG + empty per-thread histories."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return {
        "conn": conn,
        "histories": {"bob": [], "annie": [], "cindy": []},
    }


_state: dict = _new_state()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conflict_to_dict(row) -> dict:
    return {
        "a_text": row["a_raw"] or row["a_desc"],
        "a_source": row["a_source"],
        "b_text": row["b_raw"] or row["b_desc"],
        "b_source": row["b_source"],
        "overlap_minutes": row["overlap_minutes"],
    }


def _all_conflicts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT cf.overlap_minutes,
                  ca.description AS a_desc, ca.raw_text AS a_raw, ca.source AS a_source,
                  cb.description AS b_desc, cb.raw_text AS b_raw, cb.source AS b_source
           FROM conflicts cf
           JOIN commitments ca ON cf.commitment_a_id = ca.id
           JOIN commitments cb ON cf.commitment_b_id = cb.id
           ORDER BY cf.detected_at"""
    ).fetchall()
    return [_conflict_to_dict(r) for r in rows]


def _graph_to_json(graph: nx.DiGraph) -> dict:
    nodes = [{"id": n, **dict(attrs)} for n, attrs in graph.nodes(data=True)]
    edges = [{"source": u, "target": v, **dict(data)} for u, v, data in graph.edges(data=True)]
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SimChatMessage(BaseModel):
    conversation_id: str    # "bob" | "annie" | "cindy"
    text: str
    current_date: str = "2026-06-23"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/message")
def send_message(inp: SimChatMessage) -> dict:
    cid = inp.conversation_id.strip().lower()
    if cid not in PERSONAS:
        raise HTTPException(status_code=400, detail=f"Unknown conversation_id: {cid!r}")

    persona = PERSONAS[cid]
    history = _state["histories"][cid]
    conn: sqlite3.Connection = _state["conn"]

    # 1. Generate persona reply using only this thread's history.
    persona_reply = persona.respond(history, inp.text, inp.current_date)

    # 2. Persist the exchange in the in-memory history.
    history.append((inp.text, persona_reply))

    # 3. Extract commitments from both the user message and the persona reply.
    extract_and_update(inp.text, "You", cid, inp.current_date, conn)
    extract_and_update(persona_reply, persona.name, cid, inp.current_date, conn)

    # 4. Return the updated graph and the full conflict list.
    graph = build_graph(conn)
    return {
        "persona_reply": persona_reply,
        "graph": _graph_to_json(graph),
        "conflicts": _all_conflicts(conn),
    }


@router.get("/history/{conversation_id}")
def get_history(conversation_id: str) -> dict:
    cid = conversation_id.strip().lower()
    if cid not in _state["histories"]:
        raise HTTPException(status_code=404, detail=f"Unknown conversation_id: {cid!r}")
    messages = []
    for user_text, persona_text in _state["histories"][cid]:
        messages.append({"role": "user", "text": user_text})
        if persona_text is not None:
            messages.append({"role": "persona", "text": persona_text})
    return {"messages": messages}


@router.get("/graph")
def get_graph() -> dict:
    graph = build_graph(_state["conn"])
    return _graph_to_json(graph)


@router.get("/conflicts")
def get_conflicts() -> dict:
    return {"conflicts": _all_conflicts(_state["conn"])}


@router.post("/reset")
def reset_session() -> dict:
    global _state
    try:
        _state["conn"].close()
    except Exception:  # noqa: BLE001
        pass
    _state = _new_state()
    return {"ok": True}
