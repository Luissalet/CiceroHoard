import React from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";
import SlideFrame from "../../components/SlideFrame.jsx";
import { Empty, Section, useAsync } from "../../components/ui.jsx";

// Client-side miniature of a title slide in the theme's colours and fonts (the real slide is the iframe below).
function Mini({ theme, title, subtitle }) {
  const c = theme.colors || {};
  const f = theme.fonts || {};
  return (
    <div className="theme-mini" aria-hidden="true" style={{ background: c.background, color: c.text, fontFamily: f.body }}>
      <div style={{ width: "16%", height: "3cqw", background: c.accent, borderRadius: 2 }} />
      <div style={{ fontFamily: f.heading, fontWeight: 700, fontSize: "7.5cqw", lineHeight: 1.15, overflow: "hidden", maxHeight: "3.4em" }}>{title}</div>
      <div style={{ color: c.muted, fontSize: "4.2cqw", lineHeight: 1.3, overflow: "hidden", maxHeight: "2.7em" }}>{subtitle}</div>
      <div style={{ display: "flex", gap: "1.5cqw" }}>
        {[c.surface, c.accent, c.accent2].map((color, i) => <span key={i} style={{ width: "4cqw", height: "4cqw", borderRadius: "50%", background: color, border: "1px solid #ffffff44" }} />)}
      </div>
    </div>
  );
}

// A design system's roles in one mode, shaped like a theme so the same miniature can draw it.
function roleTheme(roles, mode) {
  const p = roles?.[mode];
  if (!p) return null;
  return {
    colors: { background: p.background, surface: p.surface2 || p.surface, text: p.text, muted: p.muted, accent: p.accent, accent2: p.accent2 },
    fonts: { heading: roles.fonts?.heading, body: roles.fonts?.body },
  };
}

// "Theme from a design system": the design systems of the family design-system app, each in its light and dark mode.
function FromDesignSystems({ deckId, setDeck, run, busy, onCreated }) {
  const { t, notify } = useApp();
  const systems = useAsync(() => api.designSystems(), []);
  const [last, setLast] = React.useState(null);
  const items = systems.data?.items || [];

  const make = (system, mode) => run(t("busy_saving"), async () => {
    const made = await api.themeFromTokens(system.id, mode);
    const res = await api.deckUpdate(deckId, { theme: made.theme.id });
    setDeck(res.deck || res);
    setLast({ name: made.theme.name, warnings: made.warnings || [], created: made.created });
    onCreated();
    notify(t(made.created ? "theme_ds_created" : "theme_ds_reused", { name: made.theme.name }));
    return true;
  });

  return (
    <Section title={t("theme_ds_title")} right={<button type="button" className="btn" onClick={systems.reload} disabled={systems.loading}>{t("theme_ds_reload")}</button>}>
      <p className="help mb-3">{t("theme_ds_help")}</p>
      {systems.loading && !items.length && <p className="help" role="status">{t("theme_ds_loading")}</p>}
      {systems.error && <p className="help" role="alert">{t("theme_ds_unavailable", { reason: systems.error.message })}</p>}
      {!systems.loading && !systems.error && !items.length && <p className="help">{t("theme_ds_none")}</p>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((system) => (
          <div key={system.id} className="theme-card" data-design-system={system.id}>
            <div className="grid grid-cols-2 gap-2">
              {["light", "dark"].map((mode) => {
                const th = roleTheme(system.roles, mode);
                return th ? <Mini key={mode} theme={th} title={system.name} subtitle={t(mode === "light" ? "theme_ds_light" : "theme_ds_dark")} /> : <span key={mode} />;
              })}
            </div>
            <div className="mt-2 font-semibold">{system.name}</div>
            <div className="mt-1 flex flex-wrap gap-2">
              {["light", "dark"].filter((mode) => system.roles?.[mode]).map((mode) => (
                <button key={mode} type="button" className="btn" disabled={!!busy} onClick={() => make(system, mode)}>
                  {t(mode === "light" ? "theme_ds_use_light" : "theme_ds_use_dark")}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {last && (
        <div className="mt-3" role="status">
          <div className="help">{t(last.created ? "theme_ds_created" : "theme_ds_reused", { name: last.name })}</div>
          {last.warnings.length > 0 && (
            <ul className="help mt-1 list-disc pl-5">{last.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          )}
        </div>
      )}
    </Section>
  );
}

export default function Theme() {
  const { t } = useApp();
  const { deckId, deck, setDeck, run, busy } = useDeck();
  const themes = useAsync(() => api.themes(), []);
  const items = themes.data?.items || [];
  const slides = (deck.slides || []).slice().sort((a, b) => a.position - b.position);
  const first = slides[0];
  const uploadTemplate = (file) => file && run(t("busy_uploading"), async () => {
    const res = await api.templateUpload(deckId, file);
    setDeck(res.deck || res);
    return true;
  });
  const clearTemplate = () => run(t("busy_saving"), async () => {
    const res = await api.templateClear(deckId);
    setDeck(res.deck || res);
    return true;
  });

  const choose = (id) => run(t("busy_saving"), async () => {
    const res = await api.deckUpdate(deckId, { theme: id });
    setDeck(res.deck || res);
    return true;
  });

  if (themes.error) return <Empty>{themes.error.message}</Empty>;
  return (
    <div className="space-y-4">
      <Section title={t("template_title")}>
        <p className="help mb-3">{t("template_help")}</p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="btn">
            {t("template_upload")}
            <input type="file" accept=".pptx" aria-label={t("template_upload")} className="sr-only-live" disabled={!!busy}
              onChange={(e) => { uploadTemplate(e.target.files[0]); e.target.value = ""; }} />
          </label>
          {deck.template && <>
            <span className="min-w-0 [overflow-wrap:anywhere]" role="status">{deck.template.name}</span>
            <button type="button" className="btn" disabled={!!busy} onClick={clearTemplate}>{t("template_clear")}</button>
          </>}
        </div>
        {deck.template && <p className="help mt-3">{t("template_preview_help")}</p>}
      </Section>
      <Section title={t("theme_choose")} right={<span className="help">{t("theme_help")}</span>}>
        <div role="radiogroup" aria-label={t("theme_choose")} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((th) => (
            <label key={th.id} className="theme-card">
              <input type="radio" name="theme" className="sr-only-live" checked={deck.theme === th.id} disabled={!!busy} onChange={() => choose(th.id)} />
              <Mini theme={th} title={deck.title} subtitle={deck.audience || deck.brief || ""} />
              <div className="mt-2 flex items-center justify-between gap-2">
                <span className="font-semibold">{th.name}</span>
                {deck.theme === th.id && <span className="chip chip-accent">{t("theme_current")}</span>}
              </div>
              <div className="help">{th.fonts?.heading} · {th.fonts?.body}{th.custom ? ` · ${t("theme_ds_badge")}` : ""}</div>
            </label>
          ))}
        </div>
      </Section>
      <FromDesignSystems deckId={deckId} setDeck={setDeck} run={run} busy={busy} onCreated={themes.reload} />
      {first && (
        <Section title={t("theme_real")}>
          {deck.template && <p className="help mb-3">{t("template_preview_help")}</p>}
          <div className="max-w-2xl"><SlideFrame deckId={deckId} slide={first} theme={deck.theme} title={t("theme_real")} /></div>
        </Section>
      )}
    </div>
  );
}
