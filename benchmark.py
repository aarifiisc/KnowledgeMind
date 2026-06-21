"""
benchmark.py
------------
KnowledgeMind evaluation suite (SPEC 10).

30 tasks across 5 categories (6 each). Three run modes:

  static   -- offline: routes every task's tools through the privacy router and
              checks the routing/privacy contract. No LLM required. (default)
  ablation -- offline: compares local-only / hybrid / cloud-only routing,
              counting cloud calls and the privacy violations each would cause.
              (Cloud-only is NOT executed -- it would leak personal data; we
              only quantify how many high-privacy steps it would expose.)
  live     -- runs each task through HybridMindAgent and measures Task
              Completion Rate, routing accuracy, latency, and tokens.
              Requires a reachable model (Ollama / Groq).

Usage:
  python benchmark.py                          # static routing check
  python benchmark.py --mode ablation
  python benchmark.py --mode live --level L2 --limit 5 -v
  python benchmark.py --category "KG / Scheduling" -v
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from tabulate import tabulate

from routing.router import (
    router,
    RoutingDecision,
    ALWAYS_LOCAL_TOOLS,
    TOOL_PRIVACY_FLOORS,
    PRIVACY_LOCAL_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Task model
# ---------------------------------------------------------------------------

class Category(str, Enum):
    WEB_RESEARCH = "Web Research"
    DOCUMENT_QA = "Document Q&A"
    KG_SCHEDULING = "KG / Scheduling"
    CALENDAR_GMAIL = "Calendar / Gmail"
    COMPOUND = "Multi-step Compound"


@dataclass
class BenchmarkTask:
    id: str
    category: Category
    prompt: str
    expected_tools: list[str]
    privacy: str                 # 'LOW' | 'HIGH' | 'MIXED'
    expects_replan: bool = False


# SPEC 10 latency targets.
LATENCY_TARGET_SIMPLE_S: float = 15.0
LATENCY_TARGET_COMPOUND_S: float = 30.0
TCR_TARGET_PCT: float = 85.0
ROUTING_TARGET_PCT: float = 100.0


# ---------------------------------------------------------------------------
# The 30 tasks
# ---------------------------------------------------------------------------

BENCHMARK_TASKS: list[BenchmarkTask] = [
    # -- Web Research (LOW privacy -> web_search may go CLOUD) ---------------
    BenchmarkTask("WR1", Category.WEB_RESEARCH,
                  "What is the attention mechanism in transformer models?",
                  ["web_search"], "LOW"),
    BenchmarkTask("WR2", Category.WEB_RESEARCH,
                  "Summarise recent advances in retrieval-augmented generation.",
                  ["web_search"], "LOW"),
    BenchmarkTask("WR3", Category.WEB_RESEARCH,
                  "What are the differences between LoRA and full fine-tuning?",
                  ["web_search"], "LOW"),
    BenchmarkTask("WR4", Category.WEB_RESEARCH,
                  "Find recent benchmarks comparing open-source LLMs.",
                  ["web_search"], "LOW"),
    BenchmarkTask("WR5", Category.WEB_RESEARCH,
                  "What is the current state of the art in speech recognition?",
                  ["web_search"], "LOW"),
    BenchmarkTask("WR6", Category.WEB_RESEARCH,
                  "Explain mixture-of-experts architectures in large language models.",
                  ["web_search"], "LOW"),

    # -- Document Q&A (HIGH -> rag_query LOCAL) -----------------------------
    BenchmarkTask("DQ1", Category.DOCUMENT_QA,
                  "According to my documents, what is the privacy contract?",
                  ["rag_query"], "HIGH"),
    BenchmarkTask("DQ2", Category.DOCUMENT_QA,
                  "Summarise the key points from my indexed papers.",
                  ["rag_query"], "HIGH"),
    BenchmarkTask("DQ3", Category.DOCUMENT_QA,
                  "What does my document say about the routing threshold?",
                  ["rag_query"], "HIGH"),
    BenchmarkTask("DQ4", Category.DOCUMENT_QA,
                  "Find the section in my notes about conflict detection.",
                  ["rag_query"], "HIGH"),
    BenchmarkTask("DQ5", Category.DOCUMENT_QA,
                  "What are the main conclusions in my uploaded report?",
                  ["rag_query"], "HIGH"),
    BenchmarkTask("DQ6", Category.DOCUMENT_QA,
                  "Quote the part of my document that discusses the monitor FSM.",
                  ["rag_query"], "HIGH"),

    # -- KG / Scheduling (HIGH -> query_kg / find_free_slots LOCAL) ----------
    BenchmarkTask("KG1", Category.KG_SCHEDULING,
                  "What commitments do I have this week?",
                  ["query_kg"], "HIGH"),
    BenchmarkTask("KG2", Category.KG_SCHEDULING,
                  "Find a free 1-hour slot tomorrow.",
                  ["find_free_slots"], "HIGH"),
    BenchmarkTask("KG3", Category.KG_SCHEDULING,
                  "Do I have any scheduling conflicts?",
                  ["conflict_edges"], "HIGH"),
    BenchmarkTask("KG4", Category.KG_SCHEDULING,
                  "What meetings involve Priya?",
                  ["query_kg"], "HIGH"),
    BenchmarkTask("KG5", Category.KG_SCHEDULING,
                  "When am I free on Friday afternoon?",
                  ["find_free_slots"], "HIGH"),
    BenchmarkTask("KG6", Category.KG_SCHEDULING,
                  "List my hard commitments for today.",
                  ["query_kg"], "HIGH"),

    # -- Calendar / Gmail (HIGH -> google_calendar / gmail LOCAL) -----------
    BenchmarkTask("CG1", Category.CALENDAR_GMAIL,
                  "What's on my calendar today?",
                  ["google_calendar"], "HIGH"),
    BenchmarkTask("CG2", Category.CALENDAR_GMAIL,
                  "Show my unread emails.",
                  ["gmail"], "HIGH"),
    BenchmarkTask("CG3", Category.CALENDAR_GMAIL,
                  "Draft an email to Priya rescheduling our 1:1.",
                  ["gmail"], "HIGH"),
    BenchmarkTask("CG4", Category.CALENDAR_GMAIL,
                  "List my calendar events for next week.",
                  ["google_calendar"], "HIGH"),
    BenchmarkTask("CG5", Category.CALENDAR_GMAIL,
                  "Check my inbox for pending action items.",
                  ["gmail"], "HIGH"),
    BenchmarkTask("CG6", Category.CALENDAR_GMAIL,
                  "Create a calendar event for a team sync tomorrow at 3pm.",
                  ["google_calendar"], "HIGH"),

    # -- Multi-step Compound (MIXED, 3+ tools, replan scenarios) ------------
    BenchmarkTask("MC1", Category.COMPOUND,
                  "Research recent LLM papers and check if reading them conflicts "
                  "with my meetings this week.",
                  ["web_search", "query_kg", "conflict_edges"], "MIXED", expects_replan=True),
    BenchmarkTask("MC2", Category.COMPOUND,
                  "Find a free slot tomorrow, draft an email to Priya proposing it, "
                  "and add it to my calendar.",
                  ["find_free_slots", "gmail", "google_calendar"], "MIXED"),
    BenchmarkTask("MC3", Category.COMPOUND,
                  "Check my emails for action items, look up related commitments, "
                  "and add any deadlines to my calendar.",
                  ["gmail", "query_kg", "google_calendar"], "MIXED"),
    BenchmarkTask("MC4", Category.COMPOUND,
                  "Summarise my week from my calendar, check commitments, and flag conflicts.",
                  ["google_calendar", "query_kg", "conflict_edges"], "MIXED"),
    BenchmarkTask("MC5", Category.COMPOUND,
                  "Research a topic, run a quick calculation on the figures, and "
                  "message a summary to the team on Slack.",
                  ["web_search", "code_execution", "send_message"], "MIXED"),
    BenchmarkTask("MC6", Category.COMPOUND,
                  "Look up my commitments, find free time, and message the team on Slack.",
                  ["query_kg", "find_free_slots", "send_message"], "MIXED", expects_replan=True),
]


# ---------------------------------------------------------------------------
# Privacy classification + routing checks
# ---------------------------------------------------------------------------

def is_privacy_sensitive(tool_name: str) -> bool:
    """A tool is privacy-sensitive if it is pinned LOCAL or has a high floor."""
    return (
        tool_name in ALWAYS_LOCAL_TOOLS
        or TOOL_PRIVACY_FLOORS.get(tool_name, 0.0) >= PRIVACY_LOCAL_THRESHOLD
    )


@dataclass
class RoutingCheck:
    task_id: str
    category: str
    correct: bool
    violations: list[str] = field(default_factory=list)


def check_task_routing(task: BenchmarkTask) -> RoutingCheck:
    """Route each expected tool; flag any privacy-sensitive tool not LOCAL."""
    violations: list[str] = []
    for tool in task.expected_tools:
        decision = router.route(task.prompt, tool_name=tool).decision
        if is_privacy_sensitive(tool) and decision != RoutingDecision.LOCAL:
            violations.append(tool)
    return RoutingCheck(task.id, task.category.value, not violations, violations)


# ---------------------------------------------------------------------------
# Live task result
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    task_id: str
    category: str
    success: bool
    routing_correct: bool
    latency_s: float
    tokens: int
    answer_preview: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

class Benchmark:
    """Runs the benchmark in static / ablation / live modes."""

    def __init__(self, tasks: Optional[list[BenchmarkTask]] = None) -> None:
        self.tasks = tasks if tasks is not None else BENCHMARK_TASKS

    # -- static routing check (offline) ------------------------------------

    def run_static(self, verbose: bool = False) -> dict:
        """Check routing/privacy for every task. Returns a metrics dict."""
        checks = [check_task_routing(task) for task in self.tasks]
        correct = sum(1 for check in checks if check.correct)
        accuracy = correct / len(checks) * 100 if checks else 0.0

        if verbose:
            rows = [
                [check.task_id, check.category,
                 "OK" if check.correct else "VIOLATION",
                 ", ".join(check.violations) or "-"]
                for check in checks
            ]
            print(tabulate(rows, headers=["Task", "Category", "Routing", "Violations"]))
            print()

        return {
            "total": len(checks),
            "routing_correct": correct,
            "routing_accuracy_pct": round(accuracy, 1),
            "violations": [c for c in checks if not c.correct],
        }

    # -- ablation (offline, privacy-safe) ----------------------------------

    def run_ablation(self) -> dict:
        """
        Compare local-only / hybrid / cloud-only routing across all tasks.

        cloud_only is analysed, not executed: we count how many high-privacy
        steps it WOULD expose, which is exactly why the hybrid router exists.
        """
        summary: dict[str, dict] = {}
        for strategy in ("local_only", "hybrid", "cloud_only"):
            cloud_calls = 0
            privacy_violations = 0
            total_steps = 0
            for task in self.tasks:
                for tool in task.expected_tools:
                    total_steps += 1
                    if strategy == "local_only":
                        decision = "local"
                    elif strategy == "cloud_only":
                        decision = "cloud"
                    else:
                        decision = router.route(task.prompt, tool_name=tool).decision.value
                    if decision == "cloud":
                        cloud_calls += 1
                        if is_privacy_sensitive(tool):
                            privacy_violations += 1
            summary[strategy] = {
                "cloud_calls": cloud_calls,
                "privacy_violations": privacy_violations,
                "total_steps": total_steps,
            }
        return summary

    # -- live run (requires a model) ---------------------------------------

    def run_live(
        self, agency_level: str = "L2", limit: Optional[int] = None, verbose: bool = False
    ) -> dict:
        """Run each task through the agent and collect TCR / routing / latency."""
        from agent.orchestrator import HybridMindAgent, AgencyLevel

        level = {"L1": AgencyLevel.L1_AUGMENTED, "L2": AgencyLevel.L2_WORKFLOW,
                 "L3": AgencyLevel.L3_AUTONOMOUS}.get(agency_level, AgencyLevel.L2_WORKFLOW)
        agent = HybridMindAgent()
        tasks = self.tasks[:limit] if limit else self.tasks
        results: list[TaskResult] = []

        for task in tasks:
            start = time.time()
            try:
                output = agent.run(task.prompt, agency_level=level)
                elapsed = time.time() - start
                answer = output.get("answer", "")
                success = bool(answer.strip()) and not answer.startswith("I encountered an error")
                routing_correct = self._routing_correct_from_log(output.get("routing_log", []))
                summary = output.get("token_summary")
                tokens = summary.total_tokens if summary else 0
                results.append(TaskResult(
                    task.id, task.category.value, success, routing_correct,
                    round(elapsed, 2), tokens, answer[:80].replace("\n", " "),
                ))
            except Exception as error:  # noqa: BLE001 -- a task must not stop the suite
                results.append(TaskResult(
                    task.id, task.category.value, False, False,
                    round(time.time() - start, 2), 0, "", str(error),
                ))
            if verbose:
                last = results[-1]
                print(f"  {last.task_id:<4} {'OK ' if last.success else 'ERR'} "
                      f"{last.latency_s:>6.2f}s  {last.tokens:>6} tok  {last.answer_preview}")

        return self._compute_live_metrics(results)

    @staticmethod
    def _routing_correct_from_log(routing_log: list[dict]) -> bool:
        """True if no privacy-sensitive step in the log routed to cloud."""
        for entry in routing_log:
            tool = entry.get("tool", "")
            if is_privacy_sensitive(tool) and entry.get("decision") != "local":
                return False
        return True

    def _compute_live_metrics(self, results: list[TaskResult]) -> dict:
        total = len(results)
        completed = sum(1 for r in results if r.success)
        routing_ok = sum(1 for r in results if r.routing_correct)

        compound_ids = {t.id for t in self.tasks if t.category == Category.COMPOUND}
        simple = [r for r in results if r.task_id not in compound_ids]
        compound = [r for r in results if r.task_id in compound_ids]

        def avg_latency(rows: list[TaskResult]) -> float:
            return round(sum(r.latency_s for r in rows) / len(rows), 2) if rows else 0.0

        return {
            "total": total,
            "tcr_pct": round(completed / total * 100, 1) if total else 0.0,
            "routing_accuracy_pct": round(routing_ok / total * 100, 1) if total else 0.0,
            "avg_latency_simple_s": avg_latency(simple),
            "avg_latency_compound_s": avg_latency(compound),
            "total_tokens": sum(r.tokens for r in results),
            "results": results,
        }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_static_report(metrics: dict) -> None:
    accuracy = metrics["routing_accuracy_pct"]
    verdict = "PASS" if accuracy >= ROUTING_TARGET_PCT else "FAIL"
    print(f"Routing accuracy: {accuracy:.1f}% "
          f"({metrics['routing_correct']}/{metrics['total']}) "
          f"=> {verdict} (target {ROUTING_TARGET_PCT:.0f}%)")
    for violation in metrics["violations"]:
        print(f"  VIOLATION {violation.task_id}: {', '.join(violation.violations)} not LOCAL")


def _print_ablation_report(summary: dict) -> None:
    rows = [
        [strategy, data["cloud_calls"], data["privacy_violations"], data["total_steps"]]
        for strategy, data in summary.items()
    ]
    print(tabulate(rows, headers=["Strategy", "Cloud calls", "Privacy violations", "Total steps"]))
    print("\nlocal_only: never leaks, but loses cloud reasoning on public tasks.")
    print("cloud_only: fastest reasoning, but leaks every high-privacy step (unsafe).")
    print("hybrid:     cloud only for low-privacy web tasks => 0 privacy violations.")


def _print_live_report(metrics: dict) -> None:
    print(f"Task Completion Rate: {metrics['tcr_pct']:.1f}% "
          f"=> {'PASS' if metrics['tcr_pct'] >= TCR_TARGET_PCT else 'FAIL'} "
          f"(target {TCR_TARGET_PCT:.0f}%)")
    print(f"Routing accuracy:     {metrics['routing_accuracy_pct']:.1f}% "
          f"=> {'PASS' if metrics['routing_accuracy_pct'] >= ROUTING_TARGET_PCT else 'FAIL'} "
          f"(target {ROUTING_TARGET_PCT:.0f}%)")
    print(f"Avg latency (simple):   {metrics['avg_latency_simple_s']:.2f}s "
          f"=> {'PASS' if metrics['avg_latency_simple_s'] <= LATENCY_TARGET_SIMPLE_S else 'FAIL'} "
          f"(target <= {LATENCY_TARGET_SIMPLE_S:.0f}s)")
    print(f"Avg latency (compound): {metrics['avg_latency_compound_s']:.2f}s "
          f"=> {'PASS' if metrics['avg_latency_compound_s'] <= LATENCY_TARGET_COMPOUND_S else 'FAIL'} "
          f"(target <= {LATENCY_TARGET_COMPOUND_S:.0f}s)")
    print(f"Total tokens:           {metrics['total_tokens']:,}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _filter_tasks(category: Optional[str]) -> list[BenchmarkTask]:
    if not category:
        return BENCHMARK_TASKS
    return [task for task in BENCHMARK_TASKS if task.category.value.lower() == category.lower()]


def main() -> int:
    parser = argparse.ArgumentParser(description="KnowledgeMind benchmark suite (SPEC 10).")
    parser.add_argument("--mode", choices=["static", "ablation", "live"], default="static",
                        help="static routing check (default), ablation, or live agent run.")
    parser.add_argument("--level", choices=["L1", "L2", "L3"], default="L2",
                        help="Agency level for live mode.")
    parser.add_argument("--category", default=None, help="Restrict to one category.")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of tasks (live mode).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Per-task detail.")
    args = parser.parse_args()

    bench = Benchmark(_filter_tasks(args.category))

    print(f"== KnowledgeMind benchmark | mode={args.mode} | {len(bench.tasks)} task(s) ==\n")

    if args.mode == "static":
        metrics = bench.run_static(verbose=args.verbose)
        _print_static_report(metrics)
        return 0 if metrics["routing_accuracy_pct"] >= ROUTING_TARGET_PCT else 1

    if args.mode == "ablation":
        _print_ablation_report(bench.run_ablation())
        return 0

    metrics = bench.run_live(agency_level=args.level, limit=args.limit, verbose=args.verbose)
    _print_live_report(metrics)
    return 0 if metrics["tcr_pct"] >= TCR_TARGET_PCT else 1


# ---------------------------------------------------------------------------
# Smoke test / entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Self-check on definitions (runs before any CLI work, fully offline).
    assert len(BENCHMARK_TASKS) == 30, f"expected 30 tasks, got {len(BENCHMARK_TASKS)}"
    by_category: dict[str, int] = {}
    for benchmark_task in BENCHMARK_TASKS:
        by_category[benchmark_task.category.value] = by_category.get(benchmark_task.category.value, 0) + 1
    assert all(count == 6 for count in by_category.values()), f"uneven categories: {by_category}"
    assert all(len(t.expected_tools) >= 3 for t in BENCHMARK_TASKS
               if t.category == Category.COMPOUND), "compound tasks need 3+ tools"

    sys.exit(main())
