"""
api/smoke.py
------------
Offline smoke for the FastAPI layer — exercises the read endpoints end-to-end
through Starlette's TestClient, which runs the real app lifespan (demo-DB reset
+ seed scan + connector-snapshot seed). No keys, no Ollama, no network: the
bundled mock connectors + stub extractor cover everything.

Focused on the Cross-Signal Intelligence stream and the endpoints it touches:
  * GET /api/insights  — the new readiness payload (deep shape assertions)
  * GET /api/briefing  — the digest, which takes the default-signals path
                         (_default_signals -> gather_signals) the insights smoke
                         injects around, so this is where that path is exercised
  * GET /api/status    — basic liveness

Mirrors the demo_*.py scripts: run it, it asserts, it prints PASS.
Run:  python -m api.smoke
"""

from __future__ import annotations


def run() -> None:
    from fastapi.testclient import TestClient
    import api.main as m

    with TestClient(m.app) as client:
        # --- GET /api/status -------------------------------------------------
        r = client.get("/api/status")
        assert r.status_code == 200, f"/api/status -> {r.status_code}"
        assert r.json().get("app") == "KnowledgeMind", r.json()
        print("=> /api/status   200")

        # --- GET /api/insights (Cross-Signal Intelligence) ------------------
        r = client.get("/api/insights")
        assert r.status_code == 200, f"/api/insights -> {r.status_code}"
        d = r.json()
        assert {"date", "readiness", "signals", "load"} <= set(d), d.keys()

        rd = d["readiness"]
        assert {"score", "label", "factors", "recommendation"} <= set(rd), rd.keys()
        assert isinstance(rd["score"], int) and 0 <= rd["score"] <= 100, rd["score"]
        assert rd["label"] in {"fresh", "ok", "strained"}, rd["label"]
        assert isinstance(rd["recommendation"], str) and rd["recommendation"], rd
        assert isinstance(rd["factors"], list), rd["factors"]
        for f in rd["factors"]:
            assert {"signal", "detail", "impact"} <= set(f), f
            assert isinstance(f["impact"], int), f          # penalties are ints
        # the label must agree with the score band (no drift between the two)
        expected = "fresh" if rd["score"] >= 75 else "ok" if rd["score"] >= 45 else "strained"
        assert rd["label"] == expected, (rd["score"], rd["label"], expected)

        # connector seeding ran in the endpoint -> all four signal slots present
        assert set(d["signals"]) == {"todoist", "apple_health", "strava", "spotify"}, d["signals"].keys()
        assert {"commitments_today", "conflicts", "next"} <= set(d["load"]), d["load"].keys()
        assert isinstance(d["load"]["next"], list), d["load"]["next"]
        print(f"=> /api/insights 200 · score={rd['score']} label={rd['label']} "
              f"factors={len(rd['factors'])} signals={len(d['signals'])}")

        # --- GET /api/briefing (default-signals / gather_signals path) ------
        r = client.get("/api/briefing")
        assert r.status_code == 200, f"/api/briefing -> {r.status_code}"
        b = r.json().get("briefing", {})
        assert b.get("headline"), b
        assert "formatted" in b, b.keys()
        print(f"=> /api/briefing 200 · {b['headline']!r}")

    print("\napi/smoke.py smoke tests passed.")


if __name__ == "__main__":
    run()
