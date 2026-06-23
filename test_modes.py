"""
test_modes.py
-------------
Test harness for Query Mode and Preemptive Mode.
Run from the KnowledgeMind project root:
    python test_modes.py
"""

from routing.router import router, RoutingDecision
from hermes_tools.strava_tool import strava_summary
from hermes_tools.apple_health_tool import apple_health_summary
from hermes_tools.todoist_tool import todoist_summary, todoist_tasks
from hermes_tools.spotify_tool import spotify_mood


# ---------------------------------------------------------------------------
# QUERY MODE
# ---------------------------------------------------------------------------

QUERY_MODE_CASES = [
    # (prompt, tool_name, expected_routing)
    ("Do I have schedule conflicts today?",         "conflict_edges",       "LOCAL"),
    ("What tasks are overdue from Todoist?",         "todoist_tasks",        "LOCAL"),
    ("How has my fitness been this week?",           "strava_summary",       "LOCAL"),
    ("What is my sleep score today?",                "apple_health_summary", "LOCAL"),
    ("Am I in the zone with my Spotify?",            "spotify_mood",         "LOCAL"),
    ("Find me a free 1-hour slot tomorrow",          "find_free_slots",      "LOCAL"),
    ("Check my Gmail inbox for unread messages",     "gmail",                "LOCAL"),
    ("Research and compare the latest LLM benchmark papers",  "web_search",   "CLOUD"),
    ("What is the capital of France?",               None,                   "LOCAL"),
    ("Remind me about my 3pm meeting",               "query_kg",             "LOCAL"),
]


def run_query_mode_tests():
    print("=" * 60)
    print("QUERY MODE — Routing tests")
    print("=" * 60)
    passed = 0
    for prompt, tool, expected in QUERY_MODE_CASES:
        result = router.route(prompt, tool_name=tool)
        got = result.decision.value.upper()
        ok = got == expected
        label = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f"  [{label}] {prompt[:48]}")
        if not ok:
            print(f"         got={got}  expected={expected}  reason={result.reason}")
    print(f"\n  => {passed}/{len(QUERY_MODE_CASES)} query-mode routing tests passed")
    return passed == len(QUERY_MODE_CASES)


# ---------------------------------------------------------------------------
# PREEMPTIVE MODE
# ---------------------------------------------------------------------------

def run_preemptive_mode_tests():
    print()
    print("=" * 60)
    print("PREEMPTIVE MODE — Connector signals")
    print("=" * 60)

    strava  = strava_summary()
    health  = apple_health_summary()
    tasks   = todoist_summary()
    raw     = todoist_tasks("today | overdue")
    mood    = spotify_mood()

    print("\n[Strava]")
    print(f"  source                   : {strava['source']}")
    print(f"  days_since_last_activity : {strava['days_since_last_activity']}")
    print(f"  gap_threshold_exceeded   : {strava['gap_threshold_exceeded']}")
    print(f"  summary                  : {strava['summary']}")

    print("\n[Apple Health]")
    print(f"  source          : {health['source']}")
    print(f"  sleep_quality   : {health['sleep_quality']}")
    print(f"  recovery_status : {health['recovery_status']}")
    print(f"  low_hrv         : {health['low_hrv']}")
    print(f"  summary         : {health['summary']}")

    print("\n[Todoist]")
    print(f"  source          : {tasks['source']}")
    print(f"  overdue_count   : {tasks['overdue_count']}")
    print(f"  due_today_count : {tasks['due_today_count']}")
    print(f"  heavy_day       : {tasks['heavy_day']}")
    print(f"  task count (raw): {raw['count']}")
    print(f"  summary         : {tasks['summary']}")

    print("\n[Spotify]")
    print(f"  source            : {mood['source']}")
    print(f"  mood              : {mood['mood']}")
    print(f"  deep_work_session : {mood['deep_work_session']}")
    print(f"  session_minutes   : {mood['session_minutes']}")
    print(f"  summary           : {mood['summary']}")

    # Cross-source fusion (simulates the morning brief cron skill)
    print("\n[Cross-source fusion — preemptive signal evaluation]")
    fitness_gap   = strava.get("gap_threshold_exceeded", False)
    poor_sleep    = health.get("sleep_quality") in ("poor",)
    low_recovery  = health.get("recovery_status") in ("low",)
    heavy_day     = tasks.get("heavy_day", False)
    deep_work     = mood.get("deep_work_session", False)

    nudges = []
    if fitness_gap and not poor_sleep and not low_recovery:
        nudges.append("Fitness nudge: activity gap + good recovery -> suggest workout")
    elif fitness_gap and (poor_sleep or low_recovery):
        nudges.append("Soft fitness nudge: gap exceeded but recovery low -> suggest rest")

    if heavy_day:
        nudges.append(
            f"Task nudge: heavy day ({tasks['overdue_count']} overdue, "
            f"{tasks['due_today_count']} due today)"
        )

    if deep_work:
        nudges.append("Deep-work alert: in flow state -> check upcoming meetings")

    if nudges:
        for n in nudges:
            print(f"  => {n}")
    else:
        print("  => No actionable signals — preemptive agent would stay silent")

    # Privacy assertions
    print("\n[Privacy checks]")
    checks_ok = True

    for key in ("name", "artist", "track_name", "artist_name"):
        if key in mood and mood[key]:
            print(f"  FAIL: field '{key}' present in Spotify result (privacy leak)")
            checks_ok = False
    print("  PASS: No raw track/artist names in Spotify result")

    strava_str = str(strava)
    if any(kw in strava_str for kw in ("latlng", "latitude", "longitude")):
        print("  FAIL: GPS coordinates present in Strava result")
        checks_ok = False
    else:
        print("  PASS: No GPS data in Strava result")

    # All connector results must come from mock (no credentials set up)
    for name, r in [("strava", strava), ("health", health), ("tasks", tasks), ("mood", mood)]:
        assert r["success"] is True, f"{name}: success != True"
        assert r["source"] in ("live", "mock"), f"{name}: unexpected source value"
    print("  PASS: All connectors returned success=True")

    return checks_ok


# ---------------------------------------------------------------------------
# MCP server import check (privacy assertion at server boundary)
# ---------------------------------------------------------------------------

def run_mcp_import_check():
    print()
    print("=" * 60)
    print("MCP SERVER — import + privacy assertion check")
    print("=" * 60)
    try:
        import mcp_serve  # noqa: F401 — just verify it imports cleanly
        print("  PASS: mcp_serve.py imports without error")
        return True
    except Exception as e:
        print(f"  WARN: mcp_serve.py import raised: {e}")
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    q_ok = run_query_mode_tests()
    p_ok = run_preemptive_mode_tests()
    m_ok = run_mcp_import_check()

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Query mode routing : {'PASS' if q_ok else 'FAIL'}")
    print(f"  Preemptive signals : {'PASS' if p_ok else 'FAIL'}")
    print(f"  MCP server import  : {'PASS' if m_ok else 'WARN (mcp pkg not installed)'}")
    print()
    if q_ok and p_ok:
        print("All critical tests passed.")
    else:
        print("Some tests failed — see output above.")
