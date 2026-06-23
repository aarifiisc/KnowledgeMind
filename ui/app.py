"""
ui/app.py
---------
Main Gradio UI for KnowledgeMind.

Five tabs:
  1. Chat      — message input + agency level selector + routing log + token panel
  2. KG View   — live pyvis knowledge graph
  3. Monitor   — FSM status + alert feed
  4. Documents — RAG file upload + indexed doc list
  5. Settings  — re-expose config (model, keys)
"""

from __future__ import annotations

import html as html_lib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gradio as gr
from config.store import get_config, save_config, reload_config, AppConfig
from agent.orchestrator import HybridMindAgent, AgencyLevel, LEVEL_LABELS

# ---------------------------------------------------------------------------
# Global agent (one per UI session — Gradio shares state across requests
# via gr.State, but agent holds session_id so we use one per browser session)
# ---------------------------------------------------------------------------

_AGENT: HybridMindAgent | None = None

def get_agent() -> HybridMindAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = HybridMindAgent()
    return _AGENT


# ---------------------------------------------------------------------------
# Level trade-off table (from course slides — static reference)
# ---------------------------------------------------------------------------

LEVEL_TRADEOFF_HTML = """
<table style="width:100%; font-size:0.82em; border-collapse:collapse">
  <thead>
    <tr style="background:#1B3A6B; color:white">
      <th style="padding:6px 8px; text-align:left">Dimension</th>
      <th style="padding:6px 8px; text-align:center">L1 Augmented</th>
      <th style="padding:6px 8px; text-align:center">L2 Workflow</th>
      <th style="padding:6px 8px; text-align:center">L3 Autonomous</th>
    </tr>
  </thead>
  <tbody>
    <tr style="background:#EBF3FB">
      <td style="padding:5px 8px">Autonomy</td>
      <td style="padding:5px 8px; text-align:center">🟢 Low</td>
      <td style="padding:5px 8px; text-align:center">🟡 Medium</td>
      <td style="padding:5px 8px; text-align:center">🔴 High</td>
    </tr>
    <tr>
      <td style="padding:5px 8px">Predictability</td>
      <td style="padding:5px 8px; text-align:center">🟢 High</td>
      <td style="padding:5px 8px; text-align:center">🟡 Medium</td>
      <td style="padding:5px 8px; text-align:center">🔴 Low</td>
    </tr>
    <tr style="background:#EBF3FB">
      <td style="padding:5px 8px">Token Cost</td>
      <td style="padding:5px 8px; text-align:center">🟢 Low</td>
      <td style="padding:5px 8px; text-align:center">🟡 Medium</td>
      <td style="padding:5px 8px; text-align:center">🔴 High</td>
    </tr>
    <tr>
      <td style="padding:5px 8px">Flexibility</td>
      <td style="padding:5px 8px; text-align:center">🔴 Low</td>
      <td style="padding:5px 8px; text-align:center">🟡 Medium</td>
      <td style="padding:5px 8px; text-align:center">🟢 High</td>
    </tr>
    <tr style="background:#EBF3FB">
      <td style="padding:5px 8px">Control Flow</td>
      <td style="padding:5px 8px; text-align:center" colspan="2">Engineer-defined</td>
      <td style="padding:5px 8px; text-align:center">LLM-directed</td>
    </tr>
    <tr>
      <td style="padding:5px 8px">Replanning</td>
      <td style="padding:5px 8px; text-align:center">None</td>
      <td style="padding:5px 8px; text-align:center">None</td>
      <td style="padding:5px 8px; text-align:center">Up to 3×</td>
    </tr>
    <tr style="background:#EBF3FB">
      <td style="padding:5px 8px">Typical tokens</td>
      <td style="padding:5px 8px; text-align:center">~650</td>
      <td style="padding:5px 8px; text-align:center">~1,800</td>
      <td style="padding:5px 8px; text-align:center">~4,500</td>
    </tr>
  </tbody>
</table>
<p style="font-size:0.75em; color:#888; margin:4px 0 0 0">
Note: token counts are highly use-case dependent. L3 agents can replan up to 3 times, so may consume more tokens than L2.
</p>
"""


# ---------------------------------------------------------------------------
# Routing log renderer
# ---------------------------------------------------------------------------

def _render_routing_log(routing_log: list[dict]) -> str:
    if not routing_log:
        return ""
    lines = ["**Routing Decisions:**\n"]
    for log in routing_log:
        decision = log["decision"].upper()
        badge    = "🟢 LOCAL" if decision == "LOCAL" else "🟡 CLOUD"
        escalated = " ↑escalated" if log.get("escalated") else ""
        lines.append(
            f"Step {log['step_id']} &nbsp;|&nbsp; `{log['tool']}` → **{badge}{escalated}**  "
            f"*(privacy={log['privacy_score']:.2f}, complexity={log['complexity_score']:.2f})*\n"
            f"&nbsp;&nbsp;&nbsp;&nbsp;_{log['reason']}_"
        )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Token panel renderer
# ---------------------------------------------------------------------------

def _render_token_panel(token_summary, agency_level: str) -> str:
    if token_summary is None:
        return ""

    level_emoji = {"L1": "⚡", "L2": "⚙️", "L3": "🤖"}.get(agency_level, "")
    header = f"**{level_emoji} Token Consumption — {token_summary.level_label}**\n\n"
    body = f"```\n{token_summary.formatted_breakdown()}\n```"
    return header + body


# ---------------------------------------------------------------------------
# Chat handler
# ---------------------------------------------------------------------------

# Map radio label -> AgencyLevel enum.
_LEVEL_MAP = {
    "L1 — Augmented LLM (single call, lowest tokens)":   AgencyLevel.L1_AUGMENTED,
    "L2 — Workflow (plan→execute→critique)":             AgencyLevel.L2_WORKFLOW,
    "L3 — Autonomous Agent (ReAct loop, most capable)":  AgencyLevel.L3_AUTONOMOUS,
}


