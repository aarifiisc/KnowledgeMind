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
const ChartIcon = svg(<><path d="M3 3v18h18" /><rect x="7" y="10" width="3" height="7" /><rect x="12" y="6" width="3" height="11" /><rect x="17" y="13" width="3" height="4" /></>);
const BellIcon = svg(<><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></>);

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

/* ---- Connectors (Hermes signal sources) ---------------------------------- */
const CONN_META = {
  strava: { label: "Strava", icon: "🏃", sub: "Fitness & activity" },
  apple_health: { label: "Apple Health", icon: "❤️", sub: "Sleep & recovery" },
  todoist: { label: "Todoist", icon: "✓", sub: "Task load" },
  spotify: { label: "Spotify", icon: "🎵", sub: "Listening mood" },
};
const CONN_ORDER = ["strava", "apple_health", "todoist", "spotify"];
const CONN_HIDE = ["success", "source", "formatted", "summary", "available"];

export function Connectors({ refresh }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    getJSON("/api/connectors").then((d) => setData(d.connectors || {})).catch(() => setData({}));
  }, [refresh]);

  if (!data) return <Empty big="⏳" title="Loading connectors…" sub="" />;

  return (
    <>
      <div className="privacy-banner">{ShieldIcon}<div><strong>These signals are derived on-device.</strong> Raw GPS, biometrics, and track names never leave your machine — only summary signals + their routing stays LOCAL.</div></div>
      <div className="conn-grid">
        {CONN_ORDER.map((k) => {
          const c = data[k] || {};
          const meta = CONN_META[k];
          const signals = Object.entries(c).filter(([key, v]) => !CONN_HIDE.includes(key) && typeof v !== "object");
          return (
            <div className="card conn-card" key={k}>
              <div className="conn-head">
                <span className="conn-icon">{meta.icon}</span>
                <div><div className="conn-title">{meta.label}</div><div className="conn-sub">{meta.sub}</div></div>
                <span className={"chip " + (c.source === "live" ? "chip-live" : "chip-demo")} style={{ marginLeft: "auto" }}>{c.source === "live" ? "● live" : "mock"}</span>
              </div>
              <div className="conn-summary">{c.summary || c.formatted || "(no data)"}</div>
              {signals.length > 0 && (
                <div className="conn-signals">
                  {signals.slice(0, 6).map(([key, val]) => (
                    <div className="conn-signal" key={key}><span className="k">{key.replace(/_/g, " ")}</span><span className="v">{String(val)}</span></div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
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
      setMsgs((x) => [...x, { role: "bot", text: r.answer, routing: r.routing_log, demo: r.demo_mode, privacy: r.privacy }]);
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
            {msg.privacy ? <PrivacyBadge p={msg.privacy} /> : null}
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

// Honest per-turn badge: reflects what ACTUALLY executed, including fallbacks.
function PrivacyBadge({ p }) {
  if (!p) return null;
  if (p.personal_fallback)
    return <div className="route"><span className="badge badge-cloud" title="On-device model unavailable — personal data fell back to the cloud this turn">⚠ Cloud fallback · personal</span></div>;
  if (p.fallback_blocked)
    return <div className="route"><span className="badge badge-local" title="On-device model unavailable — fail-closed kept personal data on your device">🔒 Local-only · fail-closed</span></div>;
  return <div className="route"><span className={"badge " + (p.cloud ? "badge-cloud" : "badge-local")}>{p.cloud ? "Cloud" : "Local"} · this turn</span></div>;
}

/* ---- Privacy dashboard --------------------------------------------------- */
export function Privacy({ refresh }) {
  const [report, setReport] = useState(null);
  const [records, setRecords] = useState([]);
  useEffect(() => {
    Promise.all([getJSON("/api/privacy/report"), getJSON("/api/audit?limit=40")])
      .then(([rep, aud]) => { setReport(rep); setRecords((aud.records || []).slice().reverse()); })
      .catch(() => {});
  }, [refresh]);
  if (!report) return <Empty big="🔒" title="Loading privacy report…" sub="" />;
  const kpis = [
    { n: report.pct_local + "%", l: "Decisions routed LOCAL" },
    { n: report.leaks_prevented, l: "Leaks prevented (fail-closed)" },
    { n: report.personal_fallbacks, l: "Personal cloud fallbacks", alert: report.personal_fallbacks > 0 },
    { n: report.total_decisions, l: "Routing decisions" },
  ];
  return (
    <>
      <div className="privacy-banner">{ShieldIcon}<div><strong>Provable privacy.</strong> Every routing decision and every local→cloud fallback is logged here. Personal work fails closed when the on-device model is unavailable — toggle it in Settings.</div></div>
      <div className="kpi-row">{kpis.map((k, i) => <div key={i} className={"kpi" + (k.alert ? " alert" : "")}><div className="num">{k.n}</div><div className="lbl">{k.l}</div></div>)}</div>
      <h2 className="section-title">Recent decisions</h2>
      <div className="stack">
        {records.length === 0
          ? <Empty big="🗂️" title="No activity yet" sub="Ask the assistant something to populate the trail." />
          : records.map((r, i) => <AuditRow key={i} r={r} />)}
      </div>
    </>
  );
}

function AuditRow({ r }) {
  const row = { display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", background: "var(--surface)", marginBottom: 6 };
  const main = { flex: 1, fontSize: 13 };
  const sub = { fontSize: 12, color: "var(--text-muted)" };
  if (r.kind === "fallback") {
    const cls = r.blocked ? "badge-local" : "badge-cloud";
    return <div style={row}><span className={"badge " + cls}>{r.blocked ? "🔒 fail-closed" : "⚠ cloud fallback"}</span><span style={main}>{r.node}{r.personal ? " · personal" : ""}</span><span style={sub}>{r.model || ""}</span></div>;
  }
  const cloud = r.decision === "cloud";
  return <div style={row}><span className={"badge " + (cloud ? "badge-cloud" : "badge-local")}>{r.decision}</span><span style={main}>{r.tool || "(reasoning)"}</span><span style={sub}>privacy {r.privacy_score}</span></div>;
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

/* ---- Proactive Runtime --------------------------------------------------- */

function Md({ text }) {
  if (!text) return null;
  return (
    <div className="md-body">
      {text.split("\n").map((line, i) => {
        const parts = line.split(/(\*\*[^*]+\*\*)/g);
        return (
          <div key={i} className={line === "" ? "md-blank" : undefined}>
            {parts.map((p, j) => p.startsWith("**") && p.endsWith("**")
              ? <strong key={j}>{p.slice(2, -2)}</strong>
              : p)}
          </div>
        );
      })}
    </div>
  );
}

function relTime(iso) {
  if (!iso) return "";
  const ms = new Date(iso).getTime();
  if (isNaN(ms)) return iso;
  const diff = (Date.now() - ms) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" });
}

function humanCron(expr) {
  if (!expr) return expr;
  const p = expr.trim().split(/\s+/);
  if (p.length !== 5) return expr;
  const [min, hr, dom, mon, dow] = p;
  if (dom === "*" && mon === "*" && dow === "*") {
    if (/^\d+$/.test(min) && /^\d+$/.test(hr))
      return `Daily ${hr.padStart(2, "0")}:${min.padStart(2, "0")}`;
    if (/^\*\/\d+$/.test(hr) && min === "0")
      return `Every ${hr.replace("*/", "")}h`;
    if (/^\*\/\d+$/.test(min))
      return `Every ${min.replace("*/", "")} min`;
  }
  return expr;
}

const CheckIcon = svg(<polyline points="20 6 9 17 4 12"/>);
const ClockIcon = svg(<><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></>);
const SilentIcon = svg(<path d="M5 12h14"/>);

export function Proactive({ refresh, notify }) {
  const [briefing, setBriefing] = useState(null);
  const [nudges, setNudges] = useState([]);
  const [activeCount, setActiveCount] = useState(0);
  const [jobs, setJobs] = useState([]);
  const [jobErrors, setJobErrors] = useState([]);
  const [firing, setFiring] = useState(false);
  const [lastTick, setLastTick] = useState(null);
  const [showDismissed, setShowDismissed] = useState(false);

  function fetchAll(withDismissed) {
    const d = withDismissed !== undefined ? withDismissed : showDismissed;
    Promise.all([
      getJSON("/api/briefing"),
      getJSON("/api/nudges" + (d ? "?include_dismissed=true" : "")),
      getJSON("/api/nudges/jobs"),
    ]).then(([b, n, j]) => {
      setBriefing(b.briefing || null);
      setNudges(n.nudges || []);
      setActiveCount(n.active_count || 0);
      setJobs(j.jobs || []);
      setJobErrors(j.errors || []);
    }).catch(() => {});
  }

  useEffect(() => { fetchAll(showDismissed); }, [refresh, showDismissed]);

  async function runNow() {
    setFiring(true);
    try {
      const fired = [];
      for (const job of jobs) {
        const r = await postJSON(`/api/nudges/run/${encodeURIComponent(job.name)}`).catch(() => null);
        if (!r) continue;
        fired.push({
          job: job.name,
          surfaced: !!r.surfaced,
          nudge_id: r.nudge && r.nudge.id,
          answer: r.nudge && r.nudge.message,
          reason: r.message,
          routing_log: [],
        });
      }
      setLastTick(fired);
      fetchAll();
      const surfaced = fired.filter((f) => f.surfaced).length;
      notify(`${jobs.length} skill(s) ran · ${surfaced} new nudge(s)`);
    } catch {
      notify("Run failed — check the backend logs.");
    }
    setFiring(false);
  }

  async function dismiss(id) {
    setNudges((prev) => prev.filter((n) => n.id !== id));
    setActiveCount((c) => Math.max(0, c - 1));
    await postJSON(`/api/nudges/${id}/dismiss`).catch(() => {});
  }

  const visibleNudges = showDismissed ? nudges : nudges.filter((n) => !n.dismissed);
  const activeNudges = visibleNudges.filter((n) => !n.suppressed && !n.dismissed);
  const suppressedNudges = visibleNudges.filter((n) => n.suppressed);

  return (
    <div className="view">
      <div className="privacy-banner">
        {ShieldIcon}
        <div><strong>Every skill routes through the privacy layer.</strong> Personal data runs on-device (LOCAL). Nudges are stored only in your local database and never sent to the cloud.</div>
      </div>

      <div className="proactive-toprow">
        <div>
          <h2 className="section-title" style={{ margin: 0 }}>Today</h2>
          {briefing && <div className="briefing-headline">{briefing.headline}</div>}
        </div>
        <button className="btn btn-primary" onClick={runNow} disabled={firing}>
          {ClockIcon}<span>{firing ? "Running…" : "Run now"}</span>
        </button>
      </div>

      <div className="kpi-row" style={{ marginTop: 16 }}>
        <div className="kpi"><div className="num">{activeCount}</div><div className="lbl">Active nudges</div></div>
        <div className="kpi"><div className="num">{jobs.length}</div><div className="lbl">Scheduled skills</div></div>
        <div className="kpi"><div className="num">{briefing ? briefing.commitments_today.length : "—"}</div><div className="lbl">Commitments today</div></div>
        <div className={"kpi" + (briefing && briefing.conflicts && briefing.conflicts.length > 0 ? " alert" : "")}>
          <div className="num">{briefing ? briefing.conflicts.length : "—"}</div>
          <div className="lbl">Conflicts</div>
        </div>
      </div>

      <h2 className="section-title">Daily Briefing</h2>
      <div className="card">
        {!briefing
          ? <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading briefing…</div>
          : briefing.surface === false
          ? <Empty big="🌅" title="Looks like a quiet day" sub="Nothing scheduled — enjoy the open space." />
          : (
            <>
              <Md text={briefing.formatted} />
              {(briefing.task_load || briefing.readiness) && (
                <div className="briefing-chips">
                  {briefing.task_load && (
                    <>
                      <span className={"chip " + (briefing.task_load.heavy_day ? "chip-demo" : "chip-muted")}>
                        {briefing.task_load.due_today} due today
                      </span>
                      {briefing.task_load.overdue > 0 && (
                        <span className="chip chip-demo">{briefing.task_load.overdue} overdue</span>
                      )}
                    </>
                  )}
                  {briefing.readiness && briefing.readiness.recovery_status && (
                    <span className={"chip " + (briefing.readiness.low_hrv ? "chip-demo" : "chip-live")}>
                      Recovery: {briefing.readiness.recovery_status}
                    </span>
                  )}
                  {briefing.readiness && briefing.readiness.sleep_hours != null && (
                    <span className="chip chip-muted">Slept {briefing.readiness.sleep_hours}h</span>
                  )}
                </div>
              )}
            </>
          )
        }
      </div>

      <div className="section-title-row">
        <h2 className="section-title" style={{ margin: 0 }}>Nudge Feed</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {activeCount > 0 && <span className="nudge-count-badge">{activeCount} active</span>}
          <button className="btn" style={{ fontSize: 12, padding: "5px 11px" }} onClick={() => setShowDismissed((x) => !x)}>
            {showDismissed ? "Hide dismissed" : "Show dismissed"}
          </button>
        </div>
      </div>
      <div className="stack">
        {activeNudges.length === 0 && suppressedNudges.length === 0
          ? <Empty big="🔔" title="No nudges yet" sub='Press "Run now" to fire the scheduled skills.' />
          : activeNudges.map((n) => (
            <div key={n.id} className="tl nudge-item">
              <div className="nudge-time">{relTime(n.iso)}</div>
              <div className="body nudge-body"><Md text={n.message} /><div className="nudge-skill"><span className="badge badge-src">{n.skill || n.job_name}</span></div></div>
              <button className="nudge-dismiss" aria-label="Dismiss" onClick={() => dismiss(n.id)}>✕</button>
            </div>
          ))
        }
        {suppressedNudges.length > 0 && (
          <>
            <div className="day-label" style={{ marginTop: 4, opacity: 0.7 }}>Held — quiet hours</div>
            {suppressedNudges.map((n) => (
              <div key={n.id} className="tl nudge-item nudge-suppressed">
                <div className="nudge-time">{relTime(n.iso)}</div>
                <div className="body nudge-body"><Md text={n.message} /><div className="nudge-skill"><span className="badge badge-src">{n.skill || n.job_name}</span></div></div>
              </div>
            ))}
          </>
        )}
      </div>

      <h2 className="section-title">Scheduled Skills</h2>
      <div className="stack">
        {jobs.length === 0
          ? <Empty big="⚙️" title="No jobs loaded" sub="Check that hermes_jobs/*.json files are present." />
          : jobs.map((job) => (
            <div key={job.name} className="tl job-row">
              <div className="job-dot" />
              <div className="body">
                <div className="t" style={{ fontWeight: 580 }}>{job.name.replace(/_/g, " ")}</div>
                <div className="m" style={{ marginTop: 5 }}>
                  <span className="job-schedule">{humanCron(job.schedule)}</span>
                  <span className="badge badge-local">{job.skill}</span>
                  {job.quiet_hours_aware && <span className="badge badge-src">quiet hours</span>}
                </div>
              </div>
              <div className="job-lastrun"><span style={{ opacity: 0.45 }}>scheduled</span></div>
            </div>
          ))
        }
        {jobErrors.length > 0 && (
          <div className="card" style={{ borderLeft: "3px solid var(--danger)" }}>
            <strong style={{ color: "var(--danger)", fontSize: 13 }}>Load warnings</strong>
            {jobErrors.map((e, i) => <div key={i} style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4 }}>{e}</div>)}
          </div>
        )}
      </div>

      {lastTick && (
        <>
          <h2 className="section-title">Last Run · Activity Trace</h2>
          <div className="stack">
            {lastTick.map((item, i) => (
              <div key={i} className={"card trace-item" + (item.surfaced ? " trace-surfaced" : item.suppressed ? " trace-suppressed" : " trace-silent")}>
                <div className="trace-head">
                  <span className="trace-icon">{item.surfaced ? CheckIcon : item.suppressed ? ClockIcon : SilentIcon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="trace-job">{item.job}</div>
                    <div style={{ fontSize: 12, marginTop: 2 }}>
                      {item.surfaced
                        ? <span style={{ color: "var(--local)", fontWeight: 600 }}>Nudge #{item.nudge_id} created</span>
                        : item.suppressed
                        ? <span style={{ color: "var(--text-muted)" }}>Suppressed · quiet hours</span>
                        : <span style={{ color: "var(--text-muted)" }}>{item.reason || "Skill chose to stay silent"}</span>}
                    </div>
                  </div>
                  {item.routing_log && item.routing_log.length > 0 && (
                    <div className="route" style={{ flexShrink: 0 }}>
                      {item.routing_log.map((e, j) => {
                        const cloud = (JSON.stringify(e).toUpperCase()).includes("CLOUD");
                        return <span key={j} className={"badge " + (cloud ? "badge-cloud" : "badge-local")}>{e.tool || e.action || "step"} · {cloud ? "CLOUD" : "LOCAL"}</span>;
                      })}
                    </div>
                  )}
                </div>
                {item.surfaced && item.answer && (
                  <div className="trace-answer"><Md text={item.answer} /></div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ---- Settings ------------------------------------------------------------ */
export function Settings() {
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({ local_model: "", google_credentials_path: "", complexity_threshold: 0.6, groq_api_key: "", tavily_api_key: "", slack_bot_token: "", allow_cloud_fallback: true });
  const [status, setStatus] = useState("");
  const [janitor, setJanitor] = useState(null);
  const [cleaning, setCleaning] = useState(false);

  useEffect(() => {
    getJSON("/api/config").then((c) => {
      setCfg(c);
      setForm((f) => ({ ...f, local_model: c.local_model || "", google_credentials_path: c.google_credentials_path || "", complexity_threshold: c.complexity_threshold ?? 0.6, allow_cloud_fallback: c.allow_cloud_fallback ?? true }));
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
    body.allow_cloud_fallback = !!form.allow_cloud_fallback;
    setStatus("Saving…");
    try {
      const r = await postJSON("/api/config", body);
      setStatus(`Saved ${(r.saved || []).length} field(s).`);
      setForm((f) => ({ ...f, groq_api_key: "", tavily_api_key: "", slack_bot_token: "" }));
    } catch {
      setStatus("Save failed.");
    }
  }

  async function runJanitor(dryRun) {
    setCleaning(true);
    try {
      const r = await postJSON(`/api/kg/janitor${dryRun ? "?dry_run=true" : ""}`);
      setJanitor(r);
    } catch {
      setJanitor({ summary: "Cleanup failed." });
    }
    setCleaning(false);
  }

  const hint = (s) => (s ? <span className="set-hint">✓ set</span> : null);

  return (
    <>
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
      <label style={{ display: "flex", alignItems: "flex-start", gap: 10, marginTop: 16, fontSize: 13, lineHeight: 1.5 }}>
        <input type="checkbox" style={{ marginTop: 3 }} checked={!!form.allow_cloud_fallback} onChange={(e) => setForm((f) => ({ ...f, allow_cloud_fallback: e.target.checked }))} />
        <span><strong>Allow cloud fallback for personal work.</strong> When off, personal requests <em>fail closed</em> if the on-device model is unavailable — nothing personal goes to the cloud.</span>
      </label>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 16 }}>
        <button className="btn btn-primary" onClick={save}>Save settings</button>
        <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{status}</span>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: 12.5, margin: "16px 0 0" }}>Keys are stored locally in your config file. Personal-data tasks always run on the local model; only low-sensitivity tasks may use the cloud model.</p>
    </div>

    <div className="card" style={{ marginTop: 16 }}>
      <h2 className="section-title" style={{ marginTop: 0 }}>Maintenance</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 12.5, margin: "0 0 12px" }}>The knowledge-graph janitor archives stale commitments and prunes old conversation turns so conflict detection stays clean. It runs automatically at startup; trigger it manually here.</p>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <button className="btn" onClick={() => runJanitor(true)} disabled={cleaning}>Preview (dry run)</button>
        <button className="btn btn-primary" onClick={() => runJanitor(false)} disabled={cleaning}>{cleaning ? "Running…" : "Run cleanup"}</button>
        {janitor && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{janitor.summary}{janitor.dry_run ? " (dry run)" : ""}</span>}
      </div>
    </div>
    </>
  );
}

/* ---- Evaluation (Stream 4) ----------------------------------------------- */
const pct = (x) => (x * 100).toFixed(1) + "%";

export function Evaluation({ refresh, notify }) {
  const [report, setReport] = useState(undefined); // undefined=loading, null=none
  const [privacy, setPrivacy] = useState(null);
  const [traces, setTraces] = useState([]);
  const [running, setRunning] = useState(false);

  const loadPrivacy = () => getJSON("/api/privacy/report").then(setPrivacy).catch(() => {});
  const loadTraces = () => getJSON("/api/eval/traces?limit=20").then((d) => setTraces(d.traces || [])).catch(() => {});
  useEffect(() => {
    getJSON("/api/eval/report").then((d) => setReport(d.report)).catch(() => setReport(null));
    loadPrivacy();
    loadTraces();
  }, [refresh]);

  async function runEval() {
    setRunning(true);
    try {
      const d = await postJSON("/api/eval/run", {});
      setReport(d.report);
      loadPrivacy();
      loadTraces();
      notify?.("Evaluation complete");
    } catch {
      notify?.("Eval run failed");
    }
    setRunning(false);
  }

  if (report === undefined) return <Empty big="📊" title="Loading evaluation…" sub="" />;

  return (
    <>
      <div className="privacy-banner">{ChartIcon}<div><strong>Week-05 evaluation harness.</strong> Routing accuracy, latency, tokens, and a validated LLM-as-judge (TPR/TNR with 95% CIs) over a versioned golden set. Offline stub by default — no keys needed.</div></div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "0 0 16px", flexWrap: "wrap" }}>
        <button className="btn btn-primary" onClick={runEval} disabled={running}>{running ? "Running…" : "Run evaluation"}</button>
        {report && <span style={{ fontSize: 12, color: "var(--text-muted)" }}>mode {report.mode} · judge {report.judge_backend} · n={report.n_cases} · {new Date(report.generated_at).toLocaleString()}</span>}
      </div>
      {!report
        ? <Empty big="📊" title="No report yet" sub="Click “Run evaluation” to generate one (offline)." />
        : <EvalReport r={report} privacy={privacy} />}
      {traces.length > 0 && <EvalTraces traces={traces} />}
    </>
  );
}

function EvalTraces({ traces }) {
  return (
    <>
      <h2 className="section-title">Recent traces ({traces.length})</h2>
      <div className="stack">
        {traces.map((t) => (
          <div className="card" key={t.trace_id} style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span className="badge badge-local">{t.golden_id || "—"}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.input_preview}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.answer_preview}</div>
            </div>
            <span style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{t.agency_level} · {t.elapsed}s · {t.tokens ?? 0} tok</span>
          </div>
        ))}
      </div>
    </>
  );
}

function EvalReport({ r, privacy }) {
  const m = r.metrics, ra = m.routing_accuracy, j = m.judge;
  const kpis = [
    { n: pct(ra.value), l: `Routing accuracy [${pct(ra.ci_low)}–${pct(ra.ci_high)}]`, alert: ra.label !== "PASS" },
    { n: pct(j.tpr), l: "Judge TPR (recall)", alert: j.tpr < 0.8 },
    { n: pct(j.tnr), l: "Judge TNR", alert: j.tnr < 0.8 },
    { n: m.latency.mean_s + "s", l: "Mean latency" },
  ];
  return (
    <>
      <div className="kpi-row">{kpis.map((k, i) => <div key={i} className={"kpi" + (k.alert ? " alert" : "")}><div className="num">{k.n}</div><div className="lbl">{k.l}</div></div>)}</div>

      <h2 className="section-title">Judge confusion matrix</h2>
      <div className="card" style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, textAlign: "center" }}>
        {[["TP", j.tp], ["TN", j.tn], ["FP", j.fp], ["FN", j.fn]].map(([k, v]) => (
          <div key={k}><div style={{ fontSize: 22, fontWeight: 700 }}>{v}</div><div style={{ fontSize: 12, color: "var(--text-muted)" }}>{k}</div></div>
        ))}
      </div>

      {privacy && (
        <>
          <h2 className="section-title">Privacy posture (Stream 3)</h2>
          <div className="kpi-row">
            <div className="kpi"><div className="num">{privacy.pct_local}%</div><div className="lbl">Routed LOCAL</div></div>
            <div className="kpi"><div className="num">{privacy.leaks_prevented}</div><div className="lbl">Leaks prevented</div></div>
            <div className={"kpi" + (privacy.personal_fallbacks > 0 ? " alert" : "")}><div className="num">{privacy.personal_fallbacks}</div><div className="lbl">Personal cloud fallbacks</div></div>
          </div>
        </>
      )}

      <h2 className="section-title">Silent failures ({r.silent_failures.length})</h2>
      <div className="stack">
        {r.silent_failures.length === 0
          ? <Empty big="✅" title="No silent failures" sub="No fluent-but-wrong answers flagged." />
          : r.silent_failures.map((sf, i) => (
            <div className="card" key={i}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}><span className="badge badge-cloud">{sf.case_id}</span><span style={{ fontSize: 12, color: "var(--text-muted)" }}>confidence {sf.confidence}</span></div>
              <div style={{ marginTop: 6, fontSize: 13 }}>{sf.reason}</div>
              {sf.answer_preview ? <div style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>{sf.answer_preview}</div> : null}
            </div>
          ))}
      </div>
    </>
  );
}

