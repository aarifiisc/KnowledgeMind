"""
simchat/extractor.py
--------------------
Graph Extraction Agent for the SimChat application.

extract_and_update() is called after every message send. It:
  1. Runs spaCy NER for (person, time_expression) hints.
  2. Calls the commitment extractor (Ollama -> Groq fallback).
  3. Inserts extracted CommitmentNodes into the shared SQLite KG.
  4. Runs person-agnostic conflict detection against all existing commitments.
  5. Returns any newly detected ConflictEdges for the alert panel.

The function is synchronous. On typical short chat messages the extraction
pipeline (NER + LLM call + SQLite write) completes well under 1 second when
using the Groq fast model, satisfying the spec's < 1 s graph-update target.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from typing import Optional

from connectors.base import RawMessage
from extraction.commitment import LlmCaller, extract_commitments
from extraction.ner import extract_entities
from kg.graph import detect_new_conflicts, insert_commitment
from kg.schema import ConflictEdge


def _message_id(conversation_id: str, text: str, base_ts: float) -> str:
    """Deterministic dedup key derived from the message's three natural keys."""
    raw = f"{conversation_id}|{text}|{base_ts:.0f}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _date_to_base_ts(current_date: str) -> float:
    """
    Parse 'YYYY-MM-DD' to an epoch float at midnight local time.

    This timestamp is used as the anchor for timeparse, so relative expressions
    like 'tomorrow' and 'next Friday' resolve against the simulated date rather
    than wall-clock time. Falls back to time.time() for unparseable strings.
    """
    import time as _time
    try:
        return datetime.fromisoformat(current_date).timestamp()
    except (ValueError, TypeError):
        return _time.time()


def extract_and_update(
    message_text: str,
    sender: str,
    conversation_id: str,
    current_date: str,
    conn: sqlite3.Connection,
    llm_caller: Optional[LlmCaller] = None,
) -> list[ConflictEdge]:
    """
    Parse a single message, update the knowledge graph, return new conflicts.

    Args:
        message_text:    Raw text of the message (Alex's words or a persona reply).
        sender:          Display name of the author ('Alex', 'Bob', 'Annie', 'Cindy').
        conversation_id: Thread label — 'bob', 'annie', or 'cindy'.
        current_date:    Simulated date string 'YYYY-MM-DD' for time anchoring.
        conn:            Open SQLite connection to the shared in-session KG.
        llm_caller:      Override for the commitment extractor's LLM call.
                         Defaults to the Ollama → Groq fallback defined in
                         extraction/commitment.py. Pass a stub in tests.
    Returns:
        List of ConflictEdge objects newly detected by this message. Empty when
        no commitment was extracted or no temporal overlaps exist.
    """
    base_ts = _date_to_base_ts(current_date)
    ext_id = _message_id(conversation_id, message_text, base_ts)

    raw_message = RawMessage(
        source=conversation_id,
        channel_id=conversation_id,
        sender=sender,
        text=message_text,
        timestamp=base_ts,
        external_id=ext_id,
    )

    ner_candidates = extract_entities(message_text)
    result = extract_commitments(raw_message, ner_candidates, llm_caller=llm_caller)

    if result is None or not result.commitments:
        return []

    new_conflicts: list[ConflictEdge] = []
    for commitment in result.commitments:
        commitment_id = insert_commitment(
            conn, commitment, external_id=ext_id, channel_id=conversation_id
        )
        conflicts = detect_new_conflicts(conn, commitment_id)
        new_conflicts.extend(conflicts)

    return new_conflicts


# ---------------------------------------------------------------------------
# Smoke test (no Ollama / Groq needed — stub LLM caller)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    from kg.schema import init_db

    def _stub_hard(_s: str, _u: str) -> str:
        return (
            '{"is_commitment": true, "confidence": 0.92, '
            '"time_expression": "3pm Friday", "normalized_ts": null, '
            '"commitment_type": "HARD"}'
        )

    def _stub_non(_s: str, _u: str) -> str:
        return (
            '{"is_commitment": false, "confidence": 0.05, '
            '"time_expression": "", "normalized_ts": null, '
            '"commitment_type": "TENTATIVE"}'
        )

    with tempfile.TemporaryDirectory() as tmp:
        conn = init_db(str(Path(tmp) / "test.db"))
        try:
            # 1. Non-commitment: no rows, no conflicts.
            c0 = extract_and_update(
                "Hey, how are you?", "Alex", "annie", "2026-06-23", conn,
                llm_caller=_stub_non,
            )
            assert c0 == [], "non-commitment should yield no conflicts"
            count = conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0]
            assert count == 0, f"expected 0 rows, got {count}"
            print("=> non-commitment: 0 rows, 0 conflicts")

            # 2. Hard commitment: 1 row inserted.
            c1 = extract_and_update(
                "Let's meet at 3pm Friday.", "Alex", "annie", "2026-06-23", conn,
                llm_caller=_stub_hard,
            )
            count = conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0]
            assert count == 1, f"expected 1 row, got {count}"
            print(f"=> hard commitment: 1 row, {len(c1)} conflict(s)")

            # 3. Idempotency: same message + same ext_id must not insert a duplicate.
            extract_and_update(
                "Let's meet at 3pm Friday.", "Alex", "annie", "2026-06-23", conn,
                llm_caller=_stub_hard,
            )
            count = conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0]
            assert count == 1, f"idempotency failed: expected 1 row, got {count}"
            print("=> duplicate message not re-inserted")

            # 4. Overlapping commitment from a different thread triggers a conflict.
            c2 = extract_and_update(
                "Sync call at 3pm on Friday?", "Alex", "bob", "2026-06-23", conn,
                llm_caller=_stub_hard,
            )
            assert len(c2) == 1, f"expected 1 cross-thread conflict, got {len(c2)}"
            edge = c2[0]
            print(
                f"=> cross-thread conflict: {edge.commitment_a.source!r} vs "
                f"{edge.commitment_b.source!r}, overlap={edge.overlap_minutes:.0f} min"
            )
        finally:
            conn.close()

    print("All simchat/extractor.py smoke tests passed.")
