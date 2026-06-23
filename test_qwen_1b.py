"""Smoke test: HybridMindAgent with qwen2.5:1.5b as the local model.

L1 runs fully local (no Groq needed).
L2/L3 require Groq; skipped with a note if no key is set.
"""
import os
os.environ["KM_LOCAL_MODEL"] = "qwen2.5:1.5b"

from config.store import get_config
from agent.orchestrator import HybridMindAgent, AgencyLevel

cfg = get_config()
HAS_GROQ = bool(cfg.groq_api_key)

L1_TESTS = [
    "hello",
    "What is the capital of France?",
    "What are the main differences between L1, L2, and L3 agency levels?",
    "List my upcoming calendar events",
    "What did I discuss in previous sessions?",
]

L2_TESTS = [
    "List my upcoming calendar events and find a free 1-hour slot this week",
    "Search the web for latest AI news and summarise it",
]

L3_TESTS = [
    "Search the web for latest AI news, summarise it, and add a calendar reminder to read more tomorrow",
]


def run_test(agent: HybridMindAgent, query: str, level: AgencyLevel) -> None:
    import traceback as tb
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"[{level.value}] {query}")
    print(sep)
    try:
        result = agent.run(query, agency_level=level)
    except Exception as exc:
        print(f"EXCEPTION: {exc}")
        tb.print_exc()
        return
    answer = result["answer"]
    print(f"Answer  : {answer[:500]}")
    print(f"Elapsed : {result['elapsed']}s")
    tok = result.get("token_summary")
    if tok:
        print(f"Tokens  : prompt={tok.total_prompt_tokens}  completion={tok.total_completion_tokens}")
    for r in result.get("routing_log", []):
        print(
            f"  Route [{r['step_id']}] {r['tool']:20s} -> {r['decision']:6s}"
            f"  priv={r['privacy_score']:.2f}  cmplx={r['complexity_score']:.2f}"
        )


import uuid
agent = HybridMindAgent(session_id=f"test-qwen-{uuid.uuid4().hex[:6]}")

print("\n" + "#" * 64)
print("# L1 — Augmented LLM (fully local, qwen2.5:1.5b)")
print("#" * 64)
for q in L1_TESTS:
    run_test(agent, q, AgencyLevel.L1_AUGMENTED)

if HAS_GROQ:
    print("\n" + "#" * 64)
    print("# L2 — Workflow (Groq plan + local execute)")
    print("#" * 64)
    for q in L2_TESTS:
        run_test(agent, q, AgencyLevel.L2_WORKFLOW)

    print("\n" + "#" * 64)
    print("# L3 — Autonomous ReAct (Groq reason + local execute)")
    print("#" * 64)
    for q in L3_TESTS:
        run_test(agent, q, AgencyLevel.L3_AUTONOMOUS)
else:
    print("\n[SKIP] L2/L3 tests — no GROQ_API_KEY configured.")
    print("       Set groq_api_key in Settings or via GROQ_API_KEY env var to enable cloud planning.")
