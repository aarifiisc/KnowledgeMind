import { useEffect, useRef, useState, useCallback } from "react";
import cytoscape from "cytoscape";
import {
  pmListProjects, pmCreateProject, pmChatHistory, pmSendMessage,
  pmUpdateTags, pmSuggestTags, pmKG, pmCoverage, pmRules,
} from "./api";
import "./projmgmt.css";

const TAGS = ["#decision", "#feature", "#concern", "#sprint", "#architecture", "#blocker", "#out-of-scope"];

const TYPE_COLOR = {
  goal: "#4e79a7", feature: "#59a14f", component: "#f28e2b",
  constraint: "#e15759", actor: "#b07aa1", milestone: "#edc948",
  decision: "#76b7b2", work_item: "#59a14f", proposed_feature: "#f28e2b",
  concern: "#e15759", discussion_topic: "#b07aa1", blocker: "#c0392b",
};
const TYPE_SHAPE = {
  goal: "ellipse", feature: "rectangle", component: "barrel",
  constraint: "diamond", actor: "hexagon", milestone: "star",
  decision: "ellipse", work_item: "rectangle", proposed_feature: "round-rectangle",
  concern: "diamond", discussion_topic: "hexagon", blocker: "octagon",
};

const fmtTime = (ts) => { try { return ts ? new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""; } catch { return ""; } };
const scoreClass = (s) => (s >= 70 ? "hi" : s >= 40 ? "mid" : "lo");

// ── KG panel (cytoscape) ────────────────────────────────────────────────────
function KGPanel({ plane, setPlane, elements }) {
  const boxRef = useRef(null);
  const cyRef = useRef(null);
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!boxRef.current) return undefined;
    const cy = cytoscape({
      container: boxRef.current,
      style: [
        { selector: "node", style: {
          label: "data(label)", "font-size": "10px", color: "#e2e4f0",
          "text-valign": "center", "text-halign": "center", "text-wrap": "wrap",
          "text-max-width": "78px", width: 52, height: 52,
          "background-color": (e) => TYPE_COLOR[e.data("type")] || "#888",
          shape: (e) => TYPE_SHAPE[e.data("type")] || "ellipse",
          "border-width": (e) => (e.data("plane") === "user" ? 2 : 0),
          "border-color": "#cfd3e0",
          "border-style": (e) => (e.data("plane") === "user" ? "dashed" : "solid"),
          "background-opacity": (e) => (e.data("plane") === "user" ? 0.6 : 1),
        } },
        { selector: 'node[coverage_status="covered"]', style: { "border-width": 3, "border-color": "#59a14f", "border-style": "solid" } },
        { selector: "edge", style: {
          width: 1.5, "curve-style": "bezier", "target-arrow-shape": "triangle",
          label: "data(relation)", "font-size": "8px", color: "#9aa0ad", "text-rotation": "autorotate",
          "line-style": (e) => (e.data("plane") === "cross" ? "dashed" : "solid"),
          "line-color": (e) => (e.data("plane") === "cross" ? "#4e79a7" : "#c2c7d0"),
          "target-arrow-color": (e) => (e.data("plane") === "cross" ? "#4e79a7" : "#c2c7d0"),
        } },
        { selector: ":selected", style: { "border-width": 3, "border-color": "#ffffff", "border-style": "solid" } },
      ],
      layout: { name: "cose", animate: false },
      wheelSensitivity: 0.2,
    });
    cy.on("tap", "node", (evt) => setDetail(evt.target.data()));
    cy.on("tap", (evt) => { if (evt.target === cy) setDetail(null); });
    cyRef.current = cy;
    return () => { cy.destroy(); cyRef.current = null; };
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().remove();
    cy.add(elements || []);
    cy.layout({ name: "cose", animate: true, animationDuration: 400, nodeRepulsion: 8000, idealEdgeLength: 120 }).run();
    setDetail(null);
  }, [elements]);

  return (
    <section className="pa-panel">
      <div className="pa-panel-head">
        Knowledge Graph
        <div className="pa-seg">
          {["origin", "user", "both"].map((p) => (
            <button key={p} className={"pa-seg-btn" + (plane === p ? " active" : "")} onClick={() => setPlane(p)}>{p}</button>
          ))}
        </div>
      </div>
      <div className="pa-cy" ref={boxRef} />
      {detail && (
        <div className="pa-node-detail">
          <div className="pa-node-label">{detail.label}</div>
          <span className="pa-node-type" style={{ background: (TYPE_COLOR[detail.type] || "#888") + "22", color: TYPE_COLOR[detail.type] || "#888" }}>
            {detail.type} · {detail.plane}
          </span>
          {detail.description && <div className="pa-node-desc">{detail.description}</div>}
        </div>
      )}
    </section>
  );
}

