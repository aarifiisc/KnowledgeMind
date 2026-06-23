"""
demo_privacy.py
---------------
Offline acceptance test for Stream 3 (Provable Privacy) — the proof the stream
rests on. Locally there is no Ollama, so _call_ollama always takes its fallback
path: the perfect fixture. We stub the cloud caller to flag if it is ever invoked,
then prove the two non-negotiables:

  1. PERSONAL work + allow_cloud_fallback=False  -> the cloud is NEVER called
     (fail-closed: personal data does not leave the device).
  2. NON-personal work (allow_fallback=True)     -> falls back to the cloud, so
     the assistant stays usable on a no-Ollama host (e.g. the HF Space).

Run:  .venv/bin/python demo_privacy.py
"""
from __future__ import annotations

import os
import tempfile

import agent.orchestrator as orch
from config.store import get_config
from guardrails import audit


class _Tracker:
    def record(self, *a, **k): pass
    def mark_call_start(self): pass


def main() -> None:
    cfg = get_config()
    # Keep the audit out of the real config dir during the test.
    cfg.alerts_log_path = os.path.join(tempfile.gettempdir(), "km_demo_privacy_alerts.jsonl")
    audit.begin_turn()

    # Trip-wire: any call to the cloud fast tier is recorded.
    calls = {"cloud": 0}

    def _cloud_trip(*_a, **_k):
        calls["cloud"] += 1
        return "[CLOUD ANSWER]"

    orch._call_groq_fast = _cloud_trip  # monkeypatch the module-level cloud caller

    # 1) PERSONAL + fail-closed  ->  must NOT touch the cloud.
    cfg.allow_cloud_fallback = False
    out = orch._call_ollama(
        [{"role": "user", "content": "what meetings do I have on my calendar tomorrow"}],
        "system", _Tracker(), "synth", "L1", allow_fallback=False, personal=True,
    )
    assert calls["cloud"] == 0, "LEAK: personal work reached the cloud under fail-closed!"
    assert "privacy mode" in out.lower(), f"expected a fail-closed message, got: {out!r}"
    print(f"=> personal + fail-closed : cloud_calls={calls['cloud']}  (no leak) OK")

    # 2) NON-personal + fallback allowed  ->  uses the cloud (assistant stays alive).
    out2 = orch._call_ollama(
        [{"role": "user", "content": "hello"}],
        "system", _Tracker(), "single_call", "L1", allow_fallback=True, personal=False,
    )
    assert calls["cloud"] == 1 and out2 == "[CLOUD ANSWER]", (calls, out2)
    print(f"=> non-personal + allowed : cloud_calls={calls['cloud']}  (fell back) OK")

    summary = audit.turn_summary()
    assert summary["fallback_blocked"] is True, summary
    assert summary["personal_fallback"] is False, summary  # the personal one was BLOCKED, not leaked
    print(f"=> turn summary : {summary}")
    print(f"=> report       : {audit.report()}")
    print("\nAll demo_privacy.py acceptance checks passed.")


if __name__ == "__main__":
    main()
