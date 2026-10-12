// Small helpers shared by the pages: labels, dates, sizes.
export const LAYOUTS = ["title", "section", "bullets", "two_column", "image_text", "quote", "chart", "closing", "evidence", "comparison", "diagram", "metrics", "table", "image_full", "freeform"];
export const BLOCK_TYPES = ["bullets", "text", "quote", "columns", "chart", "image", "diagram", "metrics", "table", "timeline", "video", "audio","scene3d","poll"];
export const CHART_KINDS = ["bar", "bar_horizontal", "line", "area", "pie", "donut", "scatter", "bubble", "dot", "dumbbell", "band", "heatmap", "waterfall", "funnel"];
export const DECK_STATUSES = ["draft", "outline", "review", "ready"];
export const EXPORT_FORMATS = ["pptx", "pdf", "html", "md"];

export const STATUS_CHIP = { draft: "chip", outline: "chip chip-accent", review: "chip chip-amber", ready: "chip chip-ok" };

// Timestamps arrive as ISO strings or as epoch seconds/milliseconds; accept all three.
export function toDate(ts) {
  if (ts === null || ts === undefined || ts === "") return null;
  const date = typeof ts === "number" ? new Date(ts < 1e12 ? ts * 1000 : ts) : new Date(ts);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function clock(ts, lang) {
  const date = toDate(ts);
  if (!date) return "—";
  const locale = lang === "en" ? "en-GB" : "es-ES";
  const sameDay = date.toDateString() === new Date().toDateString();
  const time = date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  return sameDay ? time : `${date.toLocaleDateString(locale, { day: "2-digit", month: "short", year: "2-digit" })} ${time}`;
}

export function formatBytes(n, lang) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  const locale = lang === "en" ? "en-GB" : "es-ES";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toLocaleString(locale, { maximumFractionDigits: 1 })} KB`;
  return `${(n / 1024 / 1024).toLocaleString(locale, { maximumFractionDigits: 1 })} MB`;
}

export const approvedCount = (deck) => (deck.slides || []).filter((s) => s.status === "approved").length;
