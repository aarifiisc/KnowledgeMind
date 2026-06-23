import { useEffect, useState } from "react";
import { getJSON, postJSON, getKey, validateKey, setUnauthorizedHandler, clearKey } from "./api";
import Login from "./Login.jsx";
import { Dashboard, Graph, Assistant, Documents, Settings } from "./views.jsx";

const ic = (d) => <svg viewBox="0 0 24 24" className="icon">{d}</svg>;
const ICON = {
  dashboard: ic(<><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>),
  graph: ic(<><circle cx="6" cy="6" r="2.4" /><circle cx="18" cy="7" r="2.4" /><circle cx="12" cy="18" r="2.4" /><path d="M8 7l8 0M7.5 8L11 16M16.5 9L13 16" /></>),
  assistant: ic(<path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 0 1-.9-3.8A8.38 8.38 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5z" />),
  documents: ic(<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></>),
  settings: ic(<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></>),
  shield: ic(<><path d="M12 2l8 4v6c0 5-3.4 8.5-8 10-4.6-1.5-8-5-8-10V6l8-4z" /><path d="M9 12l2 2 4-4" /></>),
  refresh: ic(<><path d="M21 12a9 9 0 1 1-2.6-6.4" /><path d="M21 4v5h-5" /></>),
};

const NAV = [
  ["dashboard", "Dashboard"], ["graph", "Knowledge Graph"], ["assistant", "Assistant"],
  ["documents", "Documents"], ["settings", "Settings"],
];
const TITLES = Object.fromEntries(NAV);
const VIEW = { dashboard: Dashboard, graph: Graph, assistant: Assistant, documents: Documents, settings: Settings };

export default function App() {
  const [authed, setAuthed] = useState(false);
  const [booting, setBooting] = useState(true);
  const [view, setView] = useState("dashboard");
  const [refresh, setRefresh] = useState(0);
  const [mode, setMode] = useState("");
  const [toast, setToast] = useState("");
  const [scanning, setScanning] = useState(false);

  const notify = (m) => {
    setToast(m);
    window.clearTimeout(notify._t);
    notify._t = window.setTimeout(() => setToast(""), 2400);
  };

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthed(false));
    (async () => {
      const k = getKey();
      if (k && (await validateKey(k))) setAuthed(true);
      setBooting(false);
    })();
  }, []);

  useEffect(() => {
    if (!authed) return;
    getJSON("/api/status").then((s) => setMode(s.assistant_mode)).catch(() => {});
  }, [authed, refresh]);

  async function runScan() {
    setScanning(true);
    try {
      const r = await postJSON("/api/scan");
      notify(`Scan complete · ${r.commitments} commitments · ${r.conflicts} conflict(s)`);
      setRefresh((x) => x + 1);
    } catch {
      notify("Scan failed");
    }
    setScanning(false);
  }

  if (booting) return <div className="boot"><span className="brand-mark">🧠</span> Loading…</div>;
  if (!authed) return <Login onAuthed={() => setAuthed(true)} />;

  const ViewComp = VIEW[view];
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">🧠</div><div className="brand-name">Knowledge<span>Mind</span></div></div>
        <nav className="nav">
          {NAV.map(([id, label]) => (
            <button key={id} className={"nav-item" + (view === id ? " active" : "")} onClick={() => setView(id)}>
              {ICON[id]}<span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="privacy-pill">{ICON.shield}<div><strong>On-device</strong><span>Personal data stays private</span></div></div>
          <button className="lock-btn" onClick={() => { clearKey(); setAuthed(false); }}>Lock workspace</button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <h1>{TITLES[view]}</h1>
          <div className="topbar-actions">
            <span className={"chip " + (mode === "live" ? "chip-live" : "chip-demo")}>
              {mode === "live" ? "● Live" : mode ? "Demo mode" : "…"}
            </span>
            <button className="btn btn-primary" onClick={runScan} disabled={scanning}>
              {ICON.refresh}<span>{scanning ? "Scanning…" : "Run scan"}</span>
            </button>
          </div>
        </header>
        <div className="content">
          <ViewComp refresh={refresh} notify={notify} />
        </div>
      </main>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
