import React, { useState } from "react";
import { api } from "../api.js";
import { go, useApp } from "../App.jsx";
import { Empty, Field, useAsync } from "../components/ui.jsx";
import { STATUS_CHIP, clock } from "../format.js";

const EMPTY_FORM = { title: "", brief: "", audience: "", tone: "", language: "", slide_count: 10, theme: "" };

export default function Decks() {
  const { t, notify, lang, refresh } = useApp();
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const list = useAsync(() => api.decks(), []);
  const themes = useAsync(() => api.themes(), []);
  const settings = useAsync(() => api.settings().catch(() => null), []);

  const defaultLanguage = settings.data?.default_language || lang;
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const create = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const body = { title: form.title.trim(), language: form.language || defaultLanguage, slide_count: Number(form.slide_count) || 10 };
      for (const key of ["brief", "audience", "tone", "theme"]) if (form[key].trim()) body[key] = form[key].trim();
      const deck = await api.deckCreate(body);
      notify(t("deck_created"));
      refresh();
      go(`deck/${deck.id}/brief`);
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  };

  const items = list.data?.items || [];
  const themeItems = themes.data?.items || [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[22px] font-semibold">{t("decks_title")}</h1>
        <button type="button" className="btn btn-primary" aria-expanded={creating} onClick={() => setCreating((v) => !v)}>{t("deck_new")}</button>
      </div>
      <p className="help max-w-3xl">{t("decks_intro")}</p>
      {creating && (
        <form className="panel grid gap-3 md:grid-cols-2" onSubmit={create}>
          <div className="md:col-span-2"><Field label={t("deck_title")}><input className="field" required maxLength={200} value={form.title} onChange={set("title")} autoFocus /></Field></div>
          <div className="md:col-span-2"><Field label={t("deck_brief")} help={t("deck_brief_help")}><textarea className="field" rows={3} value={form.brief} onChange={set("brief")} /></Field></div>
          <Field label={t("deck_audience")}><input className="field" value={form.audience} onChange={set("audience")} placeholder={t("deck_audience_ph")} /></Field>
          <Field label={t("deck_tone")}><input className="field" value={form.tone} onChange={set("tone")} placeholder={t("deck_tone_ph")} /></Field>
          <Field label={t("deck_language")}>
            <select className="field" value={form.language || defaultLanguage} onChange={set("language")}>
              <option value="es">{t("lang_es")}</option>
              <option value="en">{t("lang_en")}</option>
            </select>
          </Field>
          <Field label={t("deck_slide_count")} help={t("deck_slide_count_help")}>
            <input className="field num" type="number" min={3} max={40} required value={form.slide_count} onChange={set("slide_count")} />
          </Field>
          <div className="md:col-span-2">
            <Field label={t("deck_theme")}>
              <select className="field" value={form.theme} onChange={set("theme")}>
                <option value="">{t("theme_default")}</option>
                {themeItems.map((th) => <option key={th.id} value={th.id}>{th.name}</option>)}
              </select>
            </Field>
          </div>
          <div className="flex gap-2 md:col-span-2">
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? t("creating") : t("create")}</button>
            <button className="btn" type="button" onClick={() => setCreating(false)}>{t("cancel")}</button>
          </div>
        </form>
      )}
      {list.error && <Empty>{list.error.code === "network" ? t("network_error") : list.error.message}</Empty>}
      {!list.loading && !list.error && items.length === 0 && <Empty>{t("decks_empty")}</Empty>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {items.map((d) => (
          <a key={d.id} className="card" href={`#/deck/${d.id}/${d.slides > 0 ? "slides" : "brief"}`}>
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-[15px] font-semibold">{d.title}</h2>
              <span className={STATUS_CHIP[d.status] || "chip"}>{t(`status_${d.status}`)}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5 text-[12px]">
              <span className="chip num">{t("slides_approved", { a: d.approved ?? 0, n: d.slides ?? 0 })}</span>
              <span className="chip">{d.language === "en" ? t("lang_en") : t("lang_es")}</span>
              {d.theme && <span className="chip">{d.theme}</span>}
            </div>
            <div className="help mt-2 text-right">{t("updated")}: {clock(d.updated_at, lang)}</div>
          </a>
        ))}
      </div>
    </div>
  );
}
