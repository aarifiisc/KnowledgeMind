"""
routing/router.py
-----------------
Privacy + complexity classifier. Decides whether a task step runs on the
LOCAL model (Ollama) or the CLOUD model (Groq).

PRIVACY-CRITICAL MODULE. The decision logic, the tool privacy floors, and the
ALWAYS_LOCAL_TOOLS set are implemented verbatim from SPEC.md 4.6 and the
privacy contract in SPEC.md 7. Do not add an override or force_cloud flag.
Do not remove a tool from ALWAYS_LOCAL_TOOLS without explicit approval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from config.store import get_config


# ---------------------------------------------------------------------------
# Decision enum + result
# ---------------------------------------------------------------------------

class RoutingDecision(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


@dataclass
class RoutingResult:
    """Outcome of routing a single task step (SPEC 3.2)."""
    decision: RoutingDecision
    privacy_score: float
    complexity_score: float
    reason: str
    tool_name: Optional[str]
    escalated: bool = False


# ---------------------------------------------------------------------------
# Privacy contract constants (SPEC 4.6 / 7) -- DO NOT WEAKEN
# ---------------------------------------------------------------------------

# Tools that prefer CLOUD when privacy is low (below threshold).
# These bypass the complexity check — low-privacy + this set = CLOUD.
PREFER_CLOUD_TOOLS: frozenset[str] = frozenset({
    "web_search",
})

# Tools that must always run LOCAL regardless of any score.
ALWAYS_LOCAL_TOOLS: frozenset[str] = frozenset({
    "query_kg",
    "find_free_slots",
    "conflict_edges",
    "google_calendar",
    "gmail",
    "send_message",
    "code_execution",
    # Hermes signal tools -- derived from personal health/fitness/tasks/music.
    "strava",
    "apple_health",
    "todoist",
    "spotify",
})

# Minimum privacy score a tool can ever have (floor), regardless of task text.
TOOL_PRIVACY_FLOORS: dict[str, float] = {
    "query_kg":        0.95,
    "find_free_slots": 0.95,
    "conflict_edges":  0.95,
    "google_calendar": 0.85,
    "gmail":           0.95,
    "send_message":    0.90,
    "code_execution":  0.70,
    "rag_query":       0.70,
    "web_search":      0.05,
    # Hermes signal tools -- personal biometrics/activity, pinned LOCAL.
    "apple_health":    0.98,
    "strava":          0.95,
    "spotify":         0.95,
    "todoist":         0.90,
}

# Privacy score at or above which a step is forced LOCAL (SPEC privacy rule 3).
PRIVACY_LOCAL_THRESHOLD: float = 0.65

# Heuristic signals that a task text concerns personal data.
_PERSONAL_SIGNALS: tuple[str, ...] = (
    "my ", "mine", "i have", "i am", "i'm", "remind me", "schedule",
    "calendar", "meeting", "email", "inbox", "message", "slack", "whatsapp",
    "appointment", "free slot", "free time", "availability", "commitment",
    "conflict", "priya", "boss", "team", "standup", "1:1", "call with",
)

# Heuristic signals that a task is complex / multi-step.
_COMPLEXITY_SIGNALS: tuple[str, ...] = (
    " and ", " then ", "compare", "summarise", "summarize", "analyse",
    "analyze", "research", "find out", "cross", "check if", "after",
    "before", "multiple", "each", "all of", "plan", "draft",
)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _privacy_score(task_text: str, tool_name: Optional[str]) -> float:
    """
    Heuristic privacy score in [0, 1], floored by the tool's privacy floor.

    A higher score means more personal/sensitive -> keep LOCAL.
    """
    text = task_text.lower()
    hits = sum(1 for signal in _PERSONAL_SIGNALS if signal in text)
    # Each signal adds 0.18, capped; base 0.10 so neutral text is low-privacy.
    heuristic = min(0.10 + 0.18 * hits, 1.0)

    floor = TOOL_PRIVACY_FLOORS.get(tool_name, 0.0) if tool_name else 0.0
    return max(heuristic, floor)


def _complexity_score(task_text: str) -> float:
    """Heuristic complexity score in [0, 1]. Higher means more multi-step."""
    text = task_text.lower()
    hits = sum(1 for signal in _COMPLEXITY_SIGNALS if signal in text)
    word_count = len(re.findall(r"\w+", text))

    length_component = min(word_count / 40.0, 0.5)   # up to 0.5 for long tasks
    signal_component = min(0.15 * hits, 0.5)         # up to 0.5 for step words
    return min(length_component + signal_component, 1.0)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class Router:
    """Stateless privacy/complexity router. One shared instance is exported."""

    def route(self, task_text: str, tool_name: Optional[str] = None) -> RoutingResult:
        """
        Classify a task step as LOCAL or CLOUD.

        Args:
            task_text: the step instruction / user text being routed.
            tool_name: the tool this step will call, if known.
        Returns:
            RoutingResult with decision, both scores, and a human reason.
        """
        cfg = get_config()
        threshold = cfg.complexity_threshold

        privacy = _privacy_score(task_text, tool_name)
        complexity = _complexity_score(task_text)

        # --- Decision logic, verbatim from SPEC 4.6 -------------------------
        if tool_name in ALWAYS_LOCAL_TOOLS:
            return RoutingResult(
                decision=RoutingDecision.LOCAL,
                privacy_score=privacy,
                complexity_score=complexity,
                reason=f"'{tool_name}' is in ALWAYS_LOCAL_TOOLS (privacy-pinned).",
                tool_name=tool_name,
            )

        if tool_name in PREFER_CLOUD_TOOLS and privacy < PRIVACY_LOCAL_THRESHOLD:
            return RoutingResult(
                decision=RoutingDecision.CLOUD,
                privacy_score=privacy,
                complexity_score=complexity,
                reason=(
                    f"'{tool_name}' prefers CLOUD and privacy score {privacy:.2f} "
                    f"< {PRIVACY_LOCAL_THRESHOLD} -> CLOUD."
                ),
                tool_name=tool_name,
            )

        if privacy >= PRIVACY_LOCAL_THRESHOLD:
            return RoutingResult(
                decision=RoutingDecision.LOCAL,
                privacy_score=privacy,
                complexity_score=complexity,
                reason=f"Privacy score {privacy:.2f} >= {PRIVACY_LOCAL_THRESHOLD} -> LOCAL.",
                tool_name=tool_name,
            )

        if complexity >= threshold and privacy < PRIVACY_LOCAL_THRESHOLD:
            return RoutingResult(
                decision=RoutingDecision.CLOUD,
                privacy_score=privacy,
                complexity_score=complexity,
                reason=(
                    f"Low privacy ({privacy:.2f}) and complexity {complexity:.2f} "
                    f">= threshold {threshold:.2f} -> CLOUD."
                ),
                tool_name=tool_name,
            )

        # Conservative default: when in doubt, LOCAL.
        return RoutingResult(
            decision=RoutingDecision.LOCAL,
            privacy_score=privacy,
            complexity_score=complexity,
            reason="Default conservative route -> LOCAL.",
            tool_name=tool_name,
        )


# Shared singleton imported across the agent layer.
router = Router()


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Privacy-pinned tools must always be LOCAL, even with high complexity text.
    for pinned in sorted(ALWAYS_LOCAL_TOOLS):
        result = router.route("research and compare and analyse everything", pinned)
        assert result.decision == RoutingDecision.LOCAL, f"{pinned} routed to cloud!"
    print(f"=> all {len(ALWAYS_LOCAL_TOOLS)} ALWAYS_LOCAL_TOOLS stay LOCAL")

    # web_search goes CLOUD for any low-privacy query (short or long).
    for query in [
        "what is the capital of France",
        "research and compare the latest LLM benchmark papers",
    ]:
        web = router.route(query, "web_search")
        print(f"=> web_search ({query[:40]}...): {web.decision.value} "
              f"(privacy={web.privacy_score:.2f}, complexity={web.complexity_score:.2f})")
        assert web.decision == RoutingDecision.CLOUD, f"expected web_search -> CLOUD for: {query}"

    # web_search stays LOCAL when the query contains enough personal signals (>= 0.65).
    personal_web = router.route("search my calendar for my meetings with my team", "web_search")
    print(f"=> web_search (personal): {personal_web.decision.value} "
          f"(privacy={personal_web.privacy_score:.2f})")
    assert personal_web.decision == RoutingDecision.LOCAL, "personal web_search should stay LOCAL"

    # A personal query with no tool must stay LOCAL on privacy score.
    personal = router.route("what meetings do I have on my calendar tomorrow", None)
    assert personal.decision == RoutingDecision.LOCAL, "personal query leaked to cloud!"
    print(f"=> personal query: {personal.decision.value} (privacy={personal.privacy_score:.2f})")

    print("All routing/router.py smoke tests passed.")
