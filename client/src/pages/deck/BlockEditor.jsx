import React from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";
import { Field, ListEditor } from "../../components/ui.jsx";
import { CHART_KINDS, formatBytes } from "../../format.js";

const MAX_IMAGE = 15 * 1024 * 1024;

function ChartEditor({ block, onChange, disabled }) {
  const { t } = useApp();
  const { categories, series } = block;
  const setCat = (i, v) => onChange({ ...block, categories: categories.map((c, n) => (n === i ? v : c)) });
  const setName = (si, v) => onChange({ ...block, series: series.map((s, n) => (n === si ? { ...s, name: v } : s)) });
  const setVal = (si, ci, v) => onChange({ ...block, series: series.map((s, n) => (n === si ? { ...s, values: s.values.map((x, m) => (m === ci ? v : x)) } : s)) });
  const addRow = () => onChange({ ...block, categories: [...categories, ""], series: series.map((s) => ({ ...s, values: [...s.values, ""] })) });
  const removeRow = (ci) => onChange({ ...block, categories: categories.filter((_, n) => n !== ci), series: series.map((s) => ({ ...s, values: s.values.filter((_, n) => n !== ci) })) });
  const addSeries = () => onChange({ ...block, series: [...series, { name: t("chart_series_n", { n: series.length + 1 }), values: categories.map(() => "") }] });
  const removeSeries = (si) => onChange({ ...block, series: series.filter((_, n) => n !== si) });

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <Field label={t("chart_kind")}>
          <select className="field" value={block.chart} disabled={disabled} onChange={(e) => onChange({ ...block, chart: e.target.value })}>
            {CHART_KINDS.map((k) => <option key={k} value={k}>{t(`chart_${k}`)}</option>)}
          </select>
        </Field>
        <Field label={t("chart_title")}><input className="field" value={block.title || ""} disabled={disabled} onChange={(e) => onChange({ ...block, title: e.target.value })} /></Field>
      </div>
      <div className="overflow-x-auto">
        <table className="grid">
          <caption className="sr-only-live">{t("chart_table")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("chart_category")}</th>
              {series.map((s, si) => (
                <th key={si} scope="col" className="!normal-case">
                  <span className="flex items-center gap-1">
                    <input className="field" style={{ minWidth: 90 }} value={s.name} disabled={disabled} aria-label={t("chart_series_name", { n: si + 1 })} onChange={(e) => setName(si, e.target.value)} />
                    <button type="button" className="btn btn-icon" disabled={disabled || series.length <= 1} onClick={() => removeSeries(si)} aria-label={t("chart_series_remove", { n: si + 1 })}>✕</button>
                  </span>
                </th>
              ))}
              <th scope="col"><span className="sr-only-live">{t("actions")}</span></th>
            </tr>
          </thead>
          <tbody>
            {categories.map((c, ci) => (
              <tr key={ci}>
                <td><input className="field" style={{ minWidth: 90 }} value={c} disabled={disabled} aria-label={t("chart_category_n", { n: ci + 1 })} onChange={(e) => setCat(ci, e.target.value)} /></td>
                {series.map((s, si) => (
                  <td key={si}>
                    <input className="field num" style={{ minWidth: 70 }} inputMode="decimal" value={s.values[ci] ?? ""} disabled={disabled} aria-label={t("chart_cell", { s: s.name || si + 1, c: c || ci + 1 })} onChange={(e) => setVal(si, ci, e.target.value)} />
                  </td>
                ))}
                <td><button type="button" className="btn btn-icon" disabled={disabled || categories.length <= 1} onClick={() => removeRow(ci)} aria-label={t("chart_row_remove", { n: ci + 1 })}>✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-sm" disabled={disabled} onClick={addRow}>+ {t("chart_add_row")}</button>
        <button type="button" className="btn btn-sm" disabled={disabled} onClick={addSeries}>+ {t("chart_add_series")}</button>
      </div>
    </div>
  );
}

function ImageBlock({ block, onChange, disabled }) {
  const { t } = useApp();
  const { deckId, run } = useDeck();
  const upload = async (file) => {
    if (!file) return;
    if (file.size > MAX_IMAGE) { await run(t("busy_uploading"), async () => { throw new Error(t("file_too_big", { name: file.name, max: formatBytes(MAX_IMAGE) })); }); return; }
    const res = await run(t("busy_uploading"), () => api.assetUpload(deckId, file));
    if (res?.asset_id) onChange({ ...block, asset_id: res.asset_id });
  };
  return (
    <div className="space-y-2">
      {block.asset_id ? (
        <img src={api.assetUrl(block.asset_id)} alt={block.caption || t("image_alt")} className="max-h-40 rounded-md border" style={{ borderColor: "var(--line)" }} />
      ) : (
        <p className="help">{t("image_none")}</p>
      )}
      <label className={`btn btn-sm ${disabled ? "" : "cursor-pointer"}`} aria-disabled={disabled ? "true" : undefined}>
        {block.asset_id ? t("image_replace") : t("image_upload")}
        <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only-live" disabled={disabled} onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
      </label>
      <span className="help ml-2">{t("image_formats")}</span>
      <Field label={t("image_caption")}><input className="field" value={block.caption || ""} disabled={disabled} onChange={(e) => onChange({ ...block, caption: e.target.value })} /></Field>
    </div>
  );
}

export default function BlockEditor({ block, index, count, onChange, onMove, onRemove, disabled }) {
  const { t } = useApp();
  const name = `${t(`block_${block.type}`)} ${index + 1}`;
  let body;
  switch (block.type) {
    case "bullets":
      body = <ListEditor t={t} items={block.items} label={t("block_item")} addLabel={t("add_item")} disabled={disabled} onChange={(items) => onChange({ ...block, items })} />;
      break;
    case "text":
      body = <textarea className="field" rows={4} value={block.text} disabled={disabled} aria-label={name} onChange={(e) => onChange({ ...block, text: e.target.value })} />;
      break;
    case "quote":
      body = (
        <div className="space-y-2">
          <Field label={t("quote_text")}><textarea className="field" rows={3} value={block.text} disabled={disabled} onChange={(e) => onChange({ ...block, text: e.target.value })} /></Field>
          <Field label={t("quote_attribution")}><input className="field" value={block.attribution || ""} disabled={disabled} onChange={(e) => onChange({ ...block, attribution: e.target.value })} /></Field>
        </div>
      );
      break;
    case "columns":
      body = (
        <div className="grid gap-3">
          {["left", "right"].map((side) => (
            <fieldset key={side} className="min-w-0 space-y-2 border-0 p-0">
              <legend className="label">{t(`col_${side}`)}</legend>
              <input className="field" value={block[`${side}_title`] || ""} disabled={disabled} aria-label={t(`col_${side}_title`)} placeholder={t("col_title")} onChange={(e) => onChange({ ...block, [`${side}_title`]: e.target.value })} />
              <ListEditor t={t} items={block[side]} label={t(`col_${side}`)} addLabel={t("add_item")} disabled={disabled} onChange={(items) => onChange({ ...block, [side]: items })} />
            </fieldset>
          ))}
        </div>
      );
      break;
    case "chart":
      body = <ChartEditor block={block} onChange={onChange} disabled={disabled} />;
      break;
    default:
      body = <ImageBlock block={block} onChange={onChange} disabled={disabled} />;
  }
  return (
    <div className="block-card" role="group" aria-label={name}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[12px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>{name}</span>
        <span className="inline-flex gap-1">
          <button type="button" className="btn btn-icon" disabled={disabled || index === 0} onClick={() => onMove(-1)} aria-label={`${t("move_up")}: ${name}`}>↑</button>
          <button type="button" className="btn btn-icon" disabled={disabled || index === count - 1} onClick={() => onMove(1)} aria-label={`${t("move_down")}: ${name}`}>↓</button>
          <button type="button" className="btn btn-icon" disabled={disabled} onClick={onRemove} aria-label={`${t("remove")}: ${name}`}>✕</button>
        </span>
      </div>
      {body}
    </div>
  );
}
