"""
memory/memory_manager.py
------------------------
Two-layer conversation memory.

Short-term : SQLite `turns` table -- recent dialogue, token-budgeted.
Long-term  : ChromaDB `hybridmind_memory` collection -- semantic recall.

The orchestrator uses the short-term layer every turn (add_user_message /
get_context / add_assistant_message). The long-term layer is lazy and degrades
gracefully when ChromaDB or the embedding model is unavailable (SPEC 8).

A single `memory_manager` singleton is exported and shared process-wide.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from config.store import get_config
from kg.schema import get_db_connection


# Roles that count as dialogue history fed to the LLM.
_LLM_ROLES: frozenset[str] = frozenset({"user", "assistant"})

# Long-term recall similarity floor (SPEC 4.9).
_RECALL_SIMILARITY_FLOOR: float = 0.5

# Embedding model for long-term memory (SPEC 4.9).
_EMBED_MODEL_NAME: str = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Short-term memory (SQLite turns table)
# ---------------------------------------------------------------------------

class ShortTermMemory:
    """Recent dialogue, persisted in the SQLite `turns` table."""

    def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_name: Optional[str] = None,
        routing_decision: Optional[str] = None,
    ) -> None:
        """Append a single turn for a session."""
        token_estimate = max(len(content) // 4, 1)
        conn = get_db_connection(get_config().db_path)
        try:
            conn.execute(
                """INSERT INTO turns
                   (session_id, role, content, timestamp, tool_name,
                    routing_decision, token_estimate)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, time.time(), tool_name,
                 routing_decision, token_estimate),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_turns(self, session_id: str, max_tokens: int = 4000) -> list[dict[str, Any]]:
        """
        Return recent dialogue turns (oldest-first) whose cumulative token
        estimate fits the budget, filling from the most recent backwards.
        """
        conn = get_db_connection(get_config().db_path)
        try:
            rows = conn.execute(
                """SELECT role, content, token_estimate FROM turns
                   WHERE session_id = ? AND role IN ('user', 'assistant')
                   ORDER BY timestamp DESC, id DESC""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        budget = max_tokens
        collected: list[dict[str, Any]] = []
        for row in rows:
            cost = row["token_estimate"] or 1
            if budget - cost < 0 and collected:
                break
            budget -= cost
            collected.append({"role": row["role"], "content": row["content"]})
        collected.reverse()  # oldest-first for the LLM
        return collected

    def format_for_llm(
        self, session_id: str, exclude_last_user: bool = False
    ) -> list[dict[str, str]]:
        """
        Return dialogue as a LangChain-style message list.

        Args:
            exclude_last_user: when True, drop a trailing user turn. The
                orchestrator re-appends the current user_input itself, so this
                prevents the latest message appearing twice.
        """
        cfg = get_config()
        turns = self.get_recent_turns(session_id, cfg.max_context_tokens)
        messages = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in turns
            if turn["role"] in _LLM_ROLES
        ]
        if exclude_last_user and messages and messages[-1]["role"] == "user":
            messages = messages[:-1]
        return messages

    def clear_session(self, session_id: str) -> None:
        """Delete all turns for a session."""
        conn = get_db_connection(get_config().db_path)
        try:
            conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Long-term memory (ChromaDB)
# ---------------------------------------------------------------------------

class LongTermMemory:
    """Semantic long-term memory backed by ChromaDB. Lazy + fail-soft."""

    def __init__(self) -> None:
        self._collection: Any = None
        self._available: Optional[bool] = None  # None = not yet probed

    def _ensure_collection(self) -> bool:
        """Lazily create the Chroma collection. Returns availability."""
        if self._available is not None:
            return self._available
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            cfg = get_config()
            client = chromadb.PersistentClient(path=cfg.chroma_persist_dir)
            embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=_EMBED_MODEL_NAME
            )
            self._collection = client.get_or_create_collection(
                name="hybridmind_memory", embedding_function=embedder
            )
            self._available = True
        except Exception as error:  # noqa: BLE001 -- degrade gracefully
            print(f"[Memory] WARNING: long-term memory unavailable ({error}).")
            self._available = False
        return self._available

    def store(self, content: str, source: str, importance: float = 0.5) -> bool:
        """Embed and store a memory item. Returns False if store unavailable."""
        if not self._ensure_collection():
            return False
        item_id = f"{source}:{int(time.time() * 1000)}"
        self._collection.add(
            documents=[content],
            metadatas=[{"source": source, "importance": importance, "ts": time.time()}],
            ids=[item_id],
        )
        return True

    def recall(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Semantic search; returns items above the similarity floor."""
        if not self._ensure_collection():
            return []
        result = self._collection.query(query_texts=[query], n_results=top_k)
        documents = (result.get("documents") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        recalled: list[dict[str, Any]] = []
        for document, distance in zip(documents, distances):
            similarity = 1.0 - float(distance)  # cosine distance -> similarity
            if similarity >= _RECALL_SIMILARITY_FLOOR:
                recalled.append({"content": document, "similarity": round(similarity, 3)})
        return recalled


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------

class MemoryManager:
    """Unifies short-term and long-term memory behind one object."""

    def __init__(self) -> None:
        self.conversation = ShortTermMemory()
        self.longterm = LongTermMemory()

    def add_user_message(self, session_id: str, content: str) -> None:
        self.conversation.add_turn(session_id, "user", content)

    def add_assistant_message(self, session_id: str, content: str) -> None:
        self.conversation.add_turn(session_id, "assistant", content)

    def get_context(self, session_id: str) -> list[dict[str, str]]:
        """Prior dialogue for the LLM, excluding the just-added user message."""
        return self.conversation.format_for_llm(session_id, exclude_last_user=True)


# Shared process-wide singleton.
memory_manager = MemoryManager()


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import tempfile

    from config.store import get_config as _get_config

    with tempfile.TemporaryDirectory() as tmp:
        # Point config at a throwaway DB for the test.
        os.environ["KM_DB_PATH"] = str(os.path.join(tmp, "mem.db"))
        cfg = _get_config()
        cfg.db_path = os.environ["KM_DB_PATH"]

        session = "test-session"
        memory_manager.add_user_message(session, "What is on my calendar?")
        memory_manager.add_assistant_message(session, "You have a standup at 10am.")
        memory_manager.add_user_message(session, "And tomorrow?")

        # get_context must exclude the trailing (current) user message.
        context = memory_manager.get_context(session)
        assert context[-1]["role"] == "assistant", "trailing user turn not excluded"
        print(f"=> short-term context has {len(context)} message(s)")

        memory_manager.conversation.clear_session(session)
        assert memory_manager.get_context(session) == [], "session not cleared"
        print("=> session cleared")

    print("All memory/memory_manager.py smoke tests passed.")