def _message_text(content) -> str:
    """Extract plain text from a gradio message 'content' (str or parts list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def user_turn(message: str, history: list) -> tuple[str, list]:
    """
    Step 1 (instant): echo the user's message into the chat and clear the box,
    BEFORE the agent runs. Returns (cleared_input, updated_history).
    """
    if not message.strip():
        return message, history
    history = (history or []) + [{"role": "user", "content": message}]
    return "", history


def bot_turn(
    history: list,
    agency_level_str: str,
    show_routing: bool,
    show_tokens: bool,
) -> tuple[list, str, str]:
    """
    Step 2 (after echo): run the agent on the latest user message and append the
    reply. Returns (updated_history, routing_md, token_md).
    """
    if not history:
        return history, "", ""
    message = _message_text(history[-1].get("content", ""))

    agent = get_agent()
    agency_level = _LEVEL_MAP.get(agency_level_str, AgencyLevel.L2_WORKFLOW)
    result = agent.run(message, agency_level=agency_level)

    answer        = result.get("answer", "No answer returned.")
    routing_log   = result.get("routing_log", [])
    token_summary = result.get("token_summary")
    elapsed       = result.get("elapsed", 0)
    al            = result.get("agency_level", "L2")
    step_count    = len(routing_log)

    step_str = f"{step_count} tool call{'s' if step_count != 1 else ''}" if step_count else "direct answer"
    meta = f"\n\n---\n*{LEVEL_LABELS.get(agency_level, al)} · {step_str} · {elapsed:.1f}s · Session: {agent.session_id}*"

    history = history + [{"role": "assistant", "content": answer + meta}]
    routing_md = _render_routing_log(routing_log) if show_routing else ""
    token_md   = _render_token_panel(token_summary, al) if show_tokens else ""
    return history, routing_md, token_md


# ---------------------------------------------------------------------------
# Document upload
# ---------------------------------------------------------------------------

def upload_document(file) -> str:
    if file is None:
        return "No file selected."
    agent = get_agent()
    result = agent.add_document(file.name)
    added   = result.get("added", [])
    skipped = result.get("skipped", [])
    chunks  = result.get("chunks", 0)
    parts = []
    if added:
        parts.append(f"✓ Indexed: {', '.join(added)} ({chunks} chunks)")
    if skipped:
        parts.append(f"⚠ Skipped: {', '.join(skipped)}")
    return "\n".join(parts) if parts else "Nothing indexed."


def list_documents() -> str:
    try:
        from tools.rag import rag_tool
        docs = rag_tool.list_documents()
        if not docs:
            return "No documents indexed yet."
        return "**Indexed documents:**\n" + "\n".join(f"• {d}" for d in docs)
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Gmail send-confirmation gate (PRIVACY rule 6 / rule 4)
# ---------------------------------------------------------------------------

def send_email(to: str, subject: str, body: str, confirmed: bool) -> str:
    """
    The ONLY path in the system that actually sends email. The agent's `gmail`
    tool refuses `send`; sending requires the user to tick the confirmation box
    and click Send here. This gate must never be reachable from an agent tool.
    """
    if not confirmed:
        return "Tick 'I confirm sending this email' first."
    if not to.strip() or not body.strip():
        return "Recipient and body are required."
    from connectors.gmail import GmailConnector
    connector = GmailConnector()
    if not connector.health_check():
        return "Gmail not connected. Connect Google in Settings first."
    result = connector.send_message(to.strip(), subject.strip(), body)
    if result.get("success"):
        return f"✓ Sent to {to.strip()} (message id {result.get('id')})."
    return f"Send failed: {result.get('error')}"


# ---------------------------------------------------------------------------
# KG Visualisation
# ---------------------------------------------------------------------------

def render_kg() -> str:
    """Render the KG as a pyvis HTML graph and return as HTML string."""
    try:
        from pyvis.network import Network
        import networkx as nx
        from kg.graph import build_graph
        from kg.schema import get_db_connection
        from config.store import get_config

        cfg = get_config()
        conn = get_db_connection(cfg.db_path)
        G = build_graph(conn)
        conn.close()

        if len(G.nodes) == 0:
            return "<p style='color:#888; padding:20px'>Knowledge graph is empty. Connect a data source or load mock data.</p>"

        # cdn_resources='remote': load vis.js from a CDN instead of local
        # lib/ files (which do not exist on the gradio server).
        net = Network(height="400px", width="100%", bgcolor="#f8f9fa",
                      font_color="#1B3A6B", cdn_resources="remote")
        net.from_nx(G)

        # Style nodes by type
        for node in net.nodes:
            ntype = node.get("type", "")
            if ntype == "Person":
                node["color"] = "#2E6DB4"
                node["size"]  = 20
            elif ntype == "Commitment":
                ctype = node.get("commitment_type", "")
                node["color"] = "#1A6B3A" if ctype == "HARD" else "#E07B00" if ctype == "SOFT" else "#888888"
                node["size"]  = 14
            elif ntype == "TimeSlot":
                node["color"] = "#8B0000"
                node["size"]  = 10

        net.set_options('{"physics": {"stabilization": {"iterations": 100}}}')
        document = net.generate_html(notebook=False)

        # Embed in an iframe via srcdoc so the vis.js <script> tags actually
        # execute (scripts injected directly into gr.HTML do not run).
        return (
            f'<iframe srcdoc="{html_lib.escape(document, quote=True)}" '
            f'style="width:100%; height:430px; border:none;"></iframe>'
        )

    except Exception as e:
        return f"<p style='color:red; padding:20px'>KG render error: {e}</p>"


# ---------------------------------------------------------------------------
# Monitor panel
# ---------------------------------------------------------------------------

def get_monitor_status() -> str:
    cfg = get_config()
    alerts_path = Path(cfg.alerts_log_path)
    if not alerts_path.exists():
        return "No alerts yet. Monitor loop hasn't run or no conflicts detected."

    try:
        lines = alerts_path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return "No alerts yet."
        # Show last 10 alerts
        recent = lines[-10:]
        formatted = []
        for line in reversed(recent):
            try:
                alert = json.loads(line)
                ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(alert.get("timestamp", 0)))
                formatted.append(f"**{ts}** — {alert.get('message', 'Alert')}")
            except json.JSONDecodeError:
                formatted.append(line)
        return "\n\n".join(formatted)
    except Exception as e:
        return f"Error reading alerts: {e}"


def get_monitor_state() -> str:
    """Render the FSM status indicator + last poll time for the Monitor tab."""
    from monitor.fsm import monitor_runner

    state = monitor_runner.latest_state
    if state is None:
        return "**FSM status:** idle — no cycle has run yet."

    last_poll = monitor_runner.last_poll_ts
    when = (
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_poll))
        if last_poll else "never"
    )
    status = "ERROR" if state.get("error") else "OK"
    lines = [
        f"**FSM status:** {status}",
        f"**Cycles run:** {state.get('cycle_count', 0)}",
        f"**Last poll:** {when}",
        (f"**Last cycle:** {len(state.get('new_messages', []))} msgs, "
         f"{len(state.get('new_commitments', []))} commitments, "
         f"{len(state.get('new_conflicts', []))} conflicts, "
         f"{state.get('alerts_fired', 0)} alerts"),
    ]
    if state.get("error"):
        lines.append(f"**Error:** {state['error']}")
    return "  \n".join(lines)


def run_monitor_cycle() -> tuple[str, str]:
    """Manual poll trigger: run one FSM cycle, then refresh state + alert feed."""
    from monitor.fsm import monitor_runner

    monitor_runner.run_once()
    return get_monitor_state(), get_monitor_status()


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def reset_session() -> tuple[list, str, str, str]:
    global _AGENT
    _AGENT = HybridMindAgent()
    return [], "", "", f"Session reset. New ID: {_AGENT.session_id}"


# ---------------------------------------------------------------------------
# Connector tab helpers
# ---------------------------------------------------------------------------

_CONNECTOR_LABELS = {
    "discord":      ("💬", "Discord"),
    "strava":       ("🏃", "Strava"),
    "apple_health": ("❤️", "Apple Health"),
    "todoist":      ("✅", "Todoist"),
    "spotify":      ("🎵", "Spotify"),
}


def _ts(unix: float | None) -> str:
    if not unix:
        return "never"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(unix))


def _status_badge(source: str | None, success: bool) -> str:
    if not success:
        return "🔴 error"
    if source == "live":
        return "🟢 live"
    if source == "mock":
        return "🟡 mock"
    return "⚪ unknown"


def get_connector_overview() -> str:
    """Render a markdown summary card for each connector."""
    try:
        from kg.connector_store import get_latest_run, get_run_counts
        counts = get_run_counts()
        lines = ["| Connector | Status | Last poll | Total polls |",
                 "|-----------|--------|-----------|-------------|"]
        for key, (icon, label) in _CONNECTOR_LABELS.items():
            run = get_latest_run(key)
            if run:
                badge = _status_badge(run["source"], bool(run["success"]))
                when  = _ts(run["polled_at"])
            else:
                badge = "⚪ not polled"
                when  = "—"
            cnt = counts.get(key, 0)
            lines.append(f"| {icon} {label} | {badge} | {when} | {cnt} |")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not load connector overview: {e}"


def _format_history_table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "_No data yet. Click Refresh to poll._"
    header = "| " + " | ".join(columns) + " |"
    sep    = "|" + "|".join("---" for _ in columns) + "|"
    body_lines = []
    for r in rows:
        vals = []
        for c in columns:
            v = r.get(c)
            if c == "polled_at":
                v = _ts(v)
            elif isinstance(v, float):
                v = f"{v:.2f}"
            elif isinstance(v, bool) or c in ("gap_threshold_exceeded", "heavy_day",
                                               "clear_day", "low_hrv", "high_rhr",
                                               "deep_work_session"):
                v = "yes" if v else "no"
            elif v is None:
                v = "—"
            elif c == "top_tasks":
                try:
                    tasks = json.loads(v) if isinstance(v, str) else v
                    v = "; ".join(tasks[:2]) if tasks else "—"
                except Exception:
                    pass
            vals.append(str(v))
        body_lines.append("| " + " | ".join(vals) + " |")
    return "\n".join([header, sep] + body_lines)


def refresh_strava() -> tuple[str, str]:
    try:
        from hermes_tools.strava_tool import strava_summary
        from kg.connector_store import get_history
        r = strava_summary()
        summary = (
            f"**Last activity:** {r.get('last_activity_type', '?')} on "
            f"{r.get('last_activity_date', '?')}  \n"
            f"**Days since:** {r.get('days_since_last_activity', '?')}  \n"
            f"**Weekly km:** {r.get('weekly_run_km', '?')}  \n"
            f"**Gap exceeded:** {'yes' if r.get('gap_threshold_exceeded') else 'no'}  \n"
            f"**Source:** {r.get('source', '?')}\n\n"
            f"_{r.get('summary', '')}_"
        )
        cols = ["polled_at", "days_since_last_activity", "last_activity_type",
                "last_activity_date", "weekly_run_km", "weekly_vs_4w_avg",
                "gap_threshold_exceeded", "source"]
        hist = _format_history_table(get_history("strava"), cols)
        return summary, hist
    except Exception as e:
        return f"Error: {e}", ""


def refresh_apple_health() -> tuple[str, str]:
    try:
        from hermes_tools.apple_health_tool import apple_health_summary
        from kg.connector_store import get_history
        r = apple_health_summary()
        summary = (
            f"**Date:** {r.get('date', '?')}  \n"
            f"**Sleep:** {r.get('sleep_hours', '?')}h ({r.get('sleep_quality', '?')})  \n"
            f"**Recovery:** {r.get('recovery_status', '?')}  \n"
            f"**Low HRV:** {'yes' if r.get('low_hrv') else 'no'}  \n"
            f"**Steps:** {r.get('steps', '?')}  \n"
            f"**Source:** {r.get('source', '?')}\n\n"
            f"_{r.get('summary', '')}_"
        )
        cols = ["polled_at", "health_date", "sleep_quality", "sleep_hours",
                "recovery_status", "low_hrv", "high_rhr", "steps", "source"]
        hist = _format_history_table(get_history("apple_health"), cols)
        return summary, hist
    except Exception as e:
        return f"Error: {e}", ""


def refresh_todoist() -> tuple[str, str]:
    try:
        from hermes_tools.todoist_tool import todoist_summary
        from kg.connector_store import get_history
        r = todoist_summary()
        top = "; ".join((r.get("top_tasks") or [])[:3]) or "—"
        summary = (
            f"**Overdue:** {r.get('overdue_count', 0)}  \n"
            f"**Due today:** {r.get('due_today_count', 0)}  \n"
            f"**Heavy day:** {'yes' if r.get('heavy_day') else 'no'}  \n"
            f"**Top tasks:** {top}  \n"
            f"**Source:** {r.get('source', '?')}\n\n"
            f"_{r.get('summary', '')}_"
        )
        cols = ["polled_at", "total", "overdue_count", "due_today_count",
                "heavy_day", "clear_day", "top_tasks", "source"]
        hist = _format_history_table(get_history("todoist"), cols)
        return summary, hist
    except Exception as e:
        return f"Error: {e}", ""


def refresh_spotify() -> tuple[str, str]:
    try:
        from hermes_tools.spotify_tool import spotify_mood
        from kg.connector_store import get_history
        r = spotify_mood()
        summary = (
            f"**Mood:** {r.get('mood', '?')}  \n"
            f"**Valence / Energy:** {r.get('avg_valence', '?'):.2f} / "
            f"{r.get('avg_energy', '?'):.2f}  \n"
            f"**Deep work session:** {'yes' if r.get('deep_work_session') else 'no'}  \n"
            f"**Session:** {r.get('session_minutes', '?')} min  \n"
            f"**Source:** {r.get('source', '?')}\n\n"
            f"_{r.get('summary', '')}_"
        )
        cols = ["polled_at", "mood", "avg_valence", "avg_energy",
                "deep_work_session", "session_minutes", "source"]
        hist = _format_history_table(get_history("spotify"), cols)
        return summary, hist
    except Exception as e:
        return f"Error: {e}", ""


def refresh_discord() -> tuple[str, str]:
    """Discord is polled by the Hermes gateway; show last stored snapshot."""
    try:
        from kg.connector_store import get_latest, get_history
        cfg = get_config()
        if not cfg.discord_bot_token:
            return "**Status:** not configured — add a Discord bot token in Settings.", ""
        r = get_latest("discord")
        if not r:
            return "**Status:** token configured, no polls recorded yet.", ""
        summary = (
            f"**Last poll:** {_ts(r.get('polled_at'))}  \n"
            f"**Unread DMs:** {r.get('unread_count', 0)}  \n"
            f"**Mentions:** {r.get('mention_count', 0)}  \n"
            f"**Oldest unread:** {r.get('oldest_unread_hours', '?')}h  \n"
            f"**Source:** {r.get('source', '?')}"
        )
        cols = ["polled_at", "unread_count", "mention_count",
                "oldest_unread_hours", "source"]
        hist = _format_history_table(get_history("discord"), cols)
        return summary, hist
    except Exception as e:
        return f"Error: {e}", ""


def refresh_all_connectors() -> tuple[str, str, str, str, str, str, str, str, str, str, str]:
    """Refresh all connectors and return (overview, s_sum, s_hist, h_sum, h_hist,
    t_sum, t_hist, sp_sum, sp_hist, d_sum, d_hist)."""
    overview      = get_connector_overview()
    s_sum, s_hist = refresh_strava()
    h_sum, h_hist = refresh_apple_health()
    t_sum, t_hist = refresh_todoist()
    sp_sum, sp_hist = refresh_spotify()
    d_sum, d_hist   = refresh_discord()
    return overview, s_sum, s_hist, h_sum, h_hist, t_sum, t_hist, sp_sum, sp_hist, d_sum, d_hist


def save_connector_settings(
    discord_token: str,
    discord_users: str,
    strava_client_id: str,
    strava_client_secret: str,
    strava_access_token: str,
    strava_refresh_token: str,
    todoist_token: str,
    spotify_client_id: str,
    spotify_client_secret: str,
    spotify_access_token: str,
    spotify_refresh_token: str,
    apple_health_path: str,
    quiet_start: str,
    quiet_end: str,
) -> str:
    cfg = get_config()
    cfg.discord_bot_token          = discord_token.strip()
    cfg.discord_allowed_user_ids   = discord_users.strip()
    cfg.strava_client_id           = strava_client_id.strip()
    cfg.strava_client_secret       = strava_client_secret.strip()
    cfg.strava_access_token        = strava_access_token.strip()
    cfg.strava_refresh_token       = strava_refresh_token.strip()
    cfg.todoist_api_token          = todoist_token.strip()
    cfg.spotify_client_id          = spotify_client_id.strip()
    cfg.spotify_client_secret      = spotify_client_secret.strip()
    cfg.spotify_access_token       = spotify_access_token.strip()
    cfg.spotify_refresh_token      = spotify_refresh_token.strip()
    cfg.apple_health_export_path   = apple_health_path.strip()
    try:
        cfg.preemptive_quiet_hours_start = int(quiet_start)
        cfg.preemptive_quiet_hours_end   = int(quiet_end)
    except ValueError:
        return "Quiet hours must be integers (0–23)."
    save_config(cfg)
    reload_config()
    return "✓ Connector settings saved."


def get_nudge_history_md() -> str:
    try:
        from kg.connector_store import get_nudge_history
        nudges = get_nudge_history(20)
        if not nudges:
            return "_No preemptive nudges recorded yet._"
        lines = ["| Time | Type | Surfaced | Message |",
                 "|------|------|----------|---------|"]
        for n in nudges:
            lines.append(
                f"| {_ts(n['generated_at'])} | {n['nudge_type']} "
                f"| {'✓' if n['surfaced'] else '–'} | {n['message'][:80]} |"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# DB Records helpers  (Tab 7)
# ---------------------------------------------------------------------------

def _get_db_records_md(table_name: str, limit: int = 25) -> str:
    try:
        from kg.connector_schema import get_connector_db_connection
        cfg = get_config()
        conn = get_connector_db_connection(cfg.connector_db_path)
        cur  = conn.cursor()
        cur.execute(f"SELECT * FROM {table_name} ORDER BY ROWID DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.close()
        if not rows:
            return f"_No records in `{table_name}` yet — run connectors first._"
        header = "| " + " | ".join(cols) + " |"
        sep    = "|" + "|".join("---" for _ in cols) + "|"
        lines  = [header, sep]
        for row in rows:
            vals = []
            for i, v in enumerate(row):
                col = cols[i]
                if col in ("polled_at", "generated_at") and v:
                    try:
                        v = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(v)))
                    except Exception:
                        pass
                elif isinstance(v, float):
                    v = f"{v:.3f}"
                elif v is None:
                    v = "—"
                else:
                    v = str(v)[:55]
                vals.append(v)
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading `{table_name}`: {e}"


def get_all_db_records() -> tuple:
    return (
        _get_db_records_md("connector_runs"),
        _get_db_records_md("strava_snapshots"),
        _get_db_records_md("apple_health_snapshots"),
        _get_db_records_md("todoist_snapshots"),
        _get_db_records_md("spotify_snapshots"),
        _get_db_records_md("discord_snapshots"),
        _get_db_records_md("preemptive_nudges"),
    )


# ---------------------------------------------------------------------------
# Demo mode helpers  (Tab 8)
# ---------------------------------------------------------------------------

_DEMO_QUERIES = [
    "What's on my calendar today?",
    "How am I doing this week health-wise?",
    "Do I have time for a run today?",
    "What tasks are overdue?",
    "Research recent LLM papers and summarize findings",
    "Compare the latest AI benchmark results in detail",
]


def _poll_all_connectors() -> dict:
    """Poll all four Hermes tools and return raw signal dicts."""
    import importlib
    out = {}
    for key, mod_path, fn_name in [
        ("strava",        "hermes_tools.strava_tool",        "strava_summary"),
        ("apple_health",  "hermes_tools.apple_health_tool",  "apple_health_summary"),
        ("todoist",       "hermes_tools.todoist_tool",        "todoist_summary"),
        ("spotify",       "hermes_tools.spotify_tool",        "spotify_mood"),
    ]:
        try:
            m = importlib.import_module(mod_path)
            out[key] = getattr(m, fn_name)()
        except Exception as e:
            out[key] = {"success": False, "source": "error", "summary": str(e)}
    return out


def run_query_demo(query: str) -> tuple[str, str, str]:
    if not query.strip():
        return "Enter a query above.", "", ""

    # Step 1 — routing
    try:
        from routing.router import router as _router
        r = _router.route(query)
        decision   = r.decision.value if hasattr(r.decision, "value") else str(r.decision)
        privacy    = r.privacy_score
        complexity = r.complexity_score
        reason     = r.reason
        badge = ("🟢 LOCAL (Ollama — stays on-device)"
                 if decision == "LOCAL"
                 else "🟡 CLOUD (Groq — only non-personal text sent)")
        routing_md = (
            f"### Routing Decision\n\n"
            f"**Query:** _{query}_\n\n"
            f"| Field | Value |\n|---|---|\n"
            f"| Decision | {badge} |\n"
            f"| Privacy score | `{privacy:.3f}` {'→ ≥0.65 forces LOCAL' if privacy >= 0.65 else ''} |\n"
            f"| Complexity | `{complexity:.3f}` {'→ ≥0.6 eligible for CLOUD' if complexity >= 0.6 else ''} |\n"
            f"| Reason | {reason} |"
        )
    except Exception as e:
        return f"Router error: {e}", "", ""

    # Step 2 — connector signals
    sigs = _poll_all_connectors()
    connector_lines = []
    icons = {"strava": "🏃", "apple_health": "❤️", "todoist": "✅", "spotify": "🎵"}
    labels = {"strava": "Strava", "apple_health": "Apple Health",
              "todoist": "Todoist", "spotify": "Spotify"}
    for k in ("strava", "apple_health", "todoist", "spotify"):
        d = sigs.get(k, {})
        connector_lines.append(
            f"**{icons[k]} {labels[k]} ({d.get('source','?')}):** "
            f"{d.get('summary', '—')}"
        )
    signals_md = "### Connector Signals Polled\n\n" + "\n\n".join(connector_lines)

    # Step 3 — mock answer synthesis
    s = sigs.get("strava", {})
    h = sigs.get("apple_health", {})
    t = sigs.get("todoist", {})
    sp = sigs.get("spotify", {})
    model_note = ("Processed entirely on-device by **Ollama** — no data left your machine."
                  if decision == "LOCAL"
                  else "Planning delegated to **Groq** cloud; only the query text was sent — connector signals stayed local.")
    try:
        context = (
            f"Sleep quality **{h.get('sleep_quality','unknown')}**, "
            f"**{t.get('due_today_count',0)} tasks due today** "
            f"({'heavy' if t.get('heavy_day') else 'manageable'} workload), "
            f"Spotify mood **{sp.get('mood','unknown')}**, "
            f"last exercised **{s.get('days_since_last_activity','?')} day(s) ago**."
        )
    except Exception:
        context = "_(connector data unavailable)_"

    answer_md = (
        f"### Mock Answer\n\n"
        f"_{model_note}_\n\n"
        f"**Personal context used:** {context}\n\n"
        f"> Based on your signals I would respond to _\"{query}\"_: "
        f"{context} Let me know if you want details on any of these."
    )
    return routing_md, signals_md, answer_md


def run_preemptive_demo() -> tuple[str, str, str]:
    sigs = _poll_all_connectors()
    icons  = {"strava": "🏃", "apple_health": "❤️", "todoist": "✅", "spotify": "🎵"}
    labels = {"strava": "Strava", "apple_health": "Apple Health",
              "todoist": "Todoist", "spotify": "Spotify"}
    connector_lines = []
    for k in ("strava", "apple_health", "todoist", "spotify"):
        d = sigs.get(k, {})
        connector_lines.append(
            f"**{icons[k]} {labels[k]} ({d.get('source','?')}):** "
            f"{d.get('summary', '—')}"
        )
    signals_md = "### Step 1 — Collect Signals (all mock)\n\n" + "\n\n".join(connector_lines)

    # Cross-source fusion
    s  = sigs.get("strava", {})
    h  = sigs.get("apple_health", {})
    t  = sigs.get("todoist", {})
    sp = sigs.get("spotify", {})

    days_since   = int(s.get("days_since_last_activity") or 0)
    gap_exceeded = bool(s.get("gap_threshold_exceeded", False))
    heavy_day    = bool(t.get("heavy_day", False))
    overdue      = int(t.get("overdue_count") or 0)
    due_today    = int(t.get("due_today_count") or 0)
    sleep_q      = h.get("sleep_quality", "unknown")
    mood         = sp.get("mood", "unknown")
    deep_work    = bool(sp.get("deep_work_session", False))
    recovery     = h.get("recovery_status", "unknown")
    low_hrv      = bool(h.get("low_hrv", False))

    rules = []
    nudge_type = nudge_msg = None

    if gap_exceeded:
        rules.append(f"✅ **Fitness gap** — {days_since}d since last activity (threshold exceeded)")
        nudge_type = "fitness_gap"
        nudge_msg  = f"You haven't exercised in {days_since} days — a short run could reset your energy!"
    else:
        rules.append(f"⬜ Fitness gap — {days_since}d (within threshold)")

    if heavy_day and sleep_q in ("poor", "fair"):
        rules.append(f"✅ **Task overload + poor sleep** — {overdue} overdue, {due_today} due today, sleep={sleep_q}")
        if not nudge_type:
            nudge_type = "task_overload_recovery"
            nudge_msg  = (f"Heavy day ({due_today} tasks due, {overdue} overdue) "
                          f"after {sleep_q} sleep. Tackle the top 3 first, then rest.")
    else:
        rules.append(f"⬜ Task overload + poor sleep — heavy_day={heavy_day}, sleep={sleep_q}")

    if mood in ("focused", "upbeat") and not heavy_day:
        rules.append(f"✅ **Optimal focus window** — mood={mood}, deep_work={deep_work}")
        if not nudge_type:
            nudge_type = "focus_window"
            nudge_msg  = f"Your music signals a focused mindset ({mood}). Great time for deep work!"
    else:
        rules.append(f"⬜ Optimal focus window — mood={mood}, heavy_day={heavy_day}")

    if recovery == "low" or low_hrv:
        rules.append(f"✅ **Low recovery** — recovery_status={recovery}, low_hrv={low_hrv}")
        if not nudge_type:
            nudge_type = "recovery_alert"
            nudge_msg  = f"Body signals low recovery (HRV low, status={recovery}). Consider a lighter schedule."
    else:
        rules.append(f"⬜ Low recovery — recovery_status={recovery}, low_hrv={low_hrv}")

    if not nudge_type:
        nudge_type = "all_clear"
        nudge_msg  = "All signals green — no proactive nudge needed today."

    fusion_md = (
        "### Step 2 — Cross-Source Fusion Rules\n\n"
        + "\n\n".join(rules)
        + f"\n\n**→ Triggered nudge type:** `{nudge_type}`"
    )

    try:
        from kg.connector_store import record_nudge
        record_nudge(nudge_type, nudge_msg, surfaced=True, platform="discord")
    except Exception:
        pass

    nudge_md = (
        "### Step 3 — Nudge Delivered\n\n"
        f"| Field | Value |\n|---|---|\n"
        f"| Type | `{nudge_type}` |\n"
        f"| Platform | Discord DM |\n"
        f"| Recorded | ✓ written to `preemptive_nudges` |\n\n"
        f"**Message sent:**\n> {nudge_msg}\n\n"
        "_In production the Hermes gateway delivers this as a Discord DM. "
        "Refresh the DB Records tab → preemptive\\_nudges to see the audit row._"
    )
    return signals_md, fusion_md, nudge_md


# ---------------------------------------------------------------------------
# Settings save
# ---------------------------------------------------------------------------

def save_settings(local_model, groq_key, tavily_key, slack_token, google_creds, threshold_str) -> str:
    try:
        threshold = float(threshold_str)
    except ValueError:
        return "Invalid complexity threshold — must be a number between 0 and 1."
    cfg = get_config()
    cfg.local_model              = local_model
    cfg.groq_api_key             = groq_key
    cfg.tavily_api_key           = tavily_key
    cfg.slack_bot_token          = slack_token
    cfg.google_credentials_path  = google_creds.strip()
    cfg.complexity_threshold     = threshold
    save_config(cfg)
    reload_config()
    return "✓ Settings saved."


# ---------------------------------------------------------------------------
# Google OAuth connect (Calendar / Gmail)
# ---------------------------------------------------------------------------

def _connect_google(creds_path: str, service: str) -> str:
    """
    Persist the credentials path, then run the interactive OAuth consent for the
    chosen Google service. This opens a browser for the user to authorise; it
    blocks until they finish. Returns a human-readable status.
    """
    creds_path = (creds_path or "").strip()
    if not creds_path:
        return "Enter the Google OAuth credentials path first, then connect."
    cfg = get_config()
    cfg.google_credentials_path = creds_path
    save_config(cfg)
    reload_config()

    if service == "calendar":
        from connectors.calendar import GoogleCalendarConnector
        result = GoogleCalendarConnector().connect()
    else:
        from connectors.gmail import GmailConnector
        result = GmailConnector().connect()

    if result.get("success"):
        return f"✓ {result.get('message', 'Connected.')}"
    return f"Connection failed: {result.get('error')}"


def connect_calendar(creds_path: str) -> str:
    return _connect_google(creds_path, "calendar")


def connect_gmail(creds_path: str) -> str:
    return _connect_google(creds_path, "gmail")


# ---------------------------------------------------------------------------
# Build UI
# ---------------------------------------------------------------------------

def build_main_ui(cfg: AppConfig) -> gr.Blocks:
    with gr.Blocks(
        title="KnowledgeMind",
        theme=gr.themes.Soft(primary_hue="blue"),
        css="""
            footer { display: none !important; }
            .token-panel { font-family: monospace; font-size: 0.82em; }
            .level-table { margin-bottom: 8px; }
        """,
    ) as demo:

        gr.HTML("""
            <div style="text-align:center; padding:16px 0 8px 0">
                <h1 style="color:#1B3A6B; font-size:2em; margin:0">🧠 KnowledgeMind</h1>
                <p style="color:#555; margin:2px 0">
                    Privacy-Aware Personal AI Agent · IISc Bengaluru
                </p>
            </div>
        """)

        with gr.Tabs():

            # ── Tab 1: Chat ────────────────────────────────────────────────
            with gr.TabItem("💬 Chat"):
                with gr.Row():

                    # Left column: chat + controls
                    with gr.Column(scale=3):
                        chatbot = gr.Chatbot(
                            label="Conversation",
                            height=420,
                            # gradio 6 uses the dict messages format exclusively
                            # (no `type` arg); chat() appends {"role","content"}.
                            render_markdown=True,
                        )
                        with gr.Row():
                            msg_input = gr.Textbox(
                                placeholder="Ask anything — scheduling, web search, documents, calendar...",
                                show_label=False,
                                scale=5,
                            )
                            send_btn = gr.Button("Send", variant="primary", scale=1)

                        # Agency Level selector
                        gr.Markdown("### Agency Level")
                        agency_radio = gr.Radio(
                            choices=[
                                "L1 — Augmented LLM (single call, lowest tokens)",
                                "L2 — Workflow (plan→execute→critique)",
                                "L3 — Autonomous Agent (ReAct loop, most capable)",
                            ],
                            value="L2 — Workflow (plan→execute→critique)",
                            label=None,
                            info="Select agentic autonomy level. Higher = more capable but more tokens.",
                        )

                        with gr.Row():
                            show_routing = gr.Checkbox(label="Show routing log", value=True)
                            show_tokens  = gr.Checkbox(label="Show token consumption", value=True)
                            reset_btn    = gr.Button("Reset session", variant="secondary")

                        routing_panel = gr.Markdown(label="Routing Log")
                        token_panel   = gr.Markdown(label="Token Consumption", elem_classes=["token-panel"])

                        # Gmail send-confirmation gate (PRIVACY rule 6 / rule 4):
                        # the only place email is actually sent. The agent can
                        # draft but never send; the user must confirm + click.
                        with gr.Accordion("Compose & Send Email (confirmation gate)", open=False):
                            email_to      = gr.Textbox(label="To", placeholder="name@example.com")
                            email_subject = gr.Textbox(label="Subject")
                            email_body    = gr.Textbox(label="Body", lines=4)
                            email_confirm = gr.Checkbox(label="I confirm sending this email", value=False)
                            email_send_btn = gr.Button("Send email", variant="stop")
                            email_status  = gr.Markdown()

                    # Right column: level reference table
                    with gr.Column(scale=1):
                        gr.Markdown("### Level Trade-offs")
                        gr.HTML(LEVEL_TRADEOFF_HTML, elem_classes=["level-table"])

                        gr.Markdown("### Example queries")
                        gr.Markdown("""