// ── Chat ────────────────────────────────────────────────────────────────────
function ChatMessage({ m, onApplyTag }) {
  const md = m.role === "assistant" ? (m.metadata || {}) : null;
  const score = md?.alignment_score;
  const hasMeta = md && (md.in_scope?.length || md.out_of_scope?.length || md.deviations?.length || md.recommendations?.length);
  return (
    <div className={"pa-msg " + m.role}>
      <div className="pa-msg-head">
        <span className="pa-handle">{m.author ? "@" + m.author.handle : "advisor"}</span>
        <span className="pa-time">{fmtTime(m.timestamp)}</span>
        {score != null && <span className={"pa-score " + scoreClass(score)}>⬡ {score}</span>}
        {(m.tags || []).map((t, i) => <span key={i} className="pa-tag">{t}</span>)}
      </div>
      <div className="pa-body">{m.content}</div>
      {hasMeta ? (
        <div className="pa-meta">
          {md.in_scope?.length ? <div><span className="pa-meta-label">in scope</span>{md.in_scope.map((s, i) => <span key={i} className="pa-chip inc">{s}</span>)}</div> : null}
          {md.out_of_scope?.length ? <div><span className="pa-meta-label">out</span>{md.out_of_scope.map((s, i) => <span key={i} className="pa-chip out">{s}</span>)}</div> : null}
          {md.deviations?.length ? <div><span className="pa-meta-label">deviations</span>{md.deviations.map((s, i) => <span key={i} className="pa-chip dev">⚠ {s}</span>)}</div> : null}
          {md.recommendations?.length ? <div><span className="pa-meta-label">recommend</span>{md.recommendations.map((s, i) => <span key={i} className="pa-chip">{s}</span>)}</div> : null}
        </div>
      ) : null}
      {md?.suggested_tags?.length ? (
        <div className="pa-stags"><span>Suggested:</span>{md.suggested_tags.map((t, i) => <span key={i} className="pa-stag" onClick={() => onApplyTag(t, m.message_id)}>{t}</span>)}</div>
      ) : null}
    </div>
  );
}

function ChatPanel({ messages, filterTag, onFilter, handle, setHandle, draft, setDraft, draftTags, setDraftTags, onSend, onSuggest, onApplyTag, busy }) {
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  const toggle = (t) => setDraftTags((d) => (d.includes(t) ? d.filter((x) => x !== t) : [...d, t]));
  return (
    <section className="pa-panel">
      <div className="pa-panel-head">
        Team Chat
        <select className="pa-select" value={filterTag} onChange={(e) => onFilter(e.target.value)}>
          <option value="">All tags</option>
          {TAGS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="pa-chat">
        {messages.length
          ? messages.map((m) => <ChatMessage key={m.message_id} m={m} onApplyTag={onApplyTag} />)
          : <div className="pa-empty" style={{ flex: "none", padding: "40px 0" }}>No messages yet. Start a conversation.</div>}
        <div ref={endRef} />
      </div>
      <div className="pa-input">
        <div className="pa-row">
          <label>Handle:</label>
          <input className="pa-h" value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@you" />
        </div>
        <textarea
          className="pa-ta" value={draft} onChange={(e) => setDraft(e.target.value)}
          placeholder="Share an idea, sprint plan, or decision…  (Ctrl+Enter to send)"
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) onSend(); }}
        />
        <div className="pa-row">
          {TAGS.map((t) => <span key={t} className={"pa-toggle" + (draftTags.includes(t) ? " active" : "")} onClick={() => toggle(t)}>{t}</span>)}
        </div>
        <div className="pa-send">
          <button className="btn" onClick={onSuggest} disabled={!!busy || !draft.trim()}>Suggest tags</button>
          <button className="btn btn-primary" onClick={onSend} disabled={!!busy || !draft.trim()}>Send</button>
        </div>
      </div>
    </section>
  );
}

// ── Rules + coverage ────────────────────────────────────────────────────────
const RULE_ICON = { ok: "✓", at_risk: "⚠", violated: "✗" };
const RULE_COLOR = { ok: "var(--local)", at_risk: "var(--warn)", violated: "var(--danger)" };

