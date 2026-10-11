// Block drafts: the editor works on strings for chart cells so partial input ("1,", "-") survives typing,
// and converts to the API shape on save.
export function blockToDraft(block) {
  const b = { ...block };
  if (b.type === "bullets") b.items = [...(b.items || [])];
  if (b.type === "columns") { b.left = [...(b.left || [])]; b.right = [...(b.right || [])]; }
  if (b.type === "chart") {
    b.categories = [...(b.categories || [])];
    b.series = (b.series || []).map((s) => ({ ...s, name: s.name || "", values: b.categories.map((_, i) => (s.values?.[i] === undefined || s.values?.[i] === null ? "" : String(s.values[i]))) }));
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
    case "diagram": return { type, direction: "right", nodes: [{ id: "a", label: "", detail: "" }, { id: "b", label: "", detail: "" }], edges: [{ source: "a", target: "b" }] };
    case "metrics": return { type, items: [{ value: "", label: "", detail: "" }] };
    case "table": return { type, headers: ["", ""], rows: [["", ""]] };
    case 'timeline':return {type,effect:'stages',items:[{label:'',date:'',detail:''},{label:'',date:'',detail:''}]};
    case 'video':case 'audio':return {type,asset_id:'',caption:'',start:0,volume:1,playback_rate:1,controls:true,autoplay:false,loop:false,muted:false};
    default: return { type: "image", asset_id: "", caption: "" };
  }
}

const compact = (list) => list.map((x) => x.trim()).filter(Boolean);
const withText = (obj, key, value) => { const v = (value || "").trim(); if (v) obj[key] = v; };

// Throws Error(message) with a user-facing message when a block is not valid.
function convertBlock(block, t, n) {
  switch (block.type) {
    case 'video':case 'audio': {
      if(!block.asset_id)throw new Error(t('media_missing',{n}));
      const out={...block};
      for(const key of ['start','volume','playback_rate'])out[key]=Number(block[key]);
      out.end=block.end===''||block.end==null?null:Number(block.end);
      return out;
    }
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
        ...s,
        name: s.name.trim(),
        values: s.values.map((v) => {
          const text = String(v).trim().replace(",", ".");
          if(text === "")return null;
          const num = Number(text);
          if (!Number.isFinite(num)) throw new Error(t("chart_invalid_values", { n }));
          return num;
        }),
      }));
      for(const s of series)for(const key of ['x_values','lower','upper','sizes'])if(s[key])s[key]=s[key].map(v=>{
        const text=String(v??'').trim().replace(',','.');if(!text)return null;
        const value=Number(text);if(!Number.isFinite(value))throw new Error(t('chart_invalid_values',{n}));return value;
      });
      if (!series.length || series.some((s) => !s.name)) throw new Error(t("chart_invalid_series", { n }));
      const out = { ...block, type: "chart", chart: block.chart, categories, series };
      if(out.references)out.references=out.references.map(r=>({...r,value:Number(String(r.value).replace(',','.'))}));
      withText(out, "title", block.title);
      return out;
    }
    default: return block;
  }
}

export function blockToApi(block,t,n){
  const out=convertBlock(block,t,n);
  if(block.build!==undefined&&block.build!==null)out.build=Number(block.build);
  if(block.effect)out.effect=block.effect;
  if(block.duration_ms)out.duration_ms=Number(block.duration_ms);
  for(const key of ['id','frame','font_size','fit','position'])if(block[key]!=null&&block[key]!=='')out[key]=block[key];
  return out;
}
