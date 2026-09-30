import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../api.js";
import { go, useApp } from "../../App.jsx";
import { useDeck, useDirty } from "../../components/deckContext.js";
import { ConfirmButton, Field, Section, useAsync } from "../../components/ui.jsx";
import { formatBytes } from "../../format.js";

const MAX_BYTES = 20 * 1024 * 1024;
const ACCEPT = ".txt,.md,.markdown,.pdf,.docx,.pptx";

const fromDeck = (deck) => ({
  title: deck.title || "", brief: deck.brief || "", audience: deck.audience || "", tone: deck.tone || "",
  language: deck.language || "es", slide_count: deck.slide_count || 10,
});

function BriefForm() {
  const { t, notify, refresh } = useApp();
  const { deckId, deck, setDeck, run, busy } = useDeck();
  const initialKey = JSON.stringify(fromDeck(deck));
  const initial = useMemo(() => JSON.parse(initialKey), [initialKey]);
  const [form, setForm] = useState(initial);
  useEffect(() => setForm(initial), [initial]);
  const dirty = JSON.stringify(form) !== initialKey;
  useDirty(dirty);
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const save = async (event) => {
    event.preventDefault();
    await run(t("busy_saving"), async () => {
      const res = await api.deckUpdate(deckId, { ...form, title: form.title.trim(), slide_count: Number(form.slide_count) || 10 });
      setDeck(res.deck || res);
      notify(t("saved"));
      refresh();
    });
  };

  return (
    <form className="grid gap-3 md:grid-cols-2" onSubmit={save}>
      <div className="md:col-span-2"><Field label={t("deck_title")}><input className="field" required maxLength={200} value={form.title} onChange={set("title")} /></Field></div>
      <div className="md:col-span-2"><Field label={t("deck_brief")} help={t("deck_brief_help")}><textarea className="field" rows={5} value={form.brief} onChange={set("brief")} /></Field></div>
      <Field label={t("deck_audience")}><input className="field" value={form.audience} onChange={set("audience")} placeholder={t("deck_audience_ph")} /></Field>
      <Field label={t("deck_tone")}><input className="field" value={form.tone} onChange={set("tone")} placeholder={t("deck_tone_ph")} /></Field>
      <Field label={t("deck_language")}>
        <select className="field" value={form.language} onChange={set("language")}>
          <option value="es">{t("lang_es")}</option>
          <option value="en">{t("lang_en")}</option>
        </select>
      </Field>
      <Field label={t("deck_slide_count")} help={t("deck_slide_count_help")}>
        <input className="field num" type="number" min={3} max={40} required value={form.slide_count} onChange={set("slide_count")} />
      </Field>
      <div className="flex items-center gap-3 md:col-span-2">
        <button className="btn btn-primary" type="submit" disabled={!!busy || !dirty}>{t("save")}</button>
        {dirty && <span className="help">{t("unsaved")}</span>}
      </div>
    </form>
  );
}

