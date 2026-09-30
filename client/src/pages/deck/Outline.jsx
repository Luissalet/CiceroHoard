import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../api.js";
import { go, useApp } from "../../App.jsx";
import { useDeck, useDirty } from "../../components/deckContext.js";
import { ConfirmButton, Empty, Field, ListEditor } from "../../components/ui.jsx";
import { LAYOUTS } from "../../format.js";

const toDraft = (items) => (items || []).map((it) => ({
  id: it.id, title: it.title || "", purpose: it.purpose || "", points: it.points?.length ? [...it.points] : [], layout_hint: it.layout_hint || "",
}));
const toPayload = (draft) => draft.map((it) => {
  const item = { title: it.title.trim(), purpose: it.purpose.trim(), points: it.points.map((p) => p.trim()).filter(Boolean) };
  if (it.id) item.id = it.id;
  if (it.layout_hint) item.layout_hint = it.layout_hint;
  return item;
});

export default function Outline() {
  const { t } = useApp();
  const { deckId, deck, setDeck, run, busy, noteGenerator } = useDeck();
  const initialKey = JSON.stringify(toDraft(deck.outline));
  const initial = useMemo(() => JSON.parse(initialKey), [initialKey]);
  const [draft, setDraft] = useState(initial);
  const [onlyMissing, setOnlyMissing] = useState(false);
  useEffect(() => setDraft(initial), [initial]);
  const dirty = JSON.stringify(draft) !== initialKey;
  useDirty(dirty);
  const hasSlides = (deck.slides || []).length > 0;
  const emptyInput = !(deck.brief || "").trim() && (deck.sources || []).length === 0;

  const update = (i, patch) => setDraft(draft.map((it, n) => (n === i ? { ...it, ...patch } : it)));
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= draft.length) return;
    const next = draft.slice();
    [next[i], next[j]] = [next[j], next[i]];
    setDraft(next);
  };

  const generate = () => run(t("busy_outline"), async () => {
    const res = await api.outlineGenerate(deckId);
    const next = res.deck || res;
    setDeck(next);
    noteGenerator(res, t("what_outline"), next.model_used);
    return true;
  });
  const save = () => run(t("busy_saving"), async () => {
    const res = await api.outlineSave(deckId, toPayload(draft));
    setDeck(res.deck || res);
    return true;
  });
  const generateSlides = async () => {
    const done = await run(t("busy_slides"), async () => {
      if (dirty) await api.outlineSave(deckId, toPayload(draft));
      const res = await api.slidesGenerate(deckId, hasSlides && onlyMissing);
      const next = res.deck || res;
      setDeck(next);
      noteGenerator(res, t("what_slides"), next.model_used);
      return true;
    });
    if (done) go(`deck/${deckId}/slides`);
  };

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {draft.length > 0 ? (
          <ConfirmButton t={t} className="btn" disabled={!!busy} label={t("outline_regenerate")} confirmLabel={t("outline_regenerate_confirm")} onConfirm={generate} />
        ) : (
          <button type="button" className="btn btn-primary" disabled={!!busy} onClick={generate}>{t("outline_generate")}</button>
        )}
        <button type="button" className="btn" disabled={!!busy || !dirty} onClick={save}>{t("save")}</button>
        {dirty && <span className="help">{t("unsaved")}</span>}
      </div>
      {emptyInput && <p className="help">{t("outline_no_input")}</p>}
      {draft.length === 0 && <Empty>{t("outline_empty")}</Empty>}
      <ol className="space-y-3">
        {draft.map((item, i) => (
          <li key={i} className="panel">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-[14px] font-semibold num">{t("outline_item", { n: i + 1 })}</h2>
              <span className="inline-flex gap-1">
                <button type="button" className="btn btn-icon" disabled={!!busy || i === 0} onClick={() => move(i, -1)} aria-label={`${t("move_up")}: ${t("outline_item", { n: i + 1 })}`}>↑</button>
                <button type="button" className="btn btn-icon" disabled={!!busy || i === draft.length - 1} onClick={() => move(i, 1)} aria-label={`${t("move_down")}: ${t("outline_item", { n: i + 1 })}`}>↓</button>
                <button type="button" className="btn btn-icon" disabled={!!busy} onClick={() => setDraft(draft.filter((_, n) => n !== i))} aria-label={`${t("remove")}: ${t("outline_item", { n: i + 1 })}`}>✕</button>
              </span>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Field label={t("slide_title")}><input className="field" value={item.title} onChange={(e) => update(i, { title: e.target.value })} /></Field>
              <Field label={t("layout")}>
                <select className="field" value={item.layout_hint} onChange={(e) => update(i, { layout_hint: e.target.value })}>
                  <option value="">{t("layout_auto")}</option>
                  {LAYOUTS.map((l) => <option key={l} value={l}>{t(`layout_${l}`)}</option>)}
                </select>
              </Field>
              <div className="md:col-span-2"><Field label={t("outline_purpose")}><textarea className="field" rows={2} value={item.purpose} onChange={(e) => update(i, { purpose: e.target.value })} /></Field></div>
              <div className="md:col-span-2">
                <span className="label">{t("outline_points")}</span>
                <ListEditor t={t} items={item.points} label={t("outline_point")} addLabel={t("add_point")} disabled={!!busy} onChange={(points) => update(i, { points })} />
              </div>
            </div>
          </li>
        ))}
      </ol>
      <div>
        <button type="button" className="btn" disabled={!!busy} onClick={() => setDraft([...draft, { title: "", purpose: "", points: [], layout_hint: "" }])}>+ {t("outline_add")}</button>
      </div>
      {draft.length > 0 && (
        <div className="panel flex flex-wrap items-center gap-3">
          <button type="button" className="btn btn-primary" disabled={!!busy || draft.some((it) => !it.title.trim())} onClick={generateSlides}>{t("slides_generate")}</button>
          {hasSlides && (
            <label className="flex items-center gap-2 text-[13px]">
              <input type="checkbox" checked={onlyMissing} onChange={(e) => setOnlyMissing(e.target.checked)} />
              {t("slides_only_missing")}
            </label>
          )}
          <span className="help">{hasSlides && !onlyMissing ? t("slides_replace_help") : t("slides_generate_help")}</span>
        </div>
      )}
    </div>
  );
}
