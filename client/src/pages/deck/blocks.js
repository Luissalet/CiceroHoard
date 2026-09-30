// Block drafts: the editor works on strings for chart cells so partial input ("1,", "-") survives typing,
// and converts to the API shape on save.
export function blockToDraft(block) {
  const b = { ...block };
  if (b.type === "bullets") b.items = [...(b.items || [])];
  if (b.type === "columns") { b.left = [...(b.left || [])]; b.right = [...(b.right || [])]; }
  if (b.type === "chart") {
    b.categories = [...(b.categories || [])];
    b.series = (b.series || []).map((s) => ({ name: s.name || "", values: b.categories.map((_, i) => (s.values?.[i] === undefined || s.values?.[i] === null ? "" : String(s.values[i]))) }));
  }
  return b;
}

export function newBlock(type, t) {
  switch (type) {
    case "bullets": return { type, items: [""] };
    case "text": return { type, text: "" };
    case "quote": return { type, text: "", attribution: "" };
    case "columns": return { type, left_title: "", left: [""], right_title: "", right: [""] };
    case "chart": return { type, chart: "bar", title: "", categories: ["", ""], series: [{ name: t("chart_series_n", { n: 1 }), values: ["", ""] }] };
    default: return { type: "image", asset_id: "", caption: "" };
  }
}

const compact = (list) => list.map((x) => x.trim()).filter(Boolean);
const withText = (obj, key, value) => { const v = (value || "").trim(); if (v) obj[key] = v; };

// Throws Error(message) with a user-facing message when a block is not valid.
export function blockToApi(block, t, n) {
  switch (block.type) {
    case "bullets": return { type: "bullets", items: compact(block.items) };
    case "text": return { type: "text", text: block.text };
    case "quote": { const out = { type: "quote", text: block.text }; withText(out, "attribution", block.attribution); return out; }
    case "columns": {
      const out = { type: "columns", left: compact(block.left), right: compact(block.right) };
      withText(out, "left_title", block.left_title);
      withText(out, "right_title", block.right_title);
      return out;
    }
    case "image": {
      if (!block.asset_id) throw new Error(t("image_missing", { n }));
      const out = { type: "image", asset_id: block.asset_id };
      withText(out, "caption", block.caption);
      return out;
    }
    case "chart": {
      const categories = block.categories.map((c) => c.trim());
      if (!categories.length || categories.some((c) => !c)) throw new Error(t("chart_invalid_cats", { n }));
      const series = block.series.map((s) => ({
        name: s.name.trim(),
        values: s.values.map((v) => {
          const text = String(v).trim().replace(",", ".");
          const num = text === "" ? NaN : Number(text);
          if (!Number.isFinite(num)) throw new Error(t("chart_invalid_values", { n }));
          return num;
        }),
      }));
      if (!series.length || series.some((s) => !s.name)) throw new Error(t("chart_invalid_series", { n }));
      const out = { type: "chart", chart: block.chart, categories, series };
      withText(out, "title", block.title);
      return out;
    }
    default: return block;
  }
}
