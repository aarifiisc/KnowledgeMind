import streamlit as st
import networkx as nx

from config import CURRENT_DATE, PERSONAS
from agents.persona_agent import get_reply
from agents.extraction_agent import extract
from agents.conflict_agent import scan as scan_conflicts
from graph.visualizer import render as render_graph

st.set_page_config(
    page_title="Group Chat Scheduler",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Per-speaker visual identity ──────────────────────────────────────────────
SPEAKER_META: dict[str, dict] = {
    "Alex":  {"color": "#7B5EA7", "bg": "#dce8ff", "align": "right"},
    "Bob":   {"color": "#4A90D9", "bg": "#f0f2f6", "align": "left"},
    "Annie": {"color": "#5CB85C", "bg": "#f0f2f6", "align": "left"},
    "Cindy": {"color": "#E8940A", "bg": "#f0f2f6", "align": "left"},
}

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; }

    .dm-bubble {
        padding: 8px 13px;
        border-radius: 14px;
        margin-bottom: 5px;
        max-width: 78%;
        font-size: 0.92rem;
        line-height: 1.5;
        word-wrap: break-word;
        display: inline-block;
    }
    .bubble-row-left  { text-align: left;  width: 100%; }
    .bubble-row-right { text-align: right; width: 100%; }

    .speaker-name {
        font-size: 0.7rem;
        font-weight: 700;
        margin-bottom: 2px;
        display: block;
    }
    .date-badge {
        background: #e8f4f8;
        border: 1px solid #b8d8e8;
        border-radius: 8px;
        padding: 2px 10px;
        font-size: 0.72rem;
        color: #2c7fa8;
        margin-left: 10px;
        vertical-align: middle;
    }

    /* ── Conflict alert cards ── */
    .conflict-card {
        background: #fff8e1;
        border: 1px solid #ffe082;
        border-left: 5px solid #D9534F;
        border-radius: 6px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .conflict-card-header {
        font-size: 0.7rem;
        font-weight: 800;
        color: #D9534F;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 5px;
    }
    .conflict-card-body {
        font-size: 0.87rem;
        color: #333;
        line-height: 1.5;
    }
    .clear-card {
        background: #f0faf2;
        border: 1px solid #b7dfbf;
        border-left: 5px solid #5CB85C;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 0.87rem;
        color: #276231;
    }
    .conflict-badge {
        display: inline-block;
        background: #D9534F;
        color: #fff;
        border-radius: 10px;
        padding: 1px 8px;
        font-size: 0.68rem;
        font-weight: 700;
        margin-left: 8px;
        vertical-align: middle;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Session state initialisation ─────────────────────────────────────────────
def _init_state() -> None:
    defaults: dict = {
        "conversations": {p: [] for p in PERSONAS},
        "graph": nx.DiGraph(),
        "conflicts": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()

# Re-scan on every rerun so the alert panel always reflects the current graph.
# This is cheap (pure graph traversal, no LLM) and clears any stale alerts.
scan_conflicts()


# ── Helper: render one DM bubble ─────────────────────────────────────────────
def render_bubble(role: str, content: str) -> None:
    meta = SPEAKER_META.get(role, {"color": "#888", "bg": "#eee", "align": "left"})
    row_class = "bubble-row-right" if meta["align"] == "right" else "bubble-row-left"
    st.markdown(
        f"""
        <div class="{row_class}">
            <span class="speaker-name" style="color:{meta['color']};">{role}</span>
            <span class="dm-bubble" style="background:{meta['bg']};">{content}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Two-panel layout ─────────────────────────────────────────────────────────
col_chat, col_graph = st.columns([55, 45])

# ── LEFT: DM conversation panel ──────────────────────────────────────────────
with col_chat:
    st.markdown(
        f'<h3 style="margin-bottom:0.5rem;">Messages'
        f'<span class="date-badge">Today: {CURRENT_DATE.strftime("%A, %B %d %Y")}</span>'
        f"</h3>",
        unsafe_allow_html=True,
    )

    tabs = st.tabs(PERSONAS)

    for tab, persona in zip(tabs, PERSONAS):
        with tab:
            thread = st.session_state["conversations"][persona]

            # Scrollable message thread
            chat_area = st.container(height=440, border=False)
            with chat_area:
                if not thread:
                    st.caption(f"No messages yet — say something to {persona}.")
                for msg in thread:
                    render_bubble(msg["role"], msg["content"])

            # Per-conversation input form
            with st.form(key=f"form_{persona}", clear_on_submit=True):
                user_input = st.text_input(
                    "Message",
                    placeholder=f"Message {persona}…",
                    label_visibility="collapsed",
                    key=f"input_{persona}",
                )
                send = st.form_submit_button("Send", use_container_width=True)

            if send and user_input.strip():
                msg_text = user_input.strip()

                with st.spinner(f"{persona} is typing…"):
                    _, reply = get_reply(persona, thread, msg_text)

                # Append both turns together after inference so the history
                # passed to get_reply never includes the current message.
                thread.append({"role": "Alex", "content": msg_text})
                thread.append({"role": persona, "content": reply})

                # Extract scheduling entities and update the knowledge graph.
                # scan_conflicts() runs automatically at the top of the next rerun.
                extract(persona, thread)

                st.rerun()

# ── RIGHT: Unified graph + alert panel ───────────────────────────────────────
with col_graph:
    st.markdown("### Knowledge Graph")
    render_graph(st.session_state["graph"])

    st.divider()

    conflicts = st.session_state["conflicts"]
    n = len(conflicts)
    badge = f'<span class="conflict-badge">{n}</span>' if n else ""
    st.markdown(
        f'<h4 style="margin-bottom:0.6rem;">Conflict Alerts{badge}</h4>',
        unsafe_allow_html=True,
    )

    if conflicts:
        for msg in conflicts:
            # Strip the redundant "Conflict Detected: " prefix — it's implied
            # by the card header below.
            body = msg.removeprefix("Conflict Detected: ")
            st.markdown(
                f"""
                <div class="conflict-card">
                    <div class="conflict-card-header">Scheduling Conflict</div>
                    <div class="conflict-card-body">{body}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="clear-card">All clear — no scheduling conflicts detected.</div>',
            unsafe_allow_html=True,
        )
