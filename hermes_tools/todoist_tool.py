"""
hermes_tools/todoist_tool.py
-----------------------------
Todoist task tool — exposed as MCP tools `todoist_summary` and `todoist_tasks`.

Full task titles and descriptions are returned because this tool is processed
only by the local Hermes model (nous-hermes3 via Ollama) — never a cloud model.
Privacy floor: 0.90 (ALWAYS_LOCAL).
"""

from __future__ import annotations

from connectors.todoist import TodoistConnector, derive_todoist_signals
from kg.connector_store import record_todoist


def todoist_summary() -> dict:
    """
    Return a task-load summary from Todoist.

    Full task content is included — processed locally only.

    Returns:
        {
            "success": bool,
            "total": int,
            "overdue_count": int,
            "due_today_count": int,
            "heavy_day": bool,
            "clear_day": bool,
            "top_tasks": list[str],         # titles of highest-priority items
            "overdue_tasks": list[str],
            "due_today_tasks": list[str],
            "summary": str,
            "source": "live" | "mock",
        }
    """
    connector = TodoistConnector()

    if connector.health_check():
        tasks = connector.get_tasks(filter_str="today | overdue")
        source = "live"
    else:
        tasks = connector.load_mock()
        source = "mock"

    signals = derive_todoist_signals(tasks)
    result = {"success": True, "source": source, **signals}
    try:
        record_todoist(result)
    except Exception:
        pass
    return result


def todoist_tasks(filter_str: str = "today | overdue") -> dict:
    """
    Return raw task list for a Todoist filter string.

    Full task titles, descriptions, priorities and due dates are returned
    because this is a LOCAL-only tool.

    Args:
        filter_str: any valid Todoist filter (e.g. "today", "overdue", "p1").

    Returns:
        {
            "success": bool,
            "tasks": list[dict],    # full Todoist task objects
            "count": int,
            "source": "live" | "mock",
        }
    """
    connector = TodoistConnector()

    if connector.health_check():
        tasks = connector.get_tasks(filter_str=filter_str)
        source = "live"
    else:
        tasks = connector.load_mock()
        source = "mock"

    return {"success": True, "tasks": tasks, "count": len(tasks), "source": source}


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    summary = todoist_summary()
    assert summary["success"] is True
    assert "overdue_count" in summary
    assert "due_today_count" in summary
    print(f"=> source          : {summary['source']}")
    print(f"=> total           : {summary['total']}")
    print(f"=> overdue_count   : {summary['overdue_count']}")
    print(f"=> due_today_count : {summary['due_today_count']}")
    print(f"=> heavy_day       : {summary['heavy_day']}")
    print(f"=> summary         : {summary['summary']}")

    tasks = todoist_tasks("today | overdue")
    assert tasks["success"] is True
    print(f"=> todoist_tasks count : {tasks['count']}")
    print("All hermes_tools/todoist_tool.py smoke tests passed.")
