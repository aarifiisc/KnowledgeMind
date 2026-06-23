"""
simchat/visualizer.py
---------------------
Renders the shared NetworkX knowledge graph as a static PNG image for Gradio's
gr.Image component.

Node colour scheme:
  Person        — cornflowerblue
  HARD          — mediumseagreen
  SOFT          — gold
  TENTATIVE     — lightsalmon
  (unknown)     — lightgray

Edge colour scheme:
  has_commitment — lightgray (thin, 1.5 px)
  conflict       — crimson   (thick, 3.0 px)

Returns None when the graph is empty so Gradio renders a blank placeholder.
matplotlib is imported lazily at the top of the module (with a graceful
ImportError fallback) so the rest of the stack has no hard dependency on it.
"""

from __future__ import annotations

import io
from typing import Optional

import networkx as nx


# ---------------------------------------------------------------------------
# Optional matplotlib import (soft dependency)
# ---------------------------------------------------------------------------

try:
    import matplotlib
    matplotlib.use("Agg")   # non-interactive backend; must be set before pyplot
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.lines as mlines
    _MPL = True
except ImportError:
    _MPL = False
    print(
        "[Visualizer] WARNING: matplotlib not installed. "
        "Graph rendering is disabled. Run: pip install matplotlib"
    )


# ---------------------------------------------------------------------------
# Colour maps
# ---------------------------------------------------------------------------

_PERSON_COLOUR = "cornflowerblue"
_COMMITMENT_COLOURS: dict[str, str] = {
    "HARD":      "mediumseagreen",
    "SOFT":      "gold",
    "TENTATIVE": "lightsalmon",
}
_FALLBACK_COLOUR = "lightgray"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_graph(graph: nx.DiGraph) -> Optional[bytes]:
    """
    Draw the knowledge graph and return PNG bytes.

    Args:
        graph: The shared nx.DiGraph produced by kg.graph.build_graph().
    Returns:
        PNG bytes on success, or None when matplotlib is unavailable or the
        graph has no nodes.
    """
    if not _MPL or graph.number_of_nodes() == 0:
        return None

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_title("Knowledge Graph", fontsize=12, fontweight="bold", pad=10)
    ax.axis("off")

    pos = nx.spring_layout(graph, seed=42, k=2.0)

    node_colours: list[str] = []
    node_labels: dict = {}
    for node_id, attrs in graph.nodes(data=True):
        node_type = attrs.get("type", "")
        label = attrs.get("label", str(node_id))

        if node_type == "Person":
            node_colours.append(_PERSON_COLOUR)
        else:
            ctype = attrs.get("commitment_type", "")
            node_colours.append(_COMMITMENT_COLOURS.get(ctype, _FALLBACK_COLOUR))

        trimmed = label[:22] + "…" if len(label) > 22 else label
        node_labels[node_id] = trimmed

    conflict_edges = [
        (u, v) for u, v, d in graph.edges(data=True)
        if d.get("label") == "conflict"
    ]
    normal_edges = [
        (u, v) for u, v, d in graph.edges(data=True)
        if d.get("label") != "conflict"
    ]

    nx.draw_networkx_nodes(
        graph, pos, node_color=node_colours, node_size=900, ax=ax, alpha=0.9
    )
    nx.draw_networkx_labels(graph, pos, labels=node_labels, font_size=7, ax=ax)

    if normal_edges:
        nx.draw_networkx_edges(
            graph, pos, edgelist=normal_edges,
            edge_color="lightgray", width=1.5, arrows=True, ax=ax,
        )
    if conflict_edges:
        nx.draw_networkx_edges(
            graph, pos, edgelist=conflict_edges,
            edge_color="crimson", width=3.0, arrows=True, ax=ax,
        )

    legend_handles = [
        mpatches.Patch(facecolor=_PERSON_COLOUR, label="Person"),
        mpatches.Patch(facecolor=_COMMITMENT_COLOURS["HARD"], label="HARD"),
        mpatches.Patch(facecolor=_COMMITMENT_COLOURS["SOFT"], label="SOFT"),
        mpatches.Patch(facecolor=_COMMITMENT_COLOURS["TENTATIVE"], label="TENTATIVE"),
        mlines.Line2D([], [], color="crimson", lw=2.5, label="Conflict"),
    ]
    ax.legend(handles=legend_handles, loc="upper left", fontsize=7, framealpha=0.7)

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_empty() -> Optional[bytes]:
    """Return a placeholder PNG for the initial (empty) graph state."""
    if not _MPL:
        return None

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_title("Knowledge Graph", fontsize=12, fontweight="bold", pad=10)
    ax.text(
        0.5, 0.5,
        "Graph will appear once you send scheduling messages.",
        ha="center", va="center", fontsize=10, color="gray",
        transform=ax.transAxes,
    )
    ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Smoke test (needs networkx; matplotlib is optional)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Empty graph -> None.
    result = render_graph(nx.DiGraph())
    assert result is None, "empty graph should return None"
    print("=> empty graph -> None")

    # Graph with Person + mixed commitments + conflict edge.
    g = nx.DiGraph()
    g.add_node("person:1", label="Annie", type="Person")
    g.add_node("person:2", label="Bob", type="Person")
    g.add_node(
        "commitment:1", label="Coffee Friday 3pm",
        type="Commitment", commitment_type="SOFT", source="annie",
    )
    g.add_node(
        "commitment:2", label="Sync call Friday 3pm",
        type="Commitment", commitment_type="HARD", source="bob",
    )
    g.add_edge("person:1", "commitment:1", label="has_commitment")
    g.add_edge("person:2", "commitment:2", label="has_commitment")
    g.add_edge("commitment:1", "commitment:2", label="conflict", overlap_minutes=60.0)

    png = render_graph(g)
    if png is None:
        print("=> matplotlib unavailable -- render_graph returned None (install matplotlib)")
    else:
        assert isinstance(png, bytes), "expected bytes"
        assert png[:4] == b"\x89PNG", "expected PNG magic bytes"
        print(f"=> graph with {g.number_of_nodes()} nodes rendered to {len(png):,} bytes")

    placeholder = render_empty()
    if placeholder is not None:
        assert isinstance(placeholder, bytes)
        print(f"=> render_empty() returned {len(placeholder):,} bytes")
    else:
        print("=> render_empty() returned None (matplotlib unavailable)")

    print("All simchat/visualizer.py smoke tests passed.")
