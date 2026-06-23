import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { getJSON } from "./api";

// Concrete colours (cytoscape can't read CSS vars). Saturated enough to read on
// both the light and dark app backgrounds. Legend swatches reuse the same map.
const C = {
  you: "#6366f1",       // self ("You")
  person: "#a855f7",    // other people
  calendar: "#10b981",  // calendar commitments
  chat: "#3b82f6",      // slack / chat commitments
  mail: "#14b8a6",      // gmail / email
  other: "#64748b",     // unknown source
  conflict: "#ef4444",  // genuine scheduling clash
  dup: "#f59e0b",       // same real-world event on two channels
  edge: "#94a3b8",      // has_commitment links
};
const SRC_COLOR = { calendar: C.calendar, slack: C.chat, chat: C.chat, gmail: C.mail, email: C.mail };
const nodeColor = (d) =>
  d.type === "Person" ? (d.self ? C.you : C.person) : (SRC_COLOR[d.source] || C.other);

const fmtWhen = (ts) => {
  if (!ts) return "";
  try {
    return new Date(ts * 1000).toLocaleString([], {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return ""; }
};

function toElements(graph) {
  const nodes = (graph.nodes || []).map((n) => ({ data: { ...n } }));
  const edges = (graph.edges || []).map((e) => ({
    data: {
      id: e.id || `${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      relation: e.label,
      same_event: e.same_event ? 1 : 0,
      elabel: e.label === "conflict" ? `${Math.round(e.overlap_minutes || 0)}m overlap` : "",
    },
  }));
  return [...nodes, ...edges];
}

const STYLE = [
  { selector: "node", style: {
    label: "data(label)", color: "#f8fafc", "font-size": "10px", "font-weight": 600,
    "text-valign": "center", "text-halign": "center", "text-wrap": "wrap", "text-max-width": "92px",
    "background-color": (e) => nodeColor(e.data()),
    "border-width": 0,
    width: 62, height: 40, shape: "round-rectangle",
  } },
  { selector: 'node[type="Person"]', style: { width: 46, height: 46, shape: "ellipse", "font-size": "11px" } },
  { selector: "node[?self]", style: { width: 56, height: 56, shape: "star" } },
  { selector: "node[?archived]", style: { "background-opacity": 0.4, "border-width": 2, "border-style": "dashed", "border-color": C.other, color: "#cbd5e1" } },
  { selector: "edge", style: {
    width: 1.6, "curve-style": "bezier", "line-color": C.edge,
    "target-arrow-color": C.edge, "target-arrow-shape": "triangle", "arrow-scale": 0.8,
  } },
  { selector: 'edge[relation="conflict"]', style: {
    width: 2.6, "line-style": "dashed", "line-color": C.conflict, "target-arrow-shape": "none",
    label: "data(elabel)", "font-size": "9px", color: C.conflict, "text-rotation": "autorotate",
    "text-background-color": "#000", "text-background-opacity": 0.45, "text-background-padding": "2px",
  } },
  { selector: 'edge[relation="conflict"][same_event = 1]', style: { "line-color": C.dup, color: C.dup } },
  { selector: ":selected", style: { "border-width": 3, "border-style": "solid", "border-color": "#ffffff" } },
];

export default function KnowledgeGraph({ refresh }) {
  const boxRef = useRef(null);
  const cyRef = useRef(null);
  const [counts, setCounts] = useState(null);
  const [detail, setDetail] = useState(null);
  const [empty, setEmpty] = useState(false);

  // Create the cytoscape instance once.
  useEffect(() => {
    if (!boxRef.current) return undefined;
    const cy = cytoscape({
      container: boxRef.current,
      style: STYLE,
      layout: { name: "cose", animate: false },
      wheelSensitivity: 0.2,
      minZoom: 0.2,
      maxZoom: 2.5,
    });
    cy.on("tap", "node", (evt) => setDetail(evt.target.data()));
    cy.on("tap", (evt) => { if (evt.target === cy) setDetail(null); });
    cyRef.current = cy;
    return () => { cy.destroy(); cyRef.current = null; };
  }, []);

  // (Re)load the graph on mount and whenever a scan bumps `refresh`.
  useEffect(() => {
    let alive = true;
    getJSON("/api/graph")
      .then((g) => {
        if (!alive) return;
        setCounts(g.counts || null);
        const els = toElements(g);
        setEmpty(els.length === 0);
        const cy = cyRef.current;
        if (!cy) return;
        cy.elements().remove();
        cy.add(els);
        cy.resize();  // re-measure the container in case it was unsized at init
        cy.layout({
          name: "cose", animate: true, animationDuration: 500,
          nodeRepulsion: 9000, idealEdgeLength: 130, padding: 36, fit: true,
        }).run();
        setDetail(null);
      })
      .catch(() => { if (alive) setEmpty(true); });
    return () => { alive = false; };
  }, [refresh]);

  const fit = () => cyRef.current?.animate({ fit: { padding: 36 } }, { duration: 300 });

  return (
    <div className="kg-root">
      <div className="kg-toolbar">
        <div className="graph-legend">
          <span className="lg"><i className="kg-dot" style={{ background: C.you }} /> You</span>
          <span className="lg"><i className="kg-dot" style={{ background: C.person }} /> Person</span>
          <span className="lg"><i className="kg-dot" style={{ background: C.calendar }} /> Calendar</span>
          <span className="lg"><i className="kg-dot" style={{ background: C.chat }} /> Chat / Slack</span>
          <span className="lg"><i className="kg-line" style={{ borderColor: C.conflict }} /> Conflict</span>
          <span className="lg"><i className="kg-line" style={{ borderColor: C.dup }} /> Same event</span>
        </div>
        <div className="kg-tools">
          {counts && (
            <span className="kg-counts">
              {counts.persons} people · {counts.commitments} commitments · {counts.conflicts} conflict{counts.conflicts === 1 ? "" : "s"}
            </span>
          )}
          <button className="btn" onClick={fit}>Fit</button>
        </div>
      </div>

      <div className="kg-stage">
        <div ref={boxRef} className="kg-canvas" />
        {empty && (
          <div className="kg-overlay">
            <div className="big">🕸️</div>
            <strong>Graph is empty</strong>
            <div>Click “Run scan” in the top bar to populate it.</div>
          </div>
        )}
        {detail && (
          <div className="kg-detail">
            <button className="kg-detail-x" onClick={() => setDetail(null)} aria-label="Close">×</button>
            <div className="kg-detail-label">{detail.label}</div>
            <span className="kg-detail-type" style={{ background: nodeColor(detail) + "22", color: nodeColor(detail) }}>
              {detail.self ? "You" : detail.type}
              {detail.commitment_type ? ` · ${detail.commitment_type}` : ""}
              {detail.archived ? " · archived" : ""}
            </span>
            {detail.source && <div className="kg-detail-row"><span>source</span>{detail.source}</div>}
            {detail.start_ts && <div className="kg-detail-row"><span>when</span>{fmtWhen(detail.start_ts)}</div>}
          </div>
        )}
        <div className="kg-hint">drag to pan · scroll to zoom · click a node for details</div>
      </div>
    </div>
  );
}
