"""
proactive/insights.py
---------------------
Cross-Signal Intelligence — fuse the Hermes connector signals (sleep/recovery,
task-load, fitness, mood) with the commitment timeline into one deterministic
readiness-vs-load read:

  > "You have 5 commitments today (1 conflict) but slept 5.2h and recovery is
  >  low — consider deferring the soft ones."

No LLM. ``compute_readiness()`` is a pure function over a signals dict + a load
dict; ``compose_insights()`` wires it to the live connector snapshots
(connectors.db) and the KG (commitments + conflicts). Everything runs offline on
the bundled mock signals — see ``GET /api/insights`` (api/main.py) and the
Insights React view.

Reuses, never rebuilds:
  * ``kg.connector_store.get_latest`` — the persisted connector snapshots
  * ``kg.queries.conflict_edges``     — person-agnostic conflict detection
  * the ``commitments`` table (``status='active'``)

``gather_signals()`` is the single signal-read implementation, shared with
``proactive/briefing.py`` so the daily digest and the Insights view never
disagree about what the connectors are reporting.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from config.store import get_config
from kg.schema import get_db_connection
from kg.queries import conflict_edges


# ---------------------------------------------------------------------------
# Readiness penalty weights (§4.2)
# ---------------------------------------------------------------------------
# Tunable in one place. These are starting points calibrated against the mock
# signals, not sacred — see the "what I'd calibrate with real data" reflection
# at the bottom of the spec. Every weight is a penalty (<= 0); readiness starts
# at 100 and the conditions that fire subtract from it.

P_SLEEP_LT6 = -20      # apple_health: slept < 6 h
P_SLEEP_LT7 = -10      # apple_health: slept < 7 h (but >= 6)
P_RECOVERY_LOW = -18   # apple_health: recovery_status == 'low'
P_RECOVERY_MOD = -6    # apple_health: recovery_status == 'moderate'
P_LOW_HRV = -8         # apple_health: low_hrv
P_HIGH_RHR = -6        # apple_health: high_rhr
P_OVERDUE_EACH = -3    # todoist: per overdue task ...
P_OVERDUE_CAP = -18    # ... capped at this floor
P_HEAVY_DAY = -8       # todoist: heavy_day
P_COMMITS_GT6 = -15    # load: > 6 commitments today
P_COMMITS_GT4 = -8     # load: > 4 commitments today (but <= 6)
P_CONFLICTS = -6       # load: any scheduling conflicts today
P_LOW_MOOD = -5        # spotify: mood == 'low' or avg_valence < 0.4

LOW_VALENCE = 0.4      # spotify valence threshold for the low-mood signal

# Score -> label cut-offs: >= 75 fresh · 45–74 ok · < 45 strained.
FRESH_MIN = 75
OK_MIN = 45

# The connector sources we fuse (same set the briefing reads).
_CONNECTORS = ("todoist", "apple_health", "strava", "spotify")


# ---------------------------------------------------------------------------
# Signal gather (shared with proactive/briefing.py — §4.1)
# ---------------------------------------------------------------------------

def gather_signals() -> dict[str, Optional[dict]]:
    """Latest connector snapshot per Hermes source: ``{name: snapshot | None}``.

    Reads connectors.db via ``connector_store.get_latest``. Never raises — a
    missing or unreadable snapshot becomes ``None`` so the correlation degrades
    gracefully. This is the one signal-read implementation; the briefing reuses
    it (filtering to present-only) so both surfaces agree.
    """
    out: dict[str, Optional[dict]] = {name: None for name in _CONNECTORS}
    try:
        from kg import connector_store
        for name in _CONNECTORS:
            out[name] = connector_store.get_latest(name)
    except Exception:  # noqa: BLE001 — insights must never crash on missing signals
        pass
    return out


# ---------------------------------------------------------------------------
# Recommendation (rule-based, deterministic — no LLM)
# ---------------------------------------------------------------------------

def _recommendation(label: str, signals: dict[str, Any], load: dict[str, Any]) -> str:
    """A single actionable line derived from the label + the firing conditions."""
    ah = signals.get("apple_health") or {}
    td = signals.get("todoist") or {}
    commits = int(load.get("commitments_today") or 0)
    conflicts = int(load.get("conflicts") or 0)
    heavy = bool(td.get("heavy_day"))
    sleep_h = ah.get("sleep_hours")
    low_recovery = (
        ah.get("recovery_status") == "low"
        or bool(ah.get("low_hrv"))
        or (sleep_h is not None and sleep_h < 6)
    )

    if label == "strained":
        if heavy or commits > 4:
            if low_recovery:
                return ("Heavy day on low recovery — consider deferring "
                        "soft/tentative commitments.")
            return "Heavy load today — consider deferring soft/tentative commitments."
        return "Recovery is low — keep today light and protect the essentials."

    if label == "ok":
        if conflicts > 0:
            return (f"Manageable day, but resolve {conflicts} scheduling "
                    f"conflict(s) before they bite.")
        if heavy or commits > 4:
            return "Moderate load on partial recovery — don't add new soft commitments today."
        return "Balanced day — you have some capacity; pace the heavier tasks."

    # fresh
    if conflicts > 0:
        return f"You're fresh — a good moment to clear {conflicts} scheduling conflict(s)."
    return "Fresh and light — a good day to take on something demanding."


# ---------------------------------------------------------------------------
# Readiness correlation (§4.2) — pure function, no LLM, deterministic
# ---------------------------------------------------------------------------

def compute_readiness(signals: dict[str, Any], load: dict[str, Any]) -> dict[str, Any]:
    """Combine connector signals + commitment load into one readiness read.

    Args:
        signals: ``{connector_name: snapshot}`` (see ``gather_signals``). Missing
                 or ``None`` connectors are tolerated.
        load:    ``{commitments_today: int, conflicts: int, ...}`` from the KG.

    Returns:
        ``{score, label, factors: [{signal, detail, impact}], recommendation}``
        — ``score`` in [0, 100]; ``label`` in {fresh, ok, strained}; ``factors``
        are exactly the penalty rows that fired (so the UI can show *why*).
    """
    factors: list[dict[str, Any]] = []

    def fire(signal: str, detail: str, impact: int) -> None:
        factors.append({"signal": signal, "detail": detail, "impact": impact})

    # --- Apple Health: sleep + recovery -----------------------------------
    ah = signals.get("apple_health") or {}
    sleep_h = ah.get("sleep_hours")
    if sleep_h is not None:
        if sleep_h < 6:
            fire("apple_health", f"slept {sleep_h}h", P_SLEEP_LT6)
        elif sleep_h < 7:
            fire("apple_health", f"slept {sleep_h}h", P_SLEEP_LT7)
    recovery = ah.get("recovery_status")
    if recovery == "low":
        fire("apple_health", "recovery low", P_RECOVERY_LOW)
    elif recovery == "moderate":
        fire("apple_health", "recovery moderate", P_RECOVERY_MOD)
    if ah.get("low_hrv"):
        fire("apple_health", "low HRV", P_LOW_HRV)
    if ah.get("high_rhr"):
        fire("apple_health", "elevated resting HR", P_HIGH_RHR)

    # --- Todoist: overdue (−3 each, capped) + heavy day -------------------
    td = signals.get("todoist") or {}
    overdue = int(td.get("overdue_count") or 0)
    if overdue > 0:
        # both terms are negative; the cap is the floor (most-negative allowed).
        impact = max(overdue * P_OVERDUE_EACH, P_OVERDUE_CAP)
        fire("todoist", f"{overdue} overdue", impact)
    if td.get("heavy_day"):
        fire("todoist", "heavy task day", P_HEAVY_DAY)

    # --- Commitment load (KG: today's count + conflicts) ------------------
    commits = int(load.get("commitments_today") or 0)
    if commits > 6:
        fire("load", f"{commits} commitments today", P_COMMITS_GT6)
    elif commits > 4:
        fire("load", f"{commits} commitments today", P_COMMITS_GT4)
    conflicts = int(load.get("conflicts") or 0)
    if conflicts > 0:
        fire("load", f"{conflicts} conflict(s)", P_CONFLICTS)

    # --- Spotify: mood ----------------------------------------------------
    sp = signals.get("spotify") or {}
    valence = sp.get("avg_valence")
    if sp.get("mood") == "low" or (valence is not None and valence < LOW_VALENCE):
        fire("spotify", "low mood signal", P_LOW_MOOD)

    score = max(0, min(100, 100 + sum(f["impact"] for f in factors)))
    label = "fresh" if score >= FRESH_MIN else "ok" if score >= OK_MIN else "strained"

    return {
        "score": score,
        "label": label,
        "factors": factors,
        "recommendation": _recommendation(label, signals, load),
    }


# ---------------------------------------------------------------------------
# Commitment load (KG read, scoped to the injected `now`)
# ---------------------------------------------------------------------------

def _compute_load(conn, now: datetime.datetime) -> dict[str, Any]:
    """Today's commitment count + conflicts + the next few upcoming items."""
    day = now.date()
    start = datetime.datetime.combine(day, datetime.time.min).timestamp()
    end = datetime.datetime.combine(day, datetime.time.max).timestamp()

    commitments_today = conn.execute(
        "SELECT COUNT(*) FROM commitments WHERE status='active' AND start_ts BETWEEN ? AND ?",
        (start, end),
    ).fetchone()[0]

    conflicts = conflict_edges(conn, days=1).get("conflicts", [])

    next_rows = conn.execute(
        """SELECT description, start_ts FROM commitments
           WHERE status='active' AND start_ts >= ? ORDER BY start_ts LIMIT 3""",
        (now.timestamp(),),
    ).fetchall()
    upcoming = [
        {
            "description": r["description"],
            "at": datetime.datetime.fromtimestamp(r["start_ts"]).strftime("%H:%M"),
        }
        for r in next_rows
    ]

    return {
        "commitments_today": int(commitments_today),
        "conflicts": len(conflicts),
        "next": upcoming,
    }