function RulesPanel({ rules, coverage }) {
  const violated = rules.filter((r) => r.violation_status === "violated").length;
  const atRisk = rules.filter((r) => r.violation_status === "at_risk").length;
  return (
    <section className="pa-panel">
      <div className="pa-panel-head">Rules &amp; Coverage</div>
      <div className="pa-cov">
        <div className="pa-cov-label"><span>Goal coverage</span><b>{coverage == null ? "—" : coverage + "%"}</b></div>
        <div className="pa-bar-bg"><div className="pa-bar-fill" style={{ width: (coverage || 0) + "%" }} /></div>
      </div>
      <div className="pa-rules">
        {!rules.length && <div className="pa-empty" style={{ flex: "none", padding: "20px 0" }}>No rules.</div>}
        {(violated || atRisk) > 0 && <div className="pa-dev-banner">⚠ {violated} violated · {atRisk} at risk</div>}
        {rules.map((r, i) => (
          <div className="pa-rule" key={i}>
            <div className="pa-rule-head">
              <span style={{ color: RULE_COLOR[r.violation_status] || "var(--text-muted)" }}>{RULE_ICON[r.violation_status] || "?"}</span>
              <span className="pa-rule-name">{r.name}</span>
              {r.salience != null && <span style={{ fontSize: 10, color: "var(--text-muted)" }}>p{r.salience}</span>}
            </div>
            {r.when && <div className="pa-rule-when"><b>When:</b> {r.when}</div>}
            {r.then && <div className="pa-rule-then"><b>Then:</b> {r.then}</div>}
            {r.sow_excerpt && <div className="pa-rule-src">{r.sow_excerpt.slice(0, 140)}</div>}
          </div>
        ))}
      </div>
    </section>
  );
}

