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
  design:(id,body)=>request('POST',`${deckBase(id)}/design`,{body}),
  benchmark:(id,body)=>request('POST',`${deckBase(id)}/benchmarks`,{body}),
  modelImport:(id,body)=>request('POST',`${deckBase(id)}/models`,{body}),
  modelUpload:(id,file)=>{const form=new FormData();form.append('file',file);return request('POST',`${deckBase(id)}/models/upload`,{form});},
  visualLab: (id,body)=>request('POST',`/api/decks/${id}/visual-lab`,{body}),
  poll: (id,body)=>request('POST',`/api/decks/${id}/polls`,{body}),
  connector: (id,body)=>request('POST',`/api/decks/${id}/connectors`,{body}),
  collaborate: (id,slide,body)=>request('POST',`/api/decks/${id}/slides/${slide}/collaboration`,{body}),
  health: () => request("GET", "/api/health"),
  transitions: id => request('GET',`${deckBase(id)}/transitions`),
  transitionsSet: (id,body) => request('PUT',`${deckBase(id)}/transitions`,{body}),
  transitionsReset: id => request('DELETE',`${deckBase(id)}/transitions`),
  animations: id => request('GET',`${deckBase(id)}/animations`),
  animationsSet: (id,body) => request('PUT',`${deckBase(id)}/animations`,{body}),
  animationCatalogue: () => request('GET','/api/animations/catalogue'),
  media: id => request('GET',`${deckBase(id)}/media`),
  mediaImport: (id,body) => request('POST',`${deckBase(id)}/media`,{body}),
  mediaUpload: (id,file) => {const form=new FormData();form.append('file',file);return request('POST',`${deckBase(id)}/media`,{form})},
  mediaControl: (id,body) => request('POST',`${deckBase(id)}/live/media`,{body}),
  dataLinks: id => request('GET',`${deckBase(id)}/data-links`),
  dataLink: (id,body) => request('POST',`${deckBase(id)}/data-links`,{body}),
  dataLinkControl: (id,body) => request('POST',`${deckBase(id)}/data-links/control`,{body}),
  dataBind: (id,body) => request('POST',`${deckBase(id)}/data-links/bind`,{body}),
  liveStart:(id,body)=>request('POST',`${deckBase(id)}/live`,{body}),
  liveState:(id,session)=>request('GET',`${deckBase(id)}/live/${e(session)}/state`),
  liveSpeaker:(id,session)=>request('GET',`${deckBase(id)}/live/${e(session)}/speaker`),
  liveControl:(id,session,body)=>request('POST',`${deckBase(id)}/live/${e(session)}/control`,{body}),
  datasetImport:(id,body)=>request('POST',`${deckBase(id)}/datasets`,{body}),
  datasetUpload:(id,file,options)=>{const form=new FormData();form.append('file',file);for(const [key,value] of Object.entries(options))if(value!==''&&value!=null)form.append(key,value);return request('POST',`${deckBase(id)}/datasets`,{form})},
  dataset:(id,source)=>request('GET',`${deckBase(id)}/datasets/${e(source)}`),
  datasetTransform:(id,source,body)=>request('POST',`${deckBase(id)}/datasets/${e(source)}/transform`,{body}),
  datasetVisual:(id,source,body)=>request('POST',`${deckBase(id)}/datasets/${e(source)}/visual`,{body}),

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
  slideVariants: (id,sid) => request('GET',`${slideBase(id,sid)}/variants`),
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
  figureSource: assetId => request('GET', `/api/assets/${e(assetId)}/source`),
  figureDownload: assetId => `/api/assets/${e(assetId)}/source?download=true`,

  themes: () => request("GET", "/api/themes"),
  templateUpload: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", `${deckBase(id)}/template`, { form });
  },
  templateClear: (id) => request("POST", `${deckBase(id)}/template`, { body: { clear: true } }),
  designSystems: () => request("GET", "/api/themes/design-systems"),
  themeFromTokens: (tokens_id, mode) => request("POST", "/api/themes/from-tokens", { body: { tokens_id, mode } }),
  check: (id) => request("GET", `${deckBase(id)}/check`),
  visualReview: (id, fix) => request("POST", `${deckBase(id)}/visual-review`, { body: { fix: !!fix } }),

  animationsReset: (id) => request("DELETE", `${deckBase(id)}/animations`),
  animationsPreview: (id) => request("GET", `${deckBase(id)}/animations/preview`),

  exportCreate: (id, format) => request("POST", `${deckBase(id)}/export`, { body: { format } }),
  exports: (id) => request("GET", `${deckBase(id)}/exports`),
  exportUrl: (exportId) => `/api/exports/${e(exportId)}/file`,

  deckPreviewUrl: (id, theme, stamp) => `${deckBase(id)}/preview.html?th=${e(theme || "")}&v=${e(stamp || "")}`,
  slidePreviewUrl: (id, sid, revision, theme) => `${slideBase(id, sid)}/preview.html?v=${e(revision ?? 0)}&th=${e(theme || "")}`,

  settings: () => request("GET", "/api/settings"),
  settingsUpdate: (body) => request("PATCH", "/api/settings", { body }),
};
