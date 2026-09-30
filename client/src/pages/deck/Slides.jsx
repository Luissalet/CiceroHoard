import React, { useState } from "react";
import { api } from "../../api.js";
import { goReplace, useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";
import SlideFrame from "../../components/SlideFrame.jsx";
import { Empty } from "../../components/ui.jsx";
import { LAYOUTS } from "../../format.js";
import SlideEditor from "./SlideEditor.jsx";

export const selectSlide = (deckId, slideId) => goReplace(`deck/${deckId}/slides${slideId ? `?slide=${encodeURIComponent(slideId)}` : ""}`);

export default function Slides() {
  const { t } = useApp();
  const { deckId, deck, setDeck, reload, run, busy, query, confirmDiscard, noteGenerator } = useDeck();
  const [newLayout, setNewLayout] = useState("bullets");
  const slides = (deck.slides || []).slice().sort((a, b) => a.position - b.position);
  const wanted = query.get("slide");
  const index = Math.max(0, slides.findIndex((s) => s.id === wanted));
  const slide = slides[index];
  const off = !!busy;

  const select = (id) => { if (slide && id !== slide.id && confirmDiscard()) selectSlide(deckId, id); };

  const move = async (d) => {
    if (!confirmDiscard()) return;
    const order = slides.map((s) => s.id);
    const j = index + d;
    [order[index], order[j]] = [order[j], order[index]];
    await run(t("busy_saving"), async () => {
      const res = await api.slidesReorder(deckId, order);
      setDeck(res.deck || res);
      return true;
    });
  };
  const add = async () => {
    if (!confirmDiscard()) return;
    const created = await run(t("busy_adding"), async () => {
      const res = await api.slideAdd(deckId, { after_id: slide ? slide.id : null, layout: newLayout });
      await reload();
      return res.slide || res;
    });
    if (created?.id) selectSlide(deckId, created.id);
  };
  const afterDelete = () => {
    const next = slides[index + 1] || slides[index - 1];
    selectSlide(deckId, next ? next.id : null);
  };

  const generateFromOutline = () => run(t("busy_slides"), async () => {
    const res = await api.slidesGenerate(deckId, false);
    const next = res.deck || res;
    setDeck(next);
    noteGenerator(res, t("what_slides"), next.model_used);
    return true;
  });

  if (!slide) {
    const hasOutline = (deck.outline || []).length > 0;
    return (
      <div className="max-w-2xl space-y-3">
        <Empty>{t("slides_empty")}</Empty>
        {hasOutline && (
          <button type="button" className="btn btn-primary" disabled={off} onClick={generateFromOutline}>{t("slides_generate")}</button>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <label className="block">
            <span className="label">{t("layout")}</span>
            <select className="field" value={newLayout} onChange={(e) => setNewLayout(e.target.value)}>
              {LAYOUTS.map((l) => <option key={l} value={l}>{t(`layout_${l}`)}</option>)}
            </select>
          </label>
          <button type="button" className={hasOutline ? "btn" : "btn btn-primary"} disabled={off} onClick={add}>{t("slide_add")}</button>
          <a className="btn" href={`#/deck/${deckId}/outline`}>{t("tab_outline")}</a>
        </div>
      </div>
    );
  }

  const approvedLabel = (s) => (s.status === "approved" ? t("slide_status_approved") : t("slide_status_draft"));
  return (
    <div className="slides-grid">
      <nav aria-label={t("slides_strip")} className="slides-nav">
        <ol className="thumb-strip">
          {slides.map((s, i) => (
            <li key={s.id} className="thumb">
              <SlideFrame inert deckId={deckId} slide={s} theme={deck.theme} />
              <div className="thumb-meta" aria-hidden="true">
                <span className="thumb-title"><span className="num">{i + 1}</span> · {s.title || t("untitled")}</span>
                <span className={s.status === "approved" ? "chip chip-ok" : "chip"}>{approvedLabel(s)}</span>
              </div>
              <button type="button" className="thumb-hit" aria-current={s.id === slide.id ? "true" : undefined} aria-label={t("slide_go", { n: i + 1, title: s.title || t("untitled"), status: approvedLabel(s) })} onClick={() => select(s.id)} />
            </li>
          ))}
        </ol>
      </nav>

      <div className="slides-preview min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] font-semibold num">{t("slide_of", { n: index + 1, total: slides.length })}</span>
          <span className={slide.status === "approved" ? "chip chip-ok" : "chip"}>{approvedLabel(slide)}</span>
          <span className="ml-auto inline-flex gap-1">
            <button type="button" className="btn btn-sm" disabled={off || index === 0} onClick={() => move(-1)}>↑ {t("move_before")}</button>
            <button type="button" className="btn btn-sm" disabled={off || index === slides.length - 1} onClick={() => move(1)}>↓ {t("move_after")}</button>
          </span>
        </div>
        <SlideFrame deckId={deckId} slide={slide} theme={deck.theme} title={t("slide_preview_title", { n: index + 1, title: slide.title || t("untitled") })} />
        <p className="help">{t("preview_saved_note")}</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="block">
            <span className="label">{t("layout")}</span>
            <select className="field" value={newLayout} disabled={off} onChange={(e) => setNewLayout(e.target.value)}>
              {LAYOUTS.map((l) => <option key={l} value={l}>{t(`layout_${l}`)}</option>)}
            </select>
          </label>
          <button type="button" className="btn" disabled={off} onClick={add}>+ {t("slide_add_after")}</button>
        </div>
      </div>

      <div className="slides-editor min-w-0">
        <SlideEditor key={`${slide.id}:${slide.revision}`} slide={slide} onDeleted={afterDelete} />
      </div>
    </div>
  );
}
