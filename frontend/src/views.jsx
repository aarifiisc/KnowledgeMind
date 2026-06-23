import { useEffect, useRef, useState } from "react";
import { getJSON, postJSON, postForm } from "./api";

/* ---- helpers ------------------------------------------------------------- */
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const trunc = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s || "");
const dt = (ts) => new Date(ts * 1000);
const fmtTime = (ts) => dt(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const fmtDay = (ts) => dt(ts).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });

const svg = (d) => <svg viewBox="0 0 24 24" className="icon">{d}</svg>;
const ShieldIcon = svg(<><path d="M12 2l8 4v6c0 5-3.4 8.5-8 10-4.6-1.5-8-5-8-10V6l8-4z" /><path d="M9 12l2 2 4-4" /></>);
const AlertIcon = svg(<><path d="M10.3 3.3l-8 14A2 2 0 0 0 4 20h16a2 2 0 0 0 1.7-2.7l-8-14a2 2 0 0 0-3.4 0z" /><path d="M12 9v4" /><path d="M12 17h.01" /></>);
const SendIcon = svg(<><path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4 20-7z" /></>);
const DocIcon = svg(<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></>);

const TypeBadge = ({ t }) => {
  const k = (t || "").toLowerCase();
  const cls = k === "hard" ? "badge-hard" : k === "soft" ? "badge-soft" : "badge-tentative";
  return <span className={"badge " + cls}>{t}</span>;
};
const SrcBadge = ({ s }) => <span className="badge badge-src">{s}</span>;
const Empty = ({ big, title, sub }) => (
  <div className="empty"><div className="big">{big}</div><strong>{title}</strong><div>{sub}</div></div>
);

/* ---- Dashboard ----------------------------------------------------------- */
export function Dashboard({ refresh }) {
  const [commitments, setCommitments] = useState([]);
  const [conflicts, setConflicts] = useState([]);
  const [counts, setCounts] = useState({ real: 0, dup: 0 });

  useEffect(() => {
    Promise.all([getJSON("/api/commitments"), getJSON("/api/conflicts")])
      .then(([c1, c2]) => {
        setCommitments(c1.commitments || []);
        setConflicts(c2.conflicts || []);
        setCounts({ real: c2.real_count, dup: c2.duplicate_count });
      })
      .catch(() => {});
  }, [refresh]);

  const sources = new Set(commitments.map((c) => c.source));
  const kpis = [
    { n: commitments.length, l: "Commitments tracked" },
    { n: counts.real, l: "Active conflicts", alert: counts.real > 0 },
    { n: counts.dup, l: "Same-event duplicates" },
    { n: sources.size, l: "Channels" },
  ];
  const groups = [];
  let lastDay = "";
  for (const c of commitments) {
    const d = fmtDay(c.start_ts);
    if (d !== lastDay) { groups.push({ day: d, items: [] }); lastDay = d; }
    groups[groups.length - 1].items.push(c);
  }

  return (
    <>
      <div className="privacy-banner">{ShieldIcon}<div><strong>All personal data stays on your device.</strong> KnowledgeMind watches your channels locally and only sends non-sensitive lookups to the cloud.</div></div>
      <div className="kpi-row">
        {kpis.map((k, i) => <div key={i} className={"kpi" + (k.alert ? " alert" : "")}><div className="num">{k.n}</div><div className="lbl">{k.l}</div></div>)}
      </div>
      <h2 className="section-title">Conflict alerts</h2>
      <div className="stack">
        {conflicts.length === 0
          ? <Empty big="✅" title="No conflicts detected" sub="Your schedule is clear across all channels." />
          : conflicts.map((c) => <ConflictCard key={c.id} c={c} />)}
      </div>
      <h2 className="section-title">Upcoming commitments</h2>
      <div className="stack">
        {commitments.length === 0
          ? <Empty big="🗓️" title="No commitments yet" sub="Run a scan to ingest your channels." />
          : groups.map((g, i) => (
            <div key={i}>
              <div className="day-label">{g.day}</div>
              {g.items.map((c) => (
                <div className="tl" key={c.id} style={{ marginTop: 8 }}>
                  <div className="time">{fmtTime(c.start_ts)}</div>
                  <div className="body">
                    <div className="t">{c.description}</div>
                    <div className="m"><SrcBadge s={c.source} /> <TypeBadge t={c.commitment_type} /> {c.who && c.who !== "(self)" ? <span>· with {c.who}</span> : null}</div>
                  </div>
                </div>
              ))}
            </div>
          ))}
      </div>
    </>
  );
}

function ConflictCard({ c }) {
  const dup = c.same_event;
  return (
    <div className={"card conflict" + (dup ? " dup" : "")}>
      <div className="conflict-head">{AlertIcon}<h3>{dup ? "Possible duplicate across channels" : "Scheduling conflict"}</h3><span className="tag">{dup ? "Same event" : "Conflict"}</span></div>
      <div className="vs">
        <div className="leg"><div className="t">{trunc(c.a_desc, 40)}</div><div className="m"><SrcBadge s={c.a_src} /> <span>{fmtTime(c.a_start)}</span></div></div>
        <div className="x">overlaps</div>
        <div className="leg"><div className="t">{trunc(c.b_desc, 40)}</div><div className="m"><SrcBadge s={c.b_src} /> <span>{fmtTime(c.b_start)}</span></div></div>
      </div>
      <div className="m" style={{ marginTop: 11, color: "var(--text-muted)", fontSize: 12.5 }}>
        {Math.round(c.overlap_minutes)} min overlap{dup ? " · likely the same real event (entity de-dup is future work)" : ""}
      </div>
    </div>
  );
}

/* ---- Knowledge Graph ----------------------------------------------------- */
export function Graph({ refresh }) {
  const [html, setHtml] = useState("");
  useEffect(() => {
    Promise.all([getJSON("/api/commitments"), getJSON("/api/conflicts")])
      .then(([c1, c2]) => setHtml(buildGraphSVG(c1.commitments || [], c2.conflicts || [])))
      .catch(() => setHtml(""));
  }, [refresh]);
  return (
    <div className="card">
      <div className="graph-legend">
        <span className="lg"><i className="dot dot-person"></i> Person</span>
        <span className="lg"><i className="dot dot-cal"></i> Calendar</span>
        <span className="lg"><i className="dot dot-chat"></i> Chat</span>
        <span className="lg"><i className="line line-conflict"></i> Conflict</span>
      </div>
      <div className="graph-wrap" dangerouslySetInnerHTML={{ __html: html || "<div class='empty'><div class='big'>🕸️</div><strong>Graph is empty</strong><div>Run a scan first.</div></div>" }} />
    </div>
  );
}

function buildGraphSVG(commitments, conflicts) {
  if (!commitments.length) return "";
  const whoOf = (c) => (c.who && c.who !== "(self)" ? c.who : "You");
  const persons = [];
  for (const c of commitments) { const w = whoOf(c); if (!persons.includes(w)) persons.push(w); }
  persons.sort((a, b) => (a === "You" ? -1 : b === "You" ? 1 : a.localeCompare(b)));

  const topPad = 34, gap = 70, leftX = 90, cardX = 430, cardW = 300, cardH = 46;
  const rows = commitments.length;
  const H = topPad * 2 + (rows - 1) * gap + cardH;
  const W = cardX + cardW + 100;
  const commY = (j) => topPad + j * gap;
  const span = rows <= 1 ? 0 : (rows - 1) * gap;
  const personY = (i) => topPad + cardH / 2 + (persons.length <= 1 ? span / 2 : (i * span) / (persons.length - 1));

  const idx = new Map();
  commitments.forEach((c, j) => idx.set(c.description + "@" + c.start_ts, j));

  let edges = "", conflictEdges = "", nodes = "";
  commitments.forEach((c, j) => {
    const pi = persons.indexOf(whoOf(c));
    const x1 = leftX + 22, y1 = personY(pi), x2 = cardX, y2 = commY(j) + cardH / 2, mx = (x1 + x2) / 2;
    edges += `<path class="gedge" d="M${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}"/>`;
  });
  conflicts.forEach((cf) => {
    const ja = idx.get(cf.a_desc + "@" + cf.a_start), jb = idx.get(cf.b_desc + "@" + cf.b_start);
    if (ja === undefined || jb === undefined) return;
    const x = cardX + cardW, ya = commY(ja) + cardH / 2, yb = commY(jb) + cardH / 2;
    const bulge = x + 56 + Math.abs(ya - yb) * 0.12;
    const stroke = cf.same_event ? "var(--warn)" : "var(--danger)";
    conflictEdges += `<path class="gconflict" style="stroke:${stroke}" d="M${x} ${ya} C ${bulge} ${ya}, ${bulge} ${yb}, ${x} ${yb}"/>`;
    conflictEdges += `<text class="gconflict-label" style="fill:${stroke}" x="${bulge - 6}" y="${(ya + yb) / 2}">${Math.round(cf.overlap_minutes)}m</text>`;
  });
  persons.forEach((p, i) => {
    const y = personY(i), init = p === "You" ? "★" : p.slice(0, 1).toUpperCase();
    nodes += `<g><circle class="gperson" cx="${leftX}" cy="${y}" r="20"/><text class="gperson-init" x="${leftX}" y="${y + 4}" text-anchor="middle">${esc(init)}</text><text class="gnode-label" x="${leftX}" y="${y + 36}" text-anchor="middle">${esc(trunc(p, 12))}</text></g>`;
  });
  commitments.forEach((c, j) => {
    const y = commY(j), cls = c.source === "calendar" ? "cal" : "chat";
    nodes += `<g><rect class="gcard ${cls}" x="${cardX}" y="${y}" width="${cardW}" height="${cardH}" rx="10"/><text class="gnode-label" x="${cardX + 14}" y="${y + 19}">${esc(trunc(c.description, 34))}</text><text class="gnode-sub" x="${cardX + 14}" y="${y + 36}">${esc(c.source)} · ${esc(c.commitment_type)}</text></g>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMin meet">${edges}${conflictEdges}${nodes}</svg>`;
}

/* ---- Assistant ----------------------------------------------------------- */
export function Assistant() {
  const [msgs, setMsgs] = useState([{ role: "bot", text: "Hi! I'm KnowledgeMind. Ask about your schedule, or try “Do I have any conflicts this week?” Personal-data tasks always run on-device." }]);
  const [input, setInput] = useState("");
  const [level, setLevel] = useState("L1");
  const [busy, setBusy] = useState(false);
  const threadRef = useRef(null);
  useEffect(() => { if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight; }, [msgs]);

  async function send(e) {
    e.preventDefault();
    const m = input.trim();
    if (!m || busy) return;
    setInput("");
    setMsgs((x) => [...x, { role: "user", text: m }]);
    setBusy(true);
    try {
      const r = await postJSON("/api/chat", { message: m, level });
      setMsgs((x) => [...x, { role: "bot", text: r.answer, routing: r.routing_log, demo: r.demo_mode }]);
    } catch {
      setMsgs((x) => [...x, { role: "bot", text: "Sorry — the assistant is unavailable." }]);
    }
    setBusy(false);
  }

  return (
    <div className="chat">
      <div className="chat-thread" ref={threadRef}>
        {msgs.map((msg, i) => (
          <div key={i} className={"msg " + msg.role}>
            <div className="bubble">{msg.text}</div>
            {msg.routing && msg.routing.length ? <RouteChips log={msg.routing} /> : null}
            {msg.demo ? <div className="demo-note">demo response · add a model for live answers</div> : null}
          </div>
        ))}
      </div>
      <form className="composer" onSubmit={send}>
        <select className="select" value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="L1">L1 · quick</option><option value="L2">L2 · plan</option><option value="L3">L3 · agent</option>
        </select>
        <input className="input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask anything — e.g. “Do I have any conflicts this week?”" />
        <button className="btn btn-primary" type="submit" aria-label="Send">{SendIcon}</button>
      </form>
    </div>
  );
}

function RouteChips({ log }) {
  return (
    <div className="route">
      {log.map((e, i) => {
        const label = e.action || e.tool || e.step || e.node || "step";
        const raw = JSON.stringify(e).toUpperCase();
        const cloud = raw.includes("CLOUD");
        const word = cloud ? "CLOUD" : raw.includes("LOCAL") ? "LOCAL" : "—";
        return <span key={i} className={"badge " + (cloud ? "badge-cloud" : "badge-local")}>{label} · {word}</span>;
      })}
    </div>
  );
}

/* ---- Documents ----------------------------------------------------------- */
export function Documents() {
  const [docs, setDocs] = useState([]);
  const [status, setStatus] = useState("");
  const fileRef = useRef(null);
  const load = () => getJSON("/api/documents").then((d) => setDocs(d.documents || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  async function upload(e) {
    e.preventDefault();
    const f = fileRef.current.files[0];
    if (!f) { setStatus("Choose a file first."); return; }
    setStatus("Indexing…");
    const fd = new FormData();
    fd.append("file", f);
    try {
      const j = await postForm("/api/documents", fd);
      setStatus(j.error ? `Error: ${j.error}` : `Indexed “${f.name}”.`);
      fileRef.current.value = "";
      load();
    } catch {
      setStatus("Upload failed.");
    }
  }

  return (
    <>
      <div className="card">
        <h2 className="section-title" style={{ marginTop: 0 }}>Add a document</h2>
        <p style={{ color: "var(--text-muted)", fontSize: 13, margin: "0 0 12px" }}>Upload a PDF, TXT, or MD file. It's chunked and indexed locally (on-device) so the assistant can answer from it — nothing leaves your device.</p>
        <form className="composer" style={{ padding: 0, border: "none" }} onSubmit={upload}>
          <input className="input" type="file" accept=".pdf,.txt,.md" ref={fileRef} />
          <button className="btn btn-primary" type="submit">Upload</button>
        </form>
        <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 10 }}>{status}</div>
      </div>
      <h2 className="section-title">Indexed documents</h2>
      <div className="stack">
        {docs.length === 0
          ? <Empty big="📄" title="No documents yet" sub="Upload a PDF, TXT, or MD file above." />
          : docs.map((d, i) => <div className="doc-row" key={i}>{DocIcon}<span>{d}</span></div>)}
      </div>
    </>
  );
}

/* ---- Settings ------------------------------------------------------------ */
export function Settings() {
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({ local_model: "", google_credentials_path: "", complexity_threshold: 0.6, groq_api_key: "", tavily_api_key: "", slack_bot_token: "" });
  const [status, setStatus] = useState("");

  useEffect(() => {
    getJSON("/api/config").then((c) => {
      setCfg(c);
      setForm((f) => ({ ...f, local_model: c.local_model || "", google_credentials_path: c.google_credentials_path || "", complexity_threshold: c.complexity_threshold ?? 0.6 }));
    }).catch(() => {});
  }, []);

  const upd = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save() {
    const body = {};
    ["local_model", "groq_api_key", "tavily_api_key", "slack_bot_token", "google_credentials_path"].forEach((k) => {
      if (form[k] && String(form[k]).trim()) body[k] = String(form[k]).trim();
    });
    const num = parseFloat(form.complexity_threshold);
    if (!Number.isNaN(num)) body.complexity_threshold = num;
    setStatus("Saving…");
    try {
      const r = await postJSON("/api/config", body);
      setStatus(`Saved ${(r.saved || []).length} field(s).`);
      setForm((f) => ({ ...f, groq_api_key: "", tavily_api_key: "", slack_bot_token: "" }));
    } catch {
      setStatus("Save failed.");
    }
  }

  const hint = (s) => (s ? <span className="set-hint">✓ set</span> : null);

  return (
    <div className="card">
      <h2 className="section-title" style={{ marginTop: 0 }}>Models &amp; keys</h2>
      <div className="form-grid">
        <label>Local model (Ollama)<input className="input" value={form.local_model} onChange={upd("local_model")} placeholder="qwen2.5:3b" /></label>
        <label>Complexity threshold (cloud routing)<input className="input" type="number" min="0" max="1" step="0.05" value={form.complexity_threshold} onChange={upd("complexity_threshold")} /></label>
        <label>Groq API key {cfg && hint(cfg.groq_api_key_set)}<input className="input" type="password" value={form.groq_api_key} onChange={upd("groq_api_key")} placeholder="gsk_..." /></label>
        <label>Tavily API key {cfg && hint(cfg.tavily_api_key_set)}<input className="input" type="password" value={form.tavily_api_key} onChange={upd("tavily_api_key")} placeholder="tvly-..." /></label>
        <label>Slack bot token {cfg && hint(cfg.slack_bot_token_set)}<input className="input" type="password" value={form.slack_bot_token} onChange={upd("slack_bot_token")} placeholder="xoxb-..." /></label>
        <label>Google credentials path<input className="input" value={form.google_credentials_path} onChange={upd("google_credentials_path")} placeholder="./credentials.json" /></label>
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 16 }}>
        <button className="btn btn-primary" onClick={save}>Save settings</button>
        <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{status}</span>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: 12.5, margin: "16px 0 0" }}>Keys are stored locally in your config file. Personal-data tasks always run on the local model; only low-sensitivity tasks may use the cloud model.</p>
    </div>
  );
}
