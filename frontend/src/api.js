// API client with shared access-key auth.
// The key is entered at the Login screen, stored in localStorage, and sent as
// the X-Access-Key header on every request. A 401 clears it and bounces to login.

const KEY_STORAGE = "km_access_key";
const BASE = import.meta.env.VITE_API_BASE || ""; // "" = same-origin (HF single deploy)

export const getKey = () => localStorage.getItem(KEY_STORAGE) || "";
export const setKey = (k) => localStorage.setItem(KEY_STORAGE, k);
export const clearKey = () => localStorage.removeItem(KEY_STORAGE);

let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

async function req(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const key = getKey();
  if (key) headers["X-Access-Key"] = key;
  const res = await fetch(BASE + path, { ...opts, headers });
  if (res.status === 401) {
    clearKey();
    onUnauthorized();
    throw new Error("unauthorized");
  }
  return res;
}

export async function getJSON(path) {
  const res = await req(path);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export async function postJSON(path, body) {
  const res = await req(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export async function postForm(path, formData) {
  const res = await req(path, { method: "POST", body: formData });
  return res.json();
}

// Validate a candidate key against a protected endpoint (used by Login).
export async function validateKey(key) {
  try {
    const res = await fetch(BASE + "/api/status", { headers: key ? { "X-Access-Key": key } : {} });
    return res.ok;
  } catch {
    return false;
  }
}
