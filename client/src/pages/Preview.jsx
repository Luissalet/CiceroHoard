import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import SlideFrame from "../components/SlideFrame.jsx";
import { Empty } from "../components/ui.jsx";

// Full-deck preview. "Slides" shows one slide at a time (arrow keys); "Document" shows the deck's preview.html in a big frame.
export default function Preview({ deckId, query }) {
  const { t } = useApp();
  const [deck, setDeck] = useState(null);
  const [error, setError] = useState(null);
  const [mode, setMode] = useState("slides");
  const [n, setN] = useState(0);
  const [showNotes, setShowNotes] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const stageRef = useRef(null);
  const docRef = useRef(null);

  useEffect(() => {
    let alive = true;
    api.deck(deckId).then((d) => alive && setDeck(d.deck || d)).catch((e) => alive && setError(e));
    return () => { alive = false; };
  }, [deckId]);

  const slides = (deck?.slides || []).slice().sort((a, b) => a.position - b.position);
  const total = slides.length;
  useEffect(() => {
    const start = Number(query.get("n"));
    if (start >= 1) setN(Math.min(start, Math.max(total, 1)) - 1);
  }, [query, total]);
  const clamp = useCallback((i) => Math.max(0, Math.min(total - 1, i)), [total]);

  // In document mode the same keys scroll the frame by one slide (pitch measured from the document itself).
  const scrollDoc = useCallback((direction) => {
    const win = docRef.current?.contentWindow;
    const doc = docRef.current?.contentDocument;
    if (!win || !doc) return;
    const els = doc.querySelectorAll(".slide, [data-slide], body > section, main > section");
    let pitch = win.innerHeight * 0.9;
    if (els.length > 1) pitch = els[1].getBoundingClientRect().top - els[0].getBoundingClientRect().top || pitch;
    win.scrollBy({ top: direction * pitch, behavior: "smooth" });
  }, []);

  const step = useCallback((direction) => {
    if (mode === "slides") setN((i) => clamp(i + direction));
    else scrollDoc(direction);
  }, [mode, clamp, scrollDoc]);

  const onKey = useCallback((event) => {
    const tag = event.target?.tagName;
    if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || event.altKey || event.ctrlKey || event.metaKey) return;
    const onControl = tag === "BUTTON" || tag === "A";
    if (["ArrowRight", "ArrowDown", "PageDown"].includes(event.key) || (event.key === " " && !onControl)) { event.preventDefault(); step(1); }
    else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(event.key)) { event.preventDefault(); step(-1); }
    else if (event.key === "Home" && mode === "slides") { event.preventDefault(); setN(0); }
    else if (event.key === "End" && mode === "slides") { event.preventDefault(); setN(clamp(total - 1)); }
    else if (event.key === "f" || event.key === "F") { event.preventDefault(); toggleFullscreen(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, mode, total, clamp]);

  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

  // The document frame is same-origin: forward its key presses so the arrows keep working after a click inside it.
  const attachDocKeys = () => {
    try { docRef.current?.contentWindow?.addEventListener("keydown", onKey); } catch { /* cross-origin: ignore */ }
  };

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === stageRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  function toggleFullscreen() {
    try {
      if (document.fullscreenElement) document.exitFullscreen();
      else stageRef.current?.requestFullscreen?.();
    } catch { /* not available */ }
  }

  if (error) return <Empty>{error.code === "network" ? t("network_error") : error.message} <a href="#/decks">{t("back_to_decks")}</a></Empty>;
  if (!deck) return <div className="help" role="status">{t("loading")}</div>;
  if (total === 0) return <Empty>{t("slides_empty")} <a href={`#/deck/${deckId}/outline`}>{t("tab_outline")}</a></Empty>;

  const slide = slides[Math.min(n, total - 1)];
  const idx = slides.indexOf(slide);
  return (
    <div className="space-y-3">
      {deck.template && <p className="help">{t("template_preview_help")}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <a href={`#/deck/${deckId}/slides?slide=${encodeURIComponent(slide.id)}`} className="btn btn-sm">← {t("preview_back")}</a>
        <h1 className="min-w-0 flex-1 truncate text-[16px] font-semibold">{deck.title}</h1>
        <span className="inline-flex gap-1" role="group" aria-label={t("preview_mode")}>
          <button type="button" className={mode === "slides" ? "btn btn-sm btn-active" : "btn btn-sm"} aria-pressed={mode === "slides"} onClick={() => setMode("slides")}>{t("preview_mode_slides")}</button>
          <button type="button" className={mode === "doc" ? "btn btn-sm btn-active" : "btn btn-sm"} aria-pressed={mode === "doc"} onClick={() => setMode("doc")}>{t("preview_mode_doc")}</button>
        </span>
        {mode === "slides" && <button type="button" className="btn btn-sm" onClick={toggleFullscreen}>{fullscreen ? t("preview_exit_fullscreen") : t("preview_fullscreen")}</button>}
      </div>

      {mode === "slides" ? (
        <>
          <div ref={stageRef} className="stage">
            <div className="stage-frame">
              <SlideFrame inert deckId={deckId} slide={slide} theme={deck.theme} />
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <button type="button" className="btn" onClick={() => setN(clamp(idx - 1))} disabled={idx === 0}>← {t("preview_prev")}</button>
            <span className="num text-[13px]" role="status" aria-live="polite">{t("slide_of", { n: idx + 1, total })}</span>
            <button type="button" className="btn" onClick={() => setN(clamp(idx + 1))} disabled={idx === total - 1}>{t("preview_next")} →</button>
            <button type="button" className="btn btn-sm" aria-expanded={showNotes} onClick={() => setShowNotes(!showNotes)}>{t("notes")}</button>
          </div>
          {showNotes && <div className="panel mx-auto max-w-3xl whitespace-pre-wrap text-[13px]">{slide.notes || <span className="help">{t("notes_empty")}</span>}</div>}
          <p className="help text-center">{t("preview_keys")}</p>
        </>
      ) : (
        <>
          <iframe ref={docRef} className="doc-frame" title={t("preview_mode_doc")} src={api.deckPreviewUrl(deckId, deck.theme, deck.updated_at)} onLoad={attachDocKeys} />
          <p className="help text-center">{t("preview_keys_doc")}</p>
        </>
      )}
    </div>
  );
}
