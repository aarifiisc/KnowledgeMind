// Project Advisor (projmgmt) API client.
// Same-origin under /projmgmt; the km_access cookie authorizes the requests, and
// we also attach the X-Access-Key header (reusing KM's stored key) to be explicit.
import { getKey } from "../api";

const PREFIX = import.meta.env.VITE_PROJMGMT_PREFIX || "/projmgmt";

async function pm(path, { method = "GET", body } = {}) {
  const headers = {};
  const key = getKey();
  if (key) headers["X-Access-Key"] = key;
  const opts = { method, headers };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body != null) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(PREFIX + path, opts);
  if (!res.ok) throw new Error((await res.text().catch(() => "")) || `HTTP ${res.status}`);
  return res.json();
}

export const pmListProjects = () => pm("/projects");
export const pmCreateProject = (formData) => pm("/projects", { method: "POST", body: formData });
export const pmChatHistory = (pid, tag) =>
  pm(`/projects/${pid}/chat/history${tag ? `?tag=${encodeURIComponent(tag)}` : ""}`);
export const pmSendMessage = (pid, body) => pm(`/projects/${pid}/chat`, { method: "POST", body });
export const pmUpdateTags = (pid, msgId, tags) =>
  pm(`/projects/${pid}/chat/${msgId}/tags`, { method: "PATCH", body: { tags } });
export const pmSuggestTags = (pid, message) =>
  pm(`/projects/${pid}/chat/suggest-tags`, { method: "POST", body: { message } });
export const pmKG = (pid, plane) =>
  pm(`/projects/${pid}/kg${plane && plane !== "both" ? `?plane=${plane}` : ""}`);
export const pmCoverage = (pid) => pm(`/projects/${pid}/kg/coverage`);
export const pmRules = (pid) => pm(`/projects/${pid}/rules`);