# ---------------------------------------------------------------------------
# Composer (§4.3) — the GET /api/insights payload
# ---------------------------------------------------------------------------

def compose_insights(
    db_path: Optional[str] = None,
    *,
    now: Optional[datetime.datetime] = None,
    signals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build today's cross-signal readiness block.

    Args:
        db_path: KG database (defaults to ``cfg.db_path``).
        now:     injectable clock (defaults to ``datetime.now()``).
        signals: optional pre-fetched signals (tests / a future feed). ``None``
                 reads the latest connector snapshots via ``gather_signals()``.

    Returns ``{date, generated_iso, readiness, signals, load}``. Pure + offline:
    reads SQLite + the latest connector snapshots, never an LLM or the cloud.
    """
    now = now or datetime.datetime.now()
    db_path = db_path or get_config().db_path
    signals = gather_signals() if signals is None else signals

    conn = get_db_connection(db_path)
    try:
        load = _compute_load(conn, now)
    finally:
        conn.close()

    return {
        "date": now.date().isoformat(),
        "generated_iso": now.isoformat(timespec="seconds"),
        "readiness": compute_readiness(signals, load),
        "signals": signals,
        "load": load,
    }


# ---------------------------------------------------------------------------
# Smoke test (offline) — exercises EVERY penalty row in §4.2 (acceptance §7)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    def _factor(res, signal, needle):
        return next(
            (f for f in res["factors"] if f["signal"] == signal and needle in f["detail"]),
            None,
        )

    EMPTY = {"commitments_today": 0, "conflicts": 0}

    # Each tuple isolates one §4.2 row so every penalty is provably exercised
    # with the right detail string + impact. (name, signals, load, signal,
    # detail-needle, expected impact).
    rows = [
        ("sleep<6",      {"apple_health": {"sleep_hours": 5.2}},          EMPTY,                                 "apple_health", "5.2",      P_SLEEP_LT6),
        ("sleep<7",      {"apple_health": {"sleep_hours": 6.5}},          EMPTY,                                 "apple_health", "6.5",      P_SLEEP_LT7),
        ("recovery low", {"apple_health": {"recovery_status": "low"}},    EMPTY,                                 "apple_health", "recovery", P_RECOVERY_LOW),
        ("recovery mod", {"apple_health": {"recovery_status": "moderate"}}, EMPTY,                               "apple_health", "recovery", P_RECOVERY_MOD),
        ("low_hrv",      {"apple_health": {"low_hrv": True}},             EMPTY,                                 "apple_health", "HRV",      P_LOW_HRV),
        ("high_rhr",     {"apple_health": {"high_rhr": True}},            EMPTY,                                 "apple_health", "resting",  P_HIGH_RHR),
        ("overdue cap",  {"todoist": {"overdue_count": 6}},               EMPTY,                                 "todoist",      "overdue",  P_OVERDUE_CAP),
        ("heavy_day",    {"todoist": {"heavy_day": True}},                EMPTY,                                 "todoist",      "heavy",    P_HEAVY_DAY),
        ("commits>6",    {},                                              {"commitments_today": 7, "conflicts": 0}, "load",     "commitment", P_COMMITS_GT6),
        ("commits>4",    {},                                              {"commitments_today": 5, "conflicts": 0}, "load",     "commitment", P_COMMITS_GT4),
        ("conflicts",    {},                                              {"commitments_today": 0, "conflicts": 2}, "load",     "conflict", P_CONFLICTS),
        ("spotify mood", {"spotify": {"mood": "low"}},                    EMPTY,                                 "spotify",      "mood",     P_LOW_MOOD),
        ("spotify valence", {"spotify": {"avg_valence": 0.3}},            EMPTY,                                 "spotify",      "mood",     P_LOW_MOOD),
    ]
    for name, sig, load, signal, needle, impact in rows:
        res = compute_readiness(sig, load)
        f = _factor(res, signal, needle)
        assert f is not None, f"[{name}] no {signal} factor matching '{needle}': {res['factors']}"
        assert f["impact"] == impact, f"[{name}] expected impact {impact}, got {f['impact']}"
    print(f"=> per-row coverage: all {len(rows)} penalty rows fired with the right impact")

    # Overdue scales −3 each *below* the cap.
    res = compute_readiness({"todoist": {"overdue_count": 3}}, EMPTY)
    assert _factor(res, "todoist", "overdue")["impact"] == -9, "overdue should scale −3 each below cap"

    # --- Narrative fixtures: label + score change with the inputs ----------
    strained = compute_readiness(
        {"apple_health": {"sleep_hours": 5.2, "recovery_status": "low",
                          "low_hrv": True, "high_rhr": True},
         "todoist": {"overdue_count": 6, "heavy_day": True},
         "spotify": {"mood": "low"}},
        {"commitments_today": 7, "conflicts": 2},
    )
    assert strained["label"] == "strained" and strained["score"] < OK_MIN, strained
    assert "defer" in strained["recommendation"].lower(), strained["recommendation"]

    ok = compute_readiness(
        {"apple_health": {"sleep_hours": 6.5, "recovery_status": "moderate"},
         "spotify": {"avg_valence": 0.35}},
        {"commitments_today": 5, "conflicts": 0},
    )
    assert ok["label"] == "ok", ok

    fresh = compute_readiness(
        {"apple_health": {"sleep_hours": 8.0, "recovery_status": "high"},
         "todoist": {"overdue_count": 0, "heavy_day": False},
         "spotify": {"mood": "upbeat", "avg_valence": 0.7}},
        {"commitments_today": 2, "conflicts": 0},
    )
    assert fresh["label"] == "fresh" and fresh["score"] == 100 and not fresh["factors"], fresh
    print(f"=> narrative: strained={strained['score']} · ok={ok['score']} · fresh={fresh['score']}")

    # --- compose_insights end-to-end on a seeded KG (fully offline) --------
    import tempfile
    import time as _time
    from pathlib import Path
    from kg.schema import init_db

    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "insights.db")
        conn = init_db(db)
        now = datetime.datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        at = now.replace(hour=16).timestamp()
        conn.execute("INSERT INTO persons (id, name, created_at) VALUES (1, 'Lena', ?)", (_time.time(),))
        conn.execute(
            """INSERT INTO commitments
               (person_id, description, start_ts, end_ts, source, commitment_type,
                confidence, raw_text, created_at, updated_at, status)
               VALUES (1, 'Lunch with Lena', ?, ?, 'calendar', 'SOFT', 0.8, '', ?, ?, 'active')""",
            (at, at + 3600, _time.time(), _time.time()),
        )
        conn.commit()
        conn.close()

        # Inject crafted signals so the payload is deterministic (no connectors.db).
        out = compose_insights(
            db_path=db, now=now,
            signals={"apple_health": {"sleep_hours": 5.0, "recovery_status": "low"},
                     "todoist": {"overdue_count": 2, "heavy_day": True}},
        )
        assert out["date"] == now.date().isoformat()
        assert out["load"]["commitments_today"] == 1, out["load"]
        assert out["readiness"]["factors"], "expected factors from the injected signals"
        assert out["load"]["next"] and out["load"]["next"][0]["at"] == "16:00", out["load"]["next"]
        print(f"=> compose_insights: score={out['readiness']['score']} "
              f"label={out['readiness']['label']} · "
              f"{out['load']['commitments_today']} commitment(s), "
              f"next at {out['load']['next'][0]['at']}")

    # --- gather_signals() contract (tolerates a missing/empty connectors.db) -
    gs = gather_signals()
    assert set(gs.keys()) == set(_CONNECTORS), gs.keys()
    assert all(v is None or isinstance(v, dict) for v in gs.values()), gs
    print(f"=> gather_signals: contract OK "
          f"({sum(v is not None for v in gs.values())}/4 have a live snapshot)")

    # --- compose_insights default path (signals=None -> gather_signals) ------
    # Exercises the real gather path end-to-end and proves graceful degradation:
    # an empty KG + whatever signals exist must still yield a well-formed payload.
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "default.db")
        init_db(db).close()
        payload = compose_insights(db_path=db)  # no signals= -> default gather
        assert {"date", "readiness", "signals", "load"} <= set(payload), payload.keys()
        assert payload["readiness"]["label"] in {"fresh", "ok", "strained"}, payload["readiness"]
        assert set(payload["signals"]) == set(_CONNECTORS), payload["signals"].keys()
        assert payload["load"]["commitments_today"] == 0, payload["load"]
        print(f"=> compose_insights(default path): label={payload['readiness']['label']} on empty KG")

    print("\nproactive/insights.py smoke tests passed.")
