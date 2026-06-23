import { useState } from "react";
import { setKey, validateKey } from "./api";

export default function Login({ onAuthed }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    const key = value.trim();
    if (!key) return;
    setBusy(true);
    setError("");
    const ok = await validateKey(key);
    setBusy(false);
    if (ok) {
      setKey(key);
      onAuthed();
    } else {
      setError("Invalid access key.");
    }
  }

  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand"><span className="brand-mark">🧠</span> Knowledge<span style={{ color: "var(--accent)" }}>Mind</span></div>
        <p className="login-sub">This workspace is private. Enter your access key to continue.</p>
        <input className="input" type="password" placeholder="Access key" value={value}
               onChange={(e) => setValue(e.target.value)} autoFocus />
        {error && <div className="login-error">{error}</div>}
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Checking…" : "Unlock"}</button>
        <div className="login-foot">🔒 Personal data stays on-device</div>
      </form>
    </div>
  );
}
