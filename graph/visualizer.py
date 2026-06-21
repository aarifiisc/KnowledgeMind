from __future__ import annotations

import networkx as nx
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from config import CONFLICT_COLOR, NODE_COLORS

# Visual sizing per node type
_NODE_SIZES: dict[str, int] = {
    "Person": 30,
    "Event": 22,
    "TimeSlot": 18,
}

# Edge label colours
_EDGE_COLORS: dict[str, str] = {
    "ATTENDS": "#888888",
    "SCHEDULED_AT": "#AAAAAA",
    "INVOLVES": "#CCCCCC",
}

_PYVIS_OPTIONS = """
{
  "physics": {
    "barnesHut": {
      "gravitationalConstant": -4500,
      "centralGravity": 0.4,
      "springLength": 130,
      "springConstant": 0.04,
      "damping": 0.2
    },
    "minVelocity": 0.75
  },
  "edges": {
    "arrows": { "to": { "enabled": true, "scaleFactor": 0.6 } },
    "font":   { "size": 8, "align": "middle", "color": "#999999" },
    "smooth": { "type": "continuous" }
  },
  "nodes": {
    "shape": "dot",
    "font":  { "size": 12, "bold": true }
  },
  "interaction": {
    "hover": true,
    "tooltipDelay": 100
  }
}
"""


def _is_conflict_slot(node_id: str, graph: nx.DiGraph) -> bool:
    """True if this TimeSlot has ≥ 2 Person INVOLVES edges — i.e. a double-booking."""
    if graph.nodes[node_id].get("type") != "TimeSlot":
        return False
    count = sum(
        1 for _, _, d in graph.in_edges(node_id, data=True)
        if d.get("type") == "INVOLVES"
    )
    return count >= 2


def _build_network(graph: nx.DiGraph) -> Network:
    net = Network(
        height="460px",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#333333",
    )
    net.set_options(_PYVIS_OPTIONS)

    for node_id, data in graph.nodes(data=True):
        node_type = data.get("type", "Unknown")
        label = data.get("label", node_id)
        size = _NODE_SIZES.get(node_type, 18)

        if _is_conflict_slot(node_id, graph):
            color = CONFLICT_COLOR
            border = "#A00000"
            title = f"{label}\n⚠ Conflict!"
        else:
            color = NODE_COLORS.get(node_type, "#888888")
            border = color
            title = f"{node_type}: {label}"

        net.add_node(
            node_id,
            label=label,
            color={"background": color, "border": border, "highlight": {"border": border}},
            size=size,
            title=title,
        )

    for u, v, data in graph.edges(data=True):
        edge_type = data.get("type", "")
        net.add_edge(
            u, v,
            label=edge_type,
            color=_EDGE_COLORS.get(edge_type, "#AAAAAA"),
        )

    return net


def render(graph: nx.DiGraph, height: int = 460) -> None:
    """
    Render the shared knowledge graph as an interactive pyvis visualisation
    inside the Streamlit right panel.

    Empty graph shows a placeholder. Conflict TimeSlot nodes are highlighted
    in red. The graph re-renders on every Streamlit rerun, reflecting the
    latest state of st.session_state['graph'].
    """
    if graph.number_of_nodes() == 0:
        st.info(
            "The knowledge graph will appear here once scheduling events "
            "are detected in any conversation."
        )
        return

    net = _build_network(graph)
    html = net.generate_html()
    components.html(html, height=height + 20, scrolling=False)

    # Legend
    st.markdown(
        "<small>"
        f"<span style='color:{NODE_COLORS['Person']};'>&#9679;</span> Person &nbsp;"
        f"<span style='color:{NODE_COLORS['Event']};'>&#9679;</span> Event &nbsp;"
        f"<span style='color:{NODE_COLORS['TimeSlot']};'>&#9679;</span> Time Slot &nbsp;"
        f"<span style='color:{CONFLICT_COLOR};'>&#9679;</span> Conflict"
        "</small>",
        unsafe_allow_html=True,
    )
