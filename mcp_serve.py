"""
mcp_serve.py
------------
KnowledgeMind MCP server.

Exposes all KG tools AND the four new connector tools (Strava, Apple Health,
Todoist, Spotify) as a single MCP server that Hermes Agent connects to.

Privacy enforcement runs HERE, inside this process, before any tool executes.
The routing/router.py contract is asserted on every call — no KG or personal
data reaches any cloud model via this path.

Usage:
    python mcp_serve.py              # listens on default port 6789
    python mcp_serve.py --port 7000

Hermes cli-config.yaml:
    mcp_servers:
      - name: knowledgemind
        url: http://localhost:6789/mcp
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure repo root is importable when run directly
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from mcp.server.fastmcp import FastMCP

from agent.tools import dispatch_tool
from config.store import get_config
from routing.router import router, RoutingDecision, ALWAYS_LOCAL_TOOLS
from hermes_tools.strava_tool import strava_summary
from hermes_tools.apple_health_tool import apple_health_summary
from hermes_tools.todoist_tool import todoist_summary, todoist_tasks
from hermes_tools.spotify_tool import spotify_mood

mcp = FastMCP("KnowledgeMind")


# ---------------------------------------------------------------------------
# Privacy guard
# ---------------------------------------------------------------------------

def _assert_local(tool_name: str, query: str = "") -> None:
    """
    Raise RuntimeError if the privacy router would route this tool to CLOUD.
    This is a defence-in-depth check — the router already enforces ALWAYS_LOCAL
    for these tools, but we assert explicitly so any future misconfiguration
    surfaces as a hard error rather than a silent data leak.
    """
    result = router.route(query or tool_name, tool_name=tool_name)
    if result.decision != RoutingDecision.LOCAL:
        raise RuntimeError(
            f"Privacy violation: tool '{tool_name}' routed to CLOUD "
            f"(privacy={result.privacy_score:.2f}). Refusing to execute."
        )


# ---------------------------------------------------------------------------
# KG tools (wrapping existing agent/tools.py)
# ---------------------------------------------------------------------------

@mcp.tool()
def km_query_kg(query: str) -> dict:
    """
    Query the personal knowledge graph for commitments, persons, and events.
    Always LOCAL — personal data never leaves this process.
    """
    _assert_local("query_kg", query)
    return dispatch_tool("query_kg", {"query": query})


@mcp.tool()
def km_find_free_slots(date: str = "", duration_minutes: int = 60) -> dict:
    """
    Find free time slots on a given date (YYYY-MM-DD).
    Returns available windows of the requested duration. Always LOCAL.
    """
    _assert_local("find_free_slots")
    return dispatch_tool("find_free_slots", {
        "date": date,
        "duration_minutes": duration_minutes,
    })


@mcp.tool()
def km_conflict_edges(days: int = 7) -> dict:
    """
    Return commitment conflicts detected in the knowledge graph
    within the next `days` days. Always LOCAL.
    """
    _assert_local("conflict_edges")
    return dispatch_tool("conflict_edges", {"days": days})


@mcp.tool()
def km_calendar(action: str = "list") -> dict:
    """
    Read Google Calendar events.
    action: "list" — upcoming events. Always LOCAL.
    """
    _assert_local("google_calendar")
    return dispatch_tool("google_calendar", {"action": action})


@mcp.tool()
def km_gmail(action: str = "list", query: str = "is:unread") -> dict:
    """
    Read Gmail inbox or draft a message (action: "list" | "draft").
    Sending always requires UI confirmation — this tool never sends.
    Always LOCAL.
    """
    _assert_local("gmail")
    return dispatch_tool("gmail", {"action": action, "query": query})


# ---------------------------------------------------------------------------
# New connector tools (Strava, Apple Health, Todoist, Spotify)
# ---------------------------------------------------------------------------

@mcp.tool()
def km_strava_summary() -> dict:
    """
    Return fitness signals derived from Strava recent activities.
    Signals: days since last activity, weekly run km, gap threshold flag.
    Raw GPS routes and activity names never leave this process. Always LOCAL.
    """
    _assert_local("strava_summary")
    return strava_summary()


@mcp.tool()
def km_apple_health_summary(date: str = "") -> dict:
    """
    Return health signals from the Apple Health iCloud export for `date`
    (YYYY-MM-DD, or empty string for today).
    Signals: sleep quality, recovery status, low HRV flag, high resting HR flag.
    Raw biometric values are never forwarded to any model. Always LOCAL.
    """
    _assert_local("apple_health_summary")
    return apple_health_summary(date=date or None)


@mcp.tool()
def km_todoist_summary() -> dict:
    """
    Return task-load summary from Todoist (overdue count, due today, top tasks).
    Full task titles included — processed by local model only. Always LOCAL.
    """
    _assert_local("todoist_summary")
    return todoist_summary()


@mcp.tool()
def km_todoist_tasks(filter_str: str = "today | overdue") -> dict:
    """
    Return full task list matching a Todoist filter string.
    Includes titles, descriptions, priorities, due dates. Always LOCAL.
    """
    _assert_local("todoist_tasks")
    return todoist_tasks(filter_str=filter_str)


@mcp.tool()
def km_spotify_mood() -> dict:
    """
    Return mood signal derived from Spotify audio features.
    Track names and artist names are NEVER extracted or returned.
    Only valence/energy-derived mood label and session duration. Always LOCAL.
    """
    _assert_local("spotify_mood")
    return spotify_mood()


# ---------------------------------------------------------------------------
# Health check tool (used by Hermes to verify the server is up)
# ---------------------------------------------------------------------------

@mcp.tool()
def km_health() -> dict:
    """Return server health status and available tool list."""
    cfg = get_config()
    return {
        "status": "ok",
        "mcp_port": cfg.km_mcp_port,
        "tools": [
            "km_query_kg", "km_find_free_slots", "km_conflict_edges",
            "km_calendar", "km_gmail",
            "km_strava_summary", "km_apple_health_summary",
            "km_todoist_summary", "km_todoist_tasks",
            "km_spotify_mood",
        ],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="KnowledgeMind MCP server")
    parser.add_argument(
        "--port", type=int, default=None,
        help="Port to listen on (default: km_mcp_port from config, usually 6789)",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1 — localhost only)",
    )
    args = parser.parse_args()

    cfg = get_config()
    port = args.port or cfg.km_mcp_port

    print(f"[MCP] KnowledgeMind MCP server starting on {args.host}:{port}")
    print(f"[MCP] Privacy router active — all personal tools pinned LOCAL")
    print(f"[MCP] Tools: km_query_kg, km_find_free_slots, km_conflict_edges, "
          f"km_calendar, km_gmail, km_strava_summary, km_apple_health_summary, "
          f"km_todoist_summary, km_todoist_tasks, km_spotify_mood")

    # FastMCP serves over stdio (default MCP transport) or HTTP.
    # For Hermes's HTTP MCP backend, run with transport="streamable-http".
    mcp.run(transport="streamable-http", host=args.host, port=port, path="/mcp")


if __name__ == "__main__":
    main()
