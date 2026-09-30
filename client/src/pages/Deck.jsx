import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { go, useApp } from "../App.jsx";
import { DeckContext } from "../components/deckContext.js";
import { Busy, Empty, Tabs, panelId, tabId } from "../components/ui.jsx";
import { STATUS_CHIP } from "../format.js";
import Brief from "./deck/Brief.jsx";
import Outline from "./deck/Outline.jsx";
import Slides from "./deck/Slides.jsx";
import Review from "./deck/Review.jsx";
import Theme from "./deck/Theme.jsx";
import Export from "./deck/Export.jsx";

const TAB_COMPONENTS = { brief: Brief, outline: Outline, slides: Slides, review: Review, theme: Theme, export: Export };
const TAB_KEYS = Object.keys(TAB_COMPONENTS);

export default function Deck({ deckId, tab, query }) {
  const { t, notify, refresh } = useApp();
  const [deck, setDeck] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [generator, setGenerator] = useState(null);
  const busyRef = useRef(null);
  const dirtyRef = useRef(false);

  const reload = useCallback(async () => {
    try {
      const data = await api.deck(deckId);
      setDeck(data.deck || data);
      setLoadError(null);
    } catch (e) {
      setLoadError(e);
    }
  }, [deckId]);
  useEffect(() => { reload(); }, [reload]);

  // One long operation at a time: buttons read `busy` and disable themselves.
  const run = useCallback(async (label, fn) => {
    if (busyRef.current) return undefined;
    busyRef.current = label;
    setBusy(label);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError({ message: e.code === "network" ? t("network_error") : e.message, code: e.code });
      return undefined;
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
  }, [t]);

  // Generation answers carry `generator` ("fallback" when no model was reachable) and the deck's `model_used`.
  const noteGenerator = useCallback((res, what, modelUsed) => {
    const fallback = res?.generator === "fallback" || (res?.generator === undefined && !modelUsed);
    const model = res?.model_used || modelUsed || (res?.generator && res.generator !== "fallback" && res.generator !== "model" ? res.generator : null);
    setGenerator({ fallback, model, what });
    notify(fallback ? t("gen_done_fallback", { what }) : t("gen_done_model", { what, model: model || "" }));
  }, [notify, t]);

  useEffect(() => {
    const onBefore = (event) => {
      if (dirtyRef.current) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", onBefore);
    return () => window.removeEventListener("beforeunload", onBefore);
  }, []);

  const active = TAB_KEYS.includes(tab) ? tab : "brief";
  useEffect(() => { window.scrollTo(0, 0); }, [active]);

  const confirmDiscard = useCallback(() => !dirtyRef.current || window.confirm(t("discard_confirm")), [t]);
  const changeTab = (key) => { if (confirmDiscard()) go(`deck/${deckId}/${key}`); };

  const value = useMemo(() => ({
    deckId, deck, setDeck, reload, run, busy, error, setError, dirtyRef, query, noteGenerator, confirmDiscard,
  }), [deckId, deck, reload, run, busy, error, query, noteGenerator, confirmDiscard]);

  const Body = TAB_COMPONENTS[active];

  if (loadError) return <Empty>{loadError.code === "network" ? t("network_error") : loadError.message} <a href="#/decks">{t("back_to_decks")}</a></Empty>;
  if (!deck) return <div className="help" role="status">{t("loading")}</div>;

  const slides = deck.slides || [];
  const tabs = [
    { key: "brief", label: t("tab_brief"), badge: (deck.sources || []).length || null },
    { key: "outline", label: t("tab_outline"), badge: (deck.outline || []).length || null },
    { key: "slides", label: t("tab_slides"), badge: slides.length || null },
    { key: "review", label: t("tab_review") },
    { key: "theme", label: t("tab_theme") },
    { key: "export", label: t("tab_export") },
  ];
  const noModel = !deck.model_used && (deck.outline || []).length > 0;

  return (
    <DeckContext.Provider value={value}>
      <div className="space-y-4">
        <div>
          <a href="#/decks" className="help">← {t("nav_decks")}</a>
          <div className="mt-1 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-[22px] font-semibold [overflow-wrap:anywhere]">{deck.title}</h1>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className={STATUS_CHIP[deck.status] || "chip"}>{t(`status_${deck.status}`)}</span>
                <span className="chip">{deck.language === "en" ? t("lang_en") : t("lang_es")}</span>
                <span className="chip num">{t("slides_count", { n: slides.length })}</span>
                {deck.model_used && <span className="chip chip-accent" title={t("model_used_help")}>{t("model_chip", { model: deck.model_used })}</span>}
                {noModel && <span className="chip chip-amber" title={t("fallback_help")}>{t("fallback_chip")}</span>}
              </div>
              {generator && <p className="help mt-1" role="status">{generator.fallback ? t("gen_done_fallback", { what: generator.what }) : t("gen_done_model", { what: generator.what, model: generator.model || "" })}</p>}
            </div>
            <a
              className="btn"
              href={slides.length ? `#/preview/${deckId}` : undefined}
              aria-disabled={slides.length ? undefined : "true"}
              onClick={(e) => { if (!slides.length || !confirmDiscard()) e.preventDefault(); }}
            >
              {t("preview_deck")}
            </a>
          </div>
        </div>
        <Tabs tabs={tabs} active={active} onChange={changeTab} label={t("deck_sections")} />
        <Busy label={busy} />
        {error && (
          <div className="flex items-start justify-between gap-3 rounded-md border p-3 text-[13px]" style={{ background: "var(--danger-bg)", borderColor: "#e5534b66" }} role="alert">
            <span>{error.message}</span>
            <button type="button" className="btn-link shrink-0" onClick={() => setError(null)}>{t("dismiss")}</button>
          </div>
        )}
        <div role="tabpanel" id={panelId(active)} aria-labelledby={tabId(active)} tabIndex={-1} className="pt-1 outline-none">
          <Body />
        </div>
      </div>
    </DeckContext.Provider>
  );
}