// ── Create / select modal ───────────────────────────────────────────────────
function ProjectModal({ mode, projects, onClose, onOpen, onCreate }) {
  const [name, setName] = useState("");
  const [sow, setSow] = useState("");
  const [file, setFile] = useState(null);
  const submit = () => {
    if (!name.trim() || (!sow.trim() && !file)) return;
    const fd = new FormData();
    fd.append("name", name.trim());
    if (file) fd.append("sow_pdf", file); else fd.append("sow_text", sow.trim());
    onCreate(fd);
  };
  return (
    <div className="pa-overlay" onClick={(e) => { if (e.target.classList.contains("pa-overlay")) onClose(); }}>
      <div className="pa-modal">
        {mode === "create" ? (
          <>
            <h2>New Project</h2>
            <div className="pa-field">
              <label>Project name</label>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="My Project" autoFocus />
            </div>
            <div className="pa-field">
              <label>Statement of Work — paste text</label>
              <textarea value={sow} onChange={(e) => setSow(e.target.value)} placeholder="Goals, features, constraints, actors, milestones…" />
              <div className="pa-divider">or upload a PDF</div>
              <label className={"pa-drop" + (file ? " has" : "")}>
                <input type="file" accept=".pdf" style={{ display: "none" }} onChange={(e) => setFile(e.target.files[0] || null)} />
                {file ? `✓ ${file.name}` : "📄 Click to choose a PDF"}
              </label>
            </div>
            <div className="pa-modal-foot">
              <button className="btn" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" onClick={submit} disabled={!name.trim() || (!sow.trim() && !file)}>Initialize project</button>
            </div>
          </>
        ) : (
          <>
            <h2>Select Project</h2>
            <div className="pa-plist">
              {projects.length ? projects.map((p) => (
                <div className="pa-pitem" key={p.project_id} onClick={() => onOpen(p.project_id, p.name)}>
                  <span style={{ fontWeight: 600 }}>{p.name}</span>
                  <span className="pa-pdate">{p.created_at ? new Date(p.created_at).toLocaleDateString() : ""}</span>
                </div>
              )) : <div style={{ color: "var(--text-muted)", fontSize: 12, padding: "8px 0" }}>No projects yet — create one.</div>}
            </div>
            <div className="pa-modal-foot"><button className="btn" onClick={onClose}>Close</button></div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Main view ───────────────────────────────────────────────────────────────
export default function ProjectAdvisor({ notify }) {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(null);
  const [projectName, setProjectName] = useState("");
  const [plane, setPlane] = useState("both");
  const [elements, setElements] = useState([]);
  const [messages, setMessages] = useState([]);
  const [rules, setRules] = useState([]);
  const [coverage, setCoverage] = useState(null);
  const [filterTag, setFilterTag] = useState("");
  const [handle, setHandle] = useState("me");
  const [draft, setDraft] = useState("");
  const [draftTags, setDraftTags] = useState([]);
  const [busy, setBusy] = useState("");
  const [modal, setModal] = useState(null);

  const refreshProjects = useCallback(async () => {
    try { const ps = await pmListProjects(); setProjects(ps); return ps; } catch { return []; }
  }, []);

  useEffect(() => { (async () => { const ps = await refreshProjects(); setModal(ps.length ? "select" : "create"); })(); }, [refreshProjects]);

  async function openProject(pid, name) {
    setProjectId(pid); setProjectName(name); setModal(null); setFilterTag(""); setBusy("Loading project…");
    try {
      const [msgs, kg, rls, cov] = await Promise.all([pmChatHistory(pid), pmKG(pid, plane), pmRules(pid), pmCoverage(pid)]);
      setMessages(msgs); setElements(kg.elements || []); setRules(rls); setCoverage(cov.percentage ?? null);
    } catch { notify?.("Failed to load project"); } finally { setBusy(""); }
  }

  // Reload the graph when the plane toggle changes for an open project.
  useEffect(() => {
    if (!projectId) return;
    pmKG(projectId, plane).then((kg) => setElements(kg.elements || [])).catch(() => {});
  }, [plane, projectId]);

  async function reloadSidePanels() {
    if (!projectId) return;
    try {
      const [kg, rls, cov] = await Promise.all([pmKG(projectId, plane), pmRules(projectId), pmCoverage(projectId)]);
      setElements(kg.elements || []); setRules(rls); setCoverage(cov.percentage ?? null);
    } catch { /* non-fatal */ }
  }

  async function send() {
    const content = draft.trim();
    if (!content || !projectId) return;
    setBusy("Analyzing…");
    try {
      const r = await pmSendMessage(projectId, { author_handle: handle || "anon", author_id: handle || "anon", content, tags: draftTags });
      setMessages((m) => [...m, r.user_message, r.assistant_message]);
      setDraft(""); setDraftTags([]);
      await reloadSidePanels();
    } catch (e) { notify?.("Send failed: " + e.message); } finally { setBusy(""); }
  }

  async function suggest() {
    const content = draft.trim();
    if (!content || !projectId) return;
    setBusy("Suggesting…");
    try {
      const r = await pmSuggestTags(projectId, content);
      setDraftTags(r.suggested_tags || []);
      notify?.((r.suggested_tags || []).length ? "Suggested: " + r.suggested_tags.join(" ") : "No tag suggestions");
    } catch { /* ignore */ } finally { setBusy(""); }
  }

  async function applyFilter(tag) {
    setFilterTag(tag);
    if (!projectId) return;
    try { setMessages(await pmChatHistory(projectId, tag)); } catch { /* ignore */ }
  }

  async function applySuggestedTag(tag, msgId) {
    const idx = messages.findIndex((m) => m.message_id === msgId);
    const target = idx > 0 && messages[idx - 1].role === "user" ? messages[idx - 1] : null;
    if (!target || (target.tags || []).includes(tag)) return;
    const tags = [...(target.tags || []), tag];
    setMessages((ms) => ms.map((m) => (m.message_id === target.message_id ? { ...m, tags } : m)));
    try { await pmUpdateTags(projectId, target.message_id, tags); } catch { /* ignore */ }
  }

  async function createProject(formData) {
    setModal(null); setBusy("Initializing — extracting KG & rules (~30s)…");
    try {
      const r = await pmCreateProject(formData);
      await refreshProjects();
      await openProject(r.project_id, r.name);
      notify?.(`Project "${r.name}" created`);
    } catch (e) { notify?.("Create failed: " + e.message); setBusy(""); }
  }

  return (
    <div className="pa-root">
      <div className="pa-bar">
        <span className="pa-proj">{projectName || "No project selected"}</span>
        {busy && <span className="pa-busy"><span className="pa-spinner" /> {busy}</span>}
        <div className="pa-bar-actions">
          <button className="btn" onClick={async () => { await refreshProjects(); setModal("select"); }}>Switch project</button>
          <button className="btn btn-primary" onClick={() => setModal("create")}>+ New project</button>
        </div>
      </div>

      {!projectId ? (
        <div className="pa-empty">Select or create a project to begin.</div>
      ) : (
        <div className="pa-grid">
          <KGPanel plane={plane} setPlane={setPlane} elements={elements} />
          <ChatPanel
            messages={messages} filterTag={filterTag} onFilter={applyFilter}
            handle={handle} setHandle={setHandle} draft={draft} setDraft={setDraft}
            draftTags={draftTags} setDraftTags={setDraftTags}
            onSend={send} onSuggest={suggest} onApplyTag={applySuggestedTag} busy={busy}
          />
          <RulesPanel rules={rules} coverage={coverage} />
        </div>
      )}

      {modal && (
        <ProjectModal mode={modal} projects={projects} onClose={() => setModal(null)} onOpen={openProject} onCreate={createProject} />
      )}
    </div>
  );
}
