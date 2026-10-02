// Thin fetch wrapper: JSON in/out, `{ error }` bodies become exceptions (with `code` when the server sends one).
// Every call maps to a REST route that runs the same code as the MCP tool of the same name.
async function request(method, path, { params, body, form } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const init = { method };
  if (form) {
    init.body = form; // multipart: the browser sets the boundary
  } else if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(url, init);
  } catch {
    const error = new Error("network");
    error.code = "network";
    throw error;
  }
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: text };
  }
  if (!response.ok) {
    const detail = data && (data.error || (typeof data.detail === "string" ? data.detail : null));
    const error = new Error(detail || `Error ${response.status}`);
    error.status = response.status;
    error.code = data && data.code;
    throw error;
  }
  return data;
}

const e = encodeURIComponent;
const deckBase = (id) => `/api/decks/${e(id)}`;
const slideBase = (id, sid) => `${deckBase(id)}/slides/${e(sid)}`;

export const api = {
  health: () => request("GET", "/api/health"),

  decks: () => request("GET", "/api/decks"),
  deckCreate: (body) => request("POST", "/api/decks", { body }),
  deck: (id) => request("GET", deckBase(id)),
  deckUpdate: (id, body) => request("PATCH", deckBase(id), { body }),
  deckDelete: (id) => request("DELETE", deckBase(id), { params: { confirm: "true" } }),

  sourceAddText: (id, body) => request("POST", `${deckBase(id)}/sources`, { body }),
  sourceAddFile: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", `${deckBase(id)}/sources`, { form });
  },
  source: (id, sid) => request("GET", `${deckBase(id)}/sources/${e(sid)}`),
  sourceDelete: (id, sid) => request("DELETE", `${deckBase(id)}/sources/${e(sid)}`),

  outlineGenerate: (id) => request("POST", `${deckBase(id)}/outline/generate`),
  outlineSave: (id, items) => request("PUT", `${deckBase(id)}/outline`, { body: { items } }),

  slidesGenerate: (id, onlyMissing) => request("POST", `${deckBase(id)}/slides/generate`, { body: { only_missing: !!onlyMissing } }),
  slideAdd: (id, body) => request("POST", `${deckBase(id)}/slides`, { body }),
  slideUpdate: (id, sid, body) => request("PATCH", slideBase(id, sid), { body }),
  slideDelete: (id, sid) => request("DELETE", slideBase(id, sid)),
  slidesReorder: (id, order) => request("POST", `${deckBase(id)}/slides/reorder`, { body: { order } }),
  slideRegenerate: (id, sid, feedback) => request("POST", `${slideBase(id, sid)}/regenerate`, { body: { feedback } }),
  slideApprove: (id, sid) => request("POST", `${slideBase(id, sid)}/approve`),
  slideUnapprove: (id, sid) => request("POST", `${slideBase(id, sid)}/unapprove`),
  slideRevisions: (id, sid) => request("GET", `${slideBase(id, sid)}/revisions`),
  slideRevert: (id, sid, revision) => request("POST", `${slideBase(id, sid)}/revert`, { body: { revision } }),
  slideImage: (id, sid, prompt) => request("POST", `${slideBase(id, sid)}/image`, { body: prompt ? { prompt } : {} }),

  assetUpload: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", `${deckBase(id)}/assets`, { form });
  },
  assetUrl: (assetId) => `/api/assets/${e(assetId)}`,

  themes: () => request("GET", "/api/themes"),
  designSystems: () => request("GET", "/api/themes/design-systems"),
  themeFromTokens: (tokens_id, mode) => request("POST", "/api/themes/from-tokens", { body: { tokens_id, mode } }),
  check: (id) => request("GET", `${deckBase(id)}/check`),

  exportCreate: (id, format) => request("POST", `${deckBase(id)}/export`, { body: { format } }),
  exports: (id) => request("GET", `${deckBase(id)}/exports`),
  exportUrl: (exportId) => `/api/exports/${e(exportId)}/file`,

  deckPreviewUrl: (id, theme, stamp) => `${deckBase(id)}/preview.html?th=${e(theme || "")}&v=${e(stamp || "")}`,
  slidePreviewUrl: (id, sid, revision, theme) => `${slideBase(id, sid)}/preview.html?v=${e(revision ?? 0)}&th=${e(theme || "")}`,

  settings: () => request("GET", "/api/settings"),
  settingsUpdate: (body) => request("PATCH", "/api/settings", { body }),
};
