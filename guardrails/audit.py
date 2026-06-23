"""
guardrails/audit.py
-------------------
Per-request routing & privacy audit trail (Stream 3 — Provable Privacy).

Records every routing decision and every local->cloud fallback to an append-only
JSONL log, and keeps a per-turn summary (via a ContextVar) so the chat response
can honestly show whether a turn executed LOCAL, went CLOUD, or fell back. The
silent fallback was the dishonesty — so every fallback is logged, and a personal
fallback is surfaced to the UI rather than hidden behind a green LOCAL badge.
"""
from __future__ import annotations

import json
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from config.store import get_config

# Per-request privacy summary, isolated per async/thread context.
_turn: ContextVar[Optional[dict]] = ContextVar("km_turn_privacy", default=None)


def _fresh() -> dict:
    return {"cloud": False, "personal_fallback": False, "fallback_blocked": False, "events": []}


def _audit_path() -> Path:
    # Sibling of the alerts log -> lives under the config dir (/tmp on the Space).
    return Path(get_config().alerts_log_path).with_name("privacy_audit.jsonl")


def _append(rec: dict) -> None:
    try:
        with open(_audit_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


# -- per-turn summary --------------------------------------------------------

def begin_turn() -> None:
    """Start a fresh privacy summary for the current request."""
    _turn.set(_fresh())


def turn_summary() -> dict:
    t = _turn.get()
    return dict(t) if t else _fresh()


# -- recorders ---------------------------------------------------------------

def record_route(result, source: str = "agent") -> None:
    """Record one routing decision (a routing.router.RoutingResult)."""
    _append({
        "ts": time.time(), "kind": "route", "source": source,
        "decision": result.decision.value,
        "privacy_score": round(result.privacy_score, 3),
        "complexity_score": round(result.complexity_score, 3),
        "tool": result.tool_name, "reason": result.reason,
    })
    t = _turn.get()
    if t is not None:
        t["events"].append({"kind": "route", "decision": result.decision.value, "tool": result.tool_name})
        if result.decision.value == "cloud":
            t["cloud"] = True


def record_fallback(node: str, *, blocked: bool, personal: bool, model: Optional[str] = None) -> None:
    """Record a local-unavailable event: blocked (fail-closed) or fell back to cloud."""
    rec = {
        "ts": time.time(), "kind": "fallback", "node": node,
        "blocked": bool(blocked), "personal": bool(personal), "model": model,
    }
    _append(rec)
    t = _turn.get()
    if t is not None:
        t["events"].append(rec)
        if blocked:
            t["fallback_blocked"] = True
        else:
            t["cloud"] = True
            if personal:
                t["personal_fallback"] = True


# -- readers -----------------------------------------------------------------

def read_recent(limit: int = 100) -> list[dict]:
    path = _audit_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def report() -> dict:
    recs = read_recent(10000)
    routes = [r for r in recs if r.get("kind") == "route"]
    falls = [r for r in recs if r.get("kind") == "fallback"]
    total = len(routes)
    local = sum(1 for r in routes if r.get("decision") == "local")
    return {
        "total_decisions": total,
        "local": local,
        "cloud": total - local,
        "pct_local": round(100 * local / total, 1) if total else 0.0,
        "fallbacks_to_cloud": sum(1 for r in falls if not r.get("blocked")),
        "personal_fallbacks": sum(1 for r in falls if not r.get("blocked") and r.get("personal")),
        "leaks_prevented": sum(1 for r in falls if r.get("blocked")),
    }


# -- smoke test --------------------------------------------------------------

if __name__ == "__main__":
    import os
    import tempfile

    cfg = get_config()
    with tempfile.TemporaryDirectory() as tmp:
        cfg.alerts_log_path = os.path.join(tmp, "alerts.jsonl")
        begin_turn()

        class _R:  # minimal RoutingResult stand-in
            class _D:
                value = "local"
            decision = _D()
            privacy_score = 0.97
            complexity_score = 0.10
            tool_name = "query_kg"
            reason = "pinned"

        record_route(_R())
        record_fallback("synth", blocked=True, personal=True)

        s = turn_summary()
        assert s["fallback_blocked"] is True, s
        assert s["personal_fallback"] is False, s   # blocked -> prevented, not leaked
        rep = report()
        assert rep["total_decisions"] == 1 and rep["leaks_prevented"] == 1, rep
        print("=> turn summary:", s)
        print("=> report:", rep)
    print("All guardrails/audit.py smoke tests passed.")