function SourceRow({ source }) {
  const { t, lang } = useApp();
  const { deckId, run, busy, reload } = useDeck();
  const [text, setText] = useState(null);
  const [open, setOpen] = useState(false);
  const toggle = async () => {
    if (!open && text === null) {
      const res = await run(t("busy_loading"), () => api.source(deckId, source.id));
      if (!res) return;
      setText(res.text ?? "");
    }
    setOpen(!open);
  };
  const remove = async () => {
    const done = await run(t("busy_saving"), async () => { await api.sourceDelete(deckId, source.id); await reload(); return true; });
    return done;
  };
  return (
    <li className="rounded-md border p-2.5" style={{ borderColor: "var(--line)" }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 font-semibold [overflow-wrap:anywhere]">{source.title}</span>
        <span className="chip">{t(`kind_${source.kind}`)}</span>
        <span className="chip num">{t("chars", { n: (source.chars ?? 0).toLocaleString(lang === "en" ? "en-GB" : "es-ES") })}</span>
        <button type="button" className="btn btn-sm" aria-expanded={open} onClick={toggle} disabled={!!busy}>{open ? t("hide_text") : t("show_text")}</button>
        <ConfirmButton t={t} disabled={!!busy} label={t("remove")} confirmLabel={t("source_remove_confirm")} onConfirm={remove} />
      </div>
      {open && <div className="pre-box mt-2 mono" tabIndex={0} role="region" aria-label={source.title}>{text}</div>}
    </li>
  );
}

function AddSources() {
  const { t, notify } = useApp();
  const { deckId, run, busy, reload } = useDeck();
  const [drag, setDrag] = useState(false);
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteText, setPasteText] = useState("");

  const upload = async (files) => {
    const list = Array.from(files || []);
    if (!list.length) return;
    await run(t("busy_uploading"), async () => {
      let added = 0;
      for (const file of list) {
        if (file.size > MAX_BYTES) throw new Error(t("file_too_big", { name: file.name, max: formatBytes(MAX_BYTES) }));
        await api.sourceAddFile(deckId, file);
        added += 1;
        await reload();
      }
      notify(t("sources_added", { n: added }));
    });
  };
  const addText = async (event) => {
    event.preventDefault();
    const done = await run(t("busy_saving"), async () => {
      await api.sourceAddText(deckId, { title: pasteTitle.trim() || t("pasted_text"), text: pasteText });
      await reload();
      return true;
    });
    if (done) { setPasteTitle(""); setPasteText(""); notify(t("sources_added", { n: 1 })); }
  };

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <label
        className="dropzone relative flex min-h-[140px] cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed p-4 text-center"
        style={{ borderColor: drag ? "var(--accent)" : "var(--line)", background: drag ? "var(--accent-soft)" : "transparent" }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); if (!busy) upload(e.dataTransfer.files); }}
      >
        <span className="font-semibold">{t("drop_files")}</span>
        <span className="help">{t("drop_help")}</span>
        <input type="file" multiple accept={ACCEPT} className="sr-only-live" disabled={!!busy} onChange={(e) => { upload(e.target.files); e.target.value = ""; }} />
      </label>
      <form className="space-y-2" onSubmit={addText}>
        <Field label={t("source_title")}><input className="field" value={pasteTitle} onChange={(e) => setPasteTitle(e.target.value)} /></Field>
        <Field label={t("source_text")}><textarea className="field" rows={4} required value={pasteText} onChange={(e) => setPasteText(e.target.value)} /></Field>
        <button type="submit" className="btn" disabled={!!busy || !pasteText.trim()}>{t("add_text")}</button>
      </form>
    </div>
  );
}

export default function Brief() {
  const { t, notify, refresh } = useApp();
  const { deckId, deck, run, busy, confirmDiscard } = useDeck();
  const remove = async () => {
    const done = await run(t("busy_deleting"), async () => { await api.deckDelete(deckId); return true; });
    if (done) { notify(t("deck_deleted")); refresh(); go("decks"); }
  };
  const sources = deck.sources || [];
  return (
    <div className="max-w-4xl space-y-4">
      <Section title={t("deck_brief_section")}><BriefForm /></Section>
      <Section title={t("sources_section")} right={<span className="help">{t("sources_help")}</span>}>
        <AddSources />
        {sources.length === 0 ? (
          <p className="help mt-3">{t("sources_empty")}</p>
        ) : (
          <ul className="mt-3 space-y-2">{sources.map((s) => <SourceRow key={s.id} source={s} />)}</ul>
        )}
      </Section>
      <Section title={t("danger_zone")}>
        <p className="help mb-2">{t("deck_delete_help")}</p>
        <ConfirmButton t={t} disabled={!!busy} label={t("deck_delete")} confirmLabel={t("deck_delete_confirm")} onConfirm={() => { if (confirmDiscard()) remove(); }} />
      </Section>
    </div>
  );
}