**L1 (fast):**
- What is attention in transformers?
- Define softmax

**L2 (structured):**
- What's on my calendar today?
- Book a 1hr slot tomorrow at 3pm

**L3 (autonomous):**
- Research recent LLM papers and check if any conflict with my meetings
- Find free time, check my emails for pending items, summarise my week
""")
                        reset_status = gr.Textbox(label="Status", interactive=False, lines=1)

            # ── Tab 2: Knowledge Graph ─────────────────────────────────────
            with gr.TabItem("🕸️ Knowledge Graph"):
                gr.Markdown("Live view of your personal knowledge graph. Auto-refreshes every 60s.")
                with gr.Row():
                    refresh_kg_btn = gr.Button("Refresh Graph", variant="secondary")
                kg_html = gr.HTML(value="<p style='color:#888'>Click Refresh to load graph.</p>")

            # ── Tab 3: Monitor ─────────────────────────────────────────────
            with gr.TabItem("📡 Monitor"):
                gr.Markdown("Background monitor status and proactive conflict alerts.")
                monitor_state_md = gr.Markdown(value=get_monitor_state())
                with gr.Row():
                    run_poll_btn = gr.Button("Run poll now", variant="primary")
                    refresh_monitor_btn = gr.Button("Refresh Alerts", variant="secondary")
                gr.Markdown("### Alerts")
                monitor_output = gr.Markdown(value=get_monitor_status())

            # ── Tab 4: Documents ───────────────────────────────────────────
            with gr.TabItem("📄 Documents"):
                gr.Markdown("Upload documents to the local RAG knowledge base.")
                upload_input  = gr.File(label="Upload PDF / TXT / MD", file_types=[".pdf", ".txt", ".md"])
                upload_status = gr.Textbox(label="Upload status", interactive=False)
                gr.HTML("<hr>")
                doc_list_btn  = gr.Button("List indexed documents")
                doc_list_out  = gr.Markdown()

            # ── Tab 5: Connectors ──────────────────────────────────────────
            with gr.TabItem("🔌 Connectors"):
                gr.Markdown(
                    "Status and latest data from each connector. "
                    "All personal data stays local — never sent to a cloud model."
                )

                connector_overview = gr.Markdown(value=get_connector_overview())
                refresh_all_btn = gr.Button("↻ Refresh all connectors", variant="primary")

                # -- Discord --------------------------------------------------
                with gr.Accordion("💬 Discord (query + preemptive gateway)", open=False):
                    discord_summary_md = gr.Markdown(value="Click Refresh to load.")
                    discord_refresh_btn = gr.Button("↻ Refresh Discord", variant="secondary")
                    gr.Markdown("#### History")
                    discord_history_md = gr.Markdown()
                    gr.Markdown("#### Configure")
                    c_discord_token = gr.Textbox(
                        label="Bot token",
                        value=cfg.discord_bot_token,
                        type="password",
                        placeholder="Bot token from Discord developer portal",
                    )
                    c_discord_users = gr.Textbox(
                        label="Allowed user IDs (comma-separated)",
                        value=cfg.discord_allowed_user_ids,
                        placeholder="123456789,987654321",
                    )
                    gr.Markdown(
                        "_Discord is handled by the Hermes gateway (`hermes gateway`). "
                        "KnowledgeMind records snapshots written by the gateway here._"
                    )

                # -- Strava ---------------------------------------------------
                with gr.Accordion("🏃 Strava (fitness signals)", open=False):
                    strava_summary_md = gr.Markdown(value="Click Refresh to load.")
                    strava_refresh_btn = gr.Button("↻ Refresh Strava", variant="secondary")
                    gr.Markdown("#### History")
                    strava_history_md = gr.Markdown()
                    gr.Markdown("#### Configure")
                    c_strava_id     = gr.Textbox(label="Client ID",     value=cfg.strava_client_id)
                    c_strava_secret = gr.Textbox(label="Client secret", value=cfg.strava_client_secret, type="password")
                    c_strava_access = gr.Textbox(label="Access token",  value=cfg.strava_access_token,  type="password")
                    c_strava_refresh= gr.Textbox(label="Refresh token", value=cfg.strava_refresh_token, type="password")

                # -- Apple Health ---------------------------------------------
                with gr.Accordion("❤️ Apple Health (sleep & recovery)", open=False):
                    health_summary_md = gr.Markdown(value="Click Refresh to load.")
                    health_refresh_btn = gr.Button("↻ Refresh Apple Health", variant="secondary")
                    gr.Markdown("#### History")
                    health_history_md = gr.Markdown()
                    gr.Markdown("#### Configure")
                    c_health_path = gr.Textbox(
                        label="Export path (iCloud folder or S3 bucket name)",
                        value=cfg.apple_health_export_path,
                        placeholder="~/Library/Mobile Documents/.../HealthExport  or  s3://km-health-export",
                    )

                # -- Todoist --------------------------------------------------
                with gr.Accordion("✅ Todoist (task load)", open=False):
                    todoist_summary_md = gr.Markdown(value="Click Refresh to load.")
                    todoist_refresh_btn = gr.Button("↻ Refresh Todoist", variant="secondary")
                    gr.Markdown("#### History")
                    todoist_history_md = gr.Markdown()
                    gr.Markdown("#### Configure")
                    c_todoist_token = gr.Textbox(
                        label="API token",
                        value=cfg.todoist_api_token,
                        type="password",
                        placeholder="Personal developer token from todoist.com/app/settings/integrations",
                    )

                # -- Spotify --------------------------------------------------
                with gr.Accordion("🎵 Spotify (mood signal)", open=False):
                    spotify_summary_md = gr.Markdown(value="Click Refresh to load.")
                    spotify_refresh_btn = gr.Button("↻ Refresh Spotify", variant="secondary")
                    gr.Markdown("#### History")
                    spotify_history_md = gr.Markdown()
                    gr.Markdown("#### Configure")
                    c_spotify_id     = gr.Textbox(label="Client ID",     value=cfg.spotify_client_id)
                    c_spotify_secret = gr.Textbox(label="Client secret", value=cfg.spotify_client_secret, type="password")
                    c_spotify_access = gr.Textbox(label="Access token",  value=cfg.spotify_access_token,  type="password")
                    c_spotify_refresh= gr.Textbox(label="Refresh token", value=cfg.spotify_refresh_token, type="password")

                # -- Preemptive nudge history ---------------------------------
                with gr.Accordion("📣 Preemptive nudge history", open=False):
                    nudge_history_md = gr.Markdown(value=get_nudge_history_md())
                    nudge_refresh_btn = gr.Button("↻ Refresh nudge log", variant="secondary")

                # Shared save button for all connector config
                gr.Markdown("---")
                with gr.Row():
                    c_quiet_start = gr.Textbox(label="Quiet hours start (UTC hour, 0-23)", value=str(cfg.preemptive_quiet_hours_start), scale=1)
                    c_quiet_end   = gr.Textbox(label="Quiet hours end (UTC hour, 0-23)",   value=str(cfg.preemptive_quiet_hours_end),   scale=1)
                connector_save_btn = gr.Button("Save connector settings", variant="primary")
                connector_save_status = gr.Markdown()

            # ── Tab 6: DB Records ──────────────────────────────────────────
            with gr.TabItem("🗄️ DB Records"):
                gr.Markdown(
                    "Raw records from **connectors.db** — the separate SQLite database "
                    "that stores all connector snapshots. Newest rows first, last 25 per table."
                )
                refresh_db_btn = gr.Button("↻ Refresh all tables", variant="primary")

                with gr.Accordion("📋 connector_runs — master poll log", open=True):
                    db_runs_md = gr.Markdown(value=_get_db_records_md("connector_runs"))

                with gr.Accordion("🏃 strava_snapshots", open=False):
                    db_strava_md = gr.Markdown(value=_get_db_records_md("strava_snapshots"))

                with gr.Accordion("❤️ apple_health_snapshots", open=False):
                    db_health_md = gr.Markdown(value=_get_db_records_md("apple_health_snapshots"))

                with gr.Accordion("✅ todoist_snapshots", open=False):
                    db_todoist_md = gr.Markdown(value=_get_db_records_md("todoist_snapshots"))

                with gr.Accordion("🎵 spotify_snapshots", open=False):
                    db_spotify_md = gr.Markdown(value=_get_db_records_md("spotify_snapshots"))

                with gr.Accordion("💬 discord_snapshots", open=False):
                    db_discord_md = gr.Markdown(value=_get_db_records_md("discord_snapshots"))

                with gr.Accordion("📣 preemptive_nudges", open=False):
                    db_nudges_md = gr.Markdown(value=_get_db_records_md("preemptive_nudges"))

            # ── Tab 7: Demo ────────────────────────────────────────────────
            with gr.TabItem("🎬 Demo"):
                gr.Markdown(
                    "Live walkthroughs of both operating modes using **mock data** — "
                    "no credentials needed. All connector signals are derived from built-in mock fixtures."
                )

                # ── Query Mode ────────────────────────────────────────────
                with gr.Accordion("🔍 Query Mode — how KnowledgeMind answers your messages", open=True):
                    gr.Markdown(
                        "Select a preset query or type your own. The demo shows the full pipeline: "
                        "**privacy routing → connector polling → answer synthesis**."
                    )
                    demo_query_dropdown = gr.Dropdown(
                        choices=_DEMO_QUERIES,
                        label="Preset queries",
                        value=_DEMO_QUERIES[0],
                    )
                    demo_query_input = gr.Textbox(
                        label="Query (edit or type your own)",
                        value=_DEMO_QUERIES[0],
                        lines=2,
                    )
                    demo_query_btn = gr.Button("▶ Run Query Demo", variant="primary")

                    with gr.Row():
                        demo_routing_md  = gr.Markdown(label="Routing")
                        demo_signals_md  = gr.Markdown(label="Connector signals")
                    demo_answer_md = gr.Markdown(label="Answer")

                # ── Preemptive Mode ────────────────────────────────────────
                with gr.Accordion("🤖 Preemptive Mode — how autonomous nudges are generated", open=True):
                    gr.Markdown(
                        "Simulates a full Hermes cron cycle: collect signals → apply cross-source "
                        "fusion rules → generate and record a nudge. The nudge row is written to "
                        "`preemptive_nudges` so you can verify it in the **DB Records** tab."
                    )
                    preemptive_demo_btn = gr.Button("▶ Run Preemptive Demo", variant="primary")

                    with gr.Row():
                        preemptive_signals_md = gr.Markdown(label="Signals")
                        preemptive_fusion_md  = gr.Markdown(label="Fusion rules")
                    preemptive_nudge_md = gr.Markdown(label="Nudge")

            # ── Tab 8: Settings ────────────────────────────────────────────
            with gr.TabItem("⚙️ Settings"):
                gr.Markdown("Update configuration without restarting. Saved immediately.")
                settings_model    = gr.Textbox(label="Local model", value=cfg.local_model)
                settings_groq     = gr.Textbox(label="Groq API Key", value=cfg.groq_api_key, type="password")
                settings_tavily   = gr.Textbox(label="Tavily API Key (optional)", value=cfg.tavily_api_key, type="password")
                settings_slack    = gr.Textbox(label="Slack Bot Token (optional)", value=cfg.slack_bot_token, type="password")
                settings_google   = gr.Textbox(
                    label="Google OAuth credentials path (Calendar + Gmail)",
                    value=cfg.google_credentials_path,
                    placeholder="./credentials.json",
                )
                settings_threshold = gr.Textbox(
                    label="Complexity threshold (L2/L3 cloud routing cutoff, 0.0–1.0)",
                    value=str(cfg.complexity_threshold),
                )
                settings_save_btn = gr.Button("Save settings", variant="primary")
                settings_status   = gr.Textbox(label="Status", interactive=False)

                gr.Markdown("### Connect Google")
                gr.Markdown(
                    "Authorise Calendar and Gmail. Each opens a browser for "
                    "one-time consent and saves a token locally."
                )
                with gr.Row():
                    connect_calendar_btn = gr.Button("Connect Google Calendar", variant="secondary")
                    connect_gmail_btn    = gr.Button("Connect Gmail", variant="secondary")
                google_status = gr.Markdown()

        # ── Event wiring ───────────────────────────────────────────────────

        # Two-step chain: user_turn echoes the message instantly (queue=False),
        # then bot_turn runs the agent and appends the reply.
        send_btn.click(
            user_turn,
            inputs=[msg_input, chatbot],
            outputs=[msg_input, chatbot],
            queue=False,
        ).then(
            bot_turn,
            inputs=[chatbot, agency_radio, show_routing, show_tokens],
            outputs=[chatbot, routing_panel, token_panel],
        )

        msg_input.submit(
            user_turn,
            inputs=[msg_input, chatbot],
            outputs=[msg_input, chatbot],
            queue=False,
        ).then(
            bot_turn,
            inputs=[chatbot, agency_radio, show_routing, show_tokens],
            outputs=[chatbot, routing_panel, token_panel],
        )

        reset_btn.click(
            reset_session,
            outputs=[chatbot, routing_panel, token_panel, reset_status],
        )

        refresh_kg_btn.click(render_kg, outputs=kg_html)
        run_poll_btn.click(run_monitor_cycle, outputs=[monitor_state_md, monitor_output])
        refresh_monitor_btn.click(get_monitor_status, outputs=monitor_output)

        # The send-confirmation gate: the sole caller of Gmail send.
        email_send_btn.click(
            send_email,
            inputs=[email_to, email_subject, email_body, email_confirm],
            outputs=email_status,
        )

        upload_input.change(upload_document, inputs=upload_input, outputs=upload_status)
        doc_list_btn.click(list_documents, outputs=doc_list_out)

        settings_save_btn.click(
            save_settings,
            inputs=[settings_model, settings_groq, settings_tavily, settings_slack,
                    settings_google, settings_threshold],
            outputs=settings_status,
        )

        connect_calendar_btn.click(connect_calendar, inputs=settings_google, outputs=google_status)
        connect_gmail_btn.click(connect_gmail, inputs=settings_google, outputs=google_status)

        # ── Connector tab wiring ───────────────────────────────────────────

        # Individual refresh buttons
        strava_refresh_btn.click(
            refresh_strava, outputs=[strava_summary_md, strava_history_md]
        )
        health_refresh_btn.click(
            refresh_apple_health, outputs=[health_summary_md, health_history_md]
        )
        todoist_refresh_btn.click(
            refresh_todoist, outputs=[todoist_summary_md, todoist_history_md]
        )
        spotify_refresh_btn.click(
            refresh_spotify, outputs=[spotify_summary_md, spotify_history_md]
        )
        discord_refresh_btn.click(
            refresh_discord, outputs=[discord_summary_md, discord_history_md]
        )
        nudge_refresh_btn.click(get_nudge_history_md, outputs=nudge_history_md)

        # Refresh all
        refresh_all_btn.click(
            refresh_all_connectors,
            outputs=[
                connector_overview,
                strava_summary_md,  strava_history_md,
                health_summary_md,  health_history_md,
                todoist_summary_md, todoist_history_md,
                spotify_summary_md, spotify_history_md,
                discord_summary_md, discord_history_md,
            ],
        )

        # Save connector settings
        connector_save_btn.click(
            save_connector_settings,
            inputs=[
                c_discord_token, c_discord_users,
                c_strava_id, c_strava_secret, c_strava_access, c_strava_refresh,
                c_todoist_token,
                c_spotify_id, c_spotify_secret, c_spotify_access, c_spotify_refresh,
                c_health_path,
                c_quiet_start, c_quiet_end,
            ],
            outputs=connector_save_status,
        )

        # ── DB Records tab wiring ─────────────────────────────────────────
        refresh_db_btn.click(
            get_all_db_records,
            outputs=[
                db_runs_md, db_strava_md, db_health_md,
                db_todoist_md, db_spotify_md, db_discord_md, db_nudges_md,
            ],
        )

        # ── Demo tab wiring ───────────────────────────────────────────────
        demo_query_dropdown.change(
            lambda q: q,
            inputs=demo_query_dropdown,
            outputs=demo_query_input,
        )
        demo_query_btn.click(
            run_query_demo,
            inputs=demo_query_input,
            outputs=[demo_routing_md, demo_signals_md, demo_answer_md],
        )
        preemptive_demo_btn.click(
            run_preemptive_demo,
            outputs=[preemptive_signals_md, preemptive_fusion_md, preemptive_nudge_md],
        )

    return demo


# ---------------------------------------------------------------------------
# Standalone entry (used by launcher.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = get_config()
    demo = build_main_ui(cfg)
    demo.launch(server_name="127.0.0.1", server_port=7860, show_error=True)
